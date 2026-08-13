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


class StubIncompleteDetails:
    def __init__(self, reason: str):
        self.reason = reason


class StubResponse:
    def __init__(self, output: list, text: str = "", incomplete_reason: str | None = None):
        self.output = output
        self.output_text = text
        self.status = "incomplete" if incomplete_reason else "completed"
        self.usage = None
        self.incomplete_details = (
            StubIncompleteDetails(incomplete_reason) if incomplete_reason else None
        )

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
        self.kwargs: list[dict] = []

    @property
    def responses(self):
        return self

    async def create(self, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self) -> None:
        return None


def _run(
    client: StubClient,
    on_text_delta=None,
    streaming: bool = False,
    settings: Settings | None = None,
    **kwargs,
):
    gateway = OpenAICompatibleGateway(settings or Settings(), client)
    gateway._streaming_supported = streaming
    return asyncio.run(
        gateway.create_turn(
            instructions="지시",
            messages=[ModelMessage(role="user", content="질문")],
            tools=[],
            on_text_delta=on_text_delta,
            **kwargs,
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

        self.assertIn("답변을 받아오지 못했습니다", turn.text)
        self.assertIn("다시 보내면", turn.text)
        self.assertEqual(client.calls, _EMPTY_OUTPUT_RETRIES + 1)

    # 출력 토큰을 다 써서 빈 응답이면 같은 요청을 다시 보내도 같은 자리에서 끊긴다.
    def test_does_not_retry_a_truncated_response(self) -> None:
        client = StubClient([StubResponse([], incomplete_reason="max_output_tokens")])

        turn = _run(client)

        self.assertEqual(client.calls, 1)
        self.assertIn("출력 한도", turn.text)

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


class ToolChoiceTests(unittest.TestCase):
    # 도구 호출을 막아야 하는 마지막 턴에서만 tool_choice를 실어 보낸다.
    def test_forwards_tool_choice_when_given(self) -> None:
        client = StubClient([StubResponse(MESSAGE_OUTPUT, "정상 답변")])

        _run(client, tool_choice="none")

        self.assertEqual(client.kwargs[0]["tool_choice"], "none")

    # 값이 없으면 공급자가 기본값을 쓰도록 필드 자체를 보내지 않는다.
    def test_omits_tool_choice_by_default(self) -> None:
        client = StubClient([StubResponse(MESSAGE_OUTPUT, "정상 답변")])

        _run(client)

        self.assertNotIn("tool_choice", client.kwargs[0])


# 게이트웨이가 모델별 어댑터로 요청을 옮기지 못해 400을 돌려주는 상황을 흉내 낸다.
class StubBadRequest(Exception):
    def __init__(self, param: str | None, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.body = {
            "error": {
                "code": "adapter_mapping_unavailable",
                "message": message,
                "param": param,
                "type": "adapter_mapping_unavailable",
            }
        }


ADAPTER_MESSAGE = (
    "Adapter mapping unavailable: Chat Completions parameter 'tool_choice' cannot be "
    "represented by provider adapter Anthropic: request_parameter_mapping_unavailable"
)


class UnsupportedParameterTests(unittest.TestCase):
    # 공급자가 옮기지 못하는 파라미터는 빼고 다시 보내야 답변이 끊기지 않는다.
    def test_retries_without_the_rejected_parameter(self) -> None:
        client = StubClient([
            StubBadRequest("tool_choice", ADAPTER_MESSAGE),
            StubResponse(MESSAGE_OUTPUT, "정상 답변"),
        ])

        turn = _run(client, tool_choice="none")

        self.assertEqual(turn.text, "정상 답변")
        self.assertEqual(client.kwargs[0]["tool_choice"], "none")
        self.assertNotIn("tool_choice", client.kwargs[1])

    # param 필드가 비어 있어도 메시지에 적힌 파라미터 이름을 찾아내야 한다.
    def test_finds_the_parameter_in_the_message(self) -> None:
        client = StubClient([
            StubBadRequest(None, ADAPTER_MESSAGE),
            StubResponse(MESSAGE_OUTPUT, "정상 답변"),
        ])

        turn = _run(client, tool_choice="none")

        self.assertEqual(turn.text, "정상 답변")
        self.assertNotIn("tool_choice", client.kwargs[1])

    # 한 번 거부당한 파라미터는 다음 요청부터 아예 싣지 않는다.
    def test_remembers_the_rejected_parameter(self) -> None:
        client = StubClient([
            StubBadRequest("tool_choice", ADAPTER_MESSAGE),
            StubResponse(MESSAGE_OUTPUT, "첫 답변"),
            StubResponse(MESSAGE_OUTPUT, "다음 답변"),
        ])
        gateway = OpenAICompatibleGateway(Settings(), client)
        gateway._streaming_supported = False

        async def two_turns():
            for _ in range(2):
                await gateway.create_turn(
                    instructions="지시",
                    messages=[ModelMessage(role="user", content="질문")],
                    tools=[],
                    tool_choice="none",
                )

        asyncio.run(two_turns())

        self.assertEqual(client.calls, 3)
        self.assertNotIn("tool_choice", client.kwargs[2])

    # 파라미터 문제로 실패한 요청 때문에 이후 요청의 스트리밍까지 끄면 안 된다.
    def test_keeps_streaming_enabled_after_a_parameter_error(self) -> None:
        client = StubClient([
            StubBadRequest("tool_choice", ADAPTER_MESSAGE),
            StubStream([
                StubEvent("response.output_text.delta", delta="정상 답변"),
                StubEvent("response.completed", response=StubResponse(MESSAGE_OUTPUT, "정상 답변")),
            ]),
        ])
        gateway = OpenAICompatibleGateway(Settings(), client)
        gateway._streaming_supported = True

        turn = asyncio.run(
            gateway.create_turn(
                instructions="지시",
                messages=[ModelMessage(role="user", content="질문")],
                tools=[],
                tool_choice="none",
                on_text_delta=lambda _text: None,
            )
        )

        self.assertEqual(turn.text, "정상 답변")
        self.assertTrue(gateway._streaming_supported)

    # 파라미터 문제가 아닌 오류까지 삼키면 진짜 실패가 묻힌다.
    def test_raises_other_bad_requests(self) -> None:
        client = StubClient([StubBadRequest("input", "input is invalid")])

        with self.assertRaises(StubBadRequest):
            _run(client, tool_choice="none")

        self.assertEqual(client.calls, 1)


class ReasoningEffortTests(unittest.TestCase):
    # 추론 강도는 요청마다 달라지지 않고 배포 설정 값으로 고정된다.
    def test_sends_the_configured_effort(self) -> None:
        client = StubClient([StubResponse(MESSAGE_OUTPUT, "정상 답변")])

        _run(client, settings=Settings(model_reasoning_effort="high"))

        self.assertEqual(client.kwargs[0]["reasoning"], {"effort": "high"})

    # 이 파라미터를 받지 않는 공급자를 위해 빈 값이면 필드를 싣지 않는다.
    def test_omits_reasoning_when_effort_is_blank(self) -> None:
        client = StubClient([StubResponse(MESSAGE_OUTPUT, "정상 답변")])

        _run(client, settings=Settings(model_reasoning_effort=""))

        self.assertNotIn("reasoning", client.kwargs[0])


if __name__ == "__main__":
    unittest.main()
