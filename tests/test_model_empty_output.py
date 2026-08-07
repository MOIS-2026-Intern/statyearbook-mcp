# -*- coding: utf-8 -*-
"""공급자가 항목 없는 응답을 완료로 돌려줄 때 턴이 복구되는지 검증한다."""
import asyncio
import unittest

from backend.config import Settings
from backend.gateways.openai_compatible_gateway import (
    _EMPTY_OUTPUT_RETRIES,
    OpenAICompatibleGateway,
)
from backend.models.tooling import ModelMessage


MESSAGE_OUTPUT = [
    {"type": "message", "content": [{"type": "output_text", "text": "정상 답변"}]}
]


class StubResponse:
    def __init__(self, output: list, text: str = ""):
        self.output = output
        self.output_text = text
        self.status = "completed"
        self.usage = None
        self.incomplete_details = None

    def model_dump(self, **_kwargs) -> dict:
        return {"output": self.output, "status": self.status}


class StubStream:
    def __init__(self, events: list):
        self._events = events

    def __aiter__(self):
        async def iterate():
            for event in self._events:
                yield event

        return iterate()

    async def close(self) -> None:
        return None


class StubEvent:
    def __init__(self, kind: str, **fields):
        self.type = kind
        self.__dict__.update(fields)


class StubClient:
    def __init__(self, results: list):
        self._results = list(results)
        self.calls = 0

    @property
    def responses(self):
        return self

    async def create(self, **_kwargs):
        self.calls += 1
        return self._results.pop(0)

    async def close(self) -> None:
        return None


def _run(client: StubClient, on_text_delta=None, streaming: bool = False):
    gateway = OpenAICompatibleGateway(Settings(), client)
    gateway._streaming_supported = streaming
    return asyncio.run(
        gateway.create_turn(
            instructions="지시",
            messages=[ModelMessage(role="user", content="질문")],
            tools=[],
            model_profile="balanced",
            on_text_delta=on_text_delta,
        )
    )


class EmptyOutputRetryTests(unittest.TestCase):
    # 항목 없는 응답은 같은 요청을 다시 보내면 대개 정상으로 돌아온다.
    def test_retries_once_and_recovers(self) -> None:
        client = StubClient([StubResponse([]), StubResponse(MESSAGE_OUTPUT, "정상 답변")])

        turn = _run(client)

        self.assertEqual(turn.text, "정상 답변")
        self.assertEqual(client.calls, 2)

    # 재시도까지 비면 안내 문구를 남기고 무한히 다시 부르지 않아야 한다.
    def test_stops_after_the_retry_budget(self) -> None:
        client = StubClient([StubResponse([])] * (_EMPTY_OUTPUT_RETRIES + 1))

        turn = _run(client)

        self.assertIn("표시할 텍스트를 찾지 못했습니다", turn.text)
        self.assertEqual(client.calls, _EMPTY_OUTPUT_RETRIES + 1)

    # 정상 응답을 재시도해 요금과 지연을 두 배로 쓰면 안 된다.
    def test_does_not_retry_a_healthy_response(self) -> None:
        client = StubClient([StubResponse(MESSAGE_OUTPUT, "정상 답변")])

        turn = _run(client)

        self.assertEqual(client.calls, 1)

    # 도구 호출만 있고 본문이 없는 턴은 정상이므로 재시도 대상이 아니다.
    def test_does_not_retry_a_tool_call_turn(self) -> None:
        tool_output = [
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "search_statistics",
                "arguments": '{"query": "재난관리기금"}',
            }
        ]
        client = StubClient([StubResponse(tool_output)])

        turn = _run(client)

        self.assertEqual(client.calls, 1)
        self.assertEqual([call.name for call in turn.tool_calls], ["search_statistics"])

    # 이미 내보낸 조각을 두고 다시 요청하면 사용자 화면에 같은 글이 두 번 흐른다.
    # 완료 응답이 본문을 빠뜨렸더라도 받은 조각으로 답을 세운다.
    def test_keeps_streamed_text_instead_of_retrying(self) -> None:
        client = StubClient([
            StubStream([
                StubEvent("response.output_text.delta", delta="재난관리기금 "),
                StubEvent("response.output_text.delta", delta="적립액입니다."),
                StubEvent("response.completed", response=StubResponse([])),
            ])
        ])
        received: list[str] = []

        turn = _run(client, on_text_delta=received.append, streaming=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(turn.text, "재난관리기금 적립액입니다.")
        self.assertEqual("".join(received).strip(), turn.text)


if __name__ == "__main__":
    unittest.main()
