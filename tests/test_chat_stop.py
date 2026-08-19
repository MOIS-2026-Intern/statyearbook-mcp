# -*- coding: utf-8 -*-
"""사용자가 멈춘 요청이 서버의 추론·도구 호출·연결까지 끊는지 검증한다."""
import asyncio
import unittest
from unittest.mock import patch

from fastapi import Request

from backend.config import Settings
from backend.controllers import chat_controller
from backend.gateways.openai_compatible_gateway import OpenAICompatibleGateway
from backend.models.chat import ChatMessage, ChatProgress, ChatRequest, McpTrace
from backend.models.tooling import ModelMessage, ModelTurn, ToolCall, ToolSpec
from backend.prompts import SEARCH_STATISTICS_RESULT_PROMPT
from backend.services.chat_service import UNANSWERED_QUESTION_NOTE, ChatService


def _request() -> ChatRequest:
    return ChatRequest(conversationId="conversation-1", message="지방세 징수액 알려줘")


# 중단된 질문 뒤에 다시 물었을 때 프런트엔드가 보내는 요청을 재현한다. 중단 안내는 화면과
# localStorage에만 남으므로 history에 없고, 답을 받지 못한 질문과 앞선 trace는 그대로 온다.
def _follow_up_request() -> ChatRequest:
    trace = McpTrace(
        id="trace-1",
        kind="tool_call",
        status="success",
        title="search_statistics 호출",
        timestamp="2026-08-10T00:00:00Z",
        server="statyearbook",
        tool="search_statistics",
        summary="1건 반환",
        request={"arguments": {"query": "지방세 징수액"}},
        response={"structuredContent": {"count": 1, "results": [{"title_ko": "지방세 징수액 통계표"}]}},
    )
    return ChatRequest(
        conversationId="conversation-1",
        message="아까 찾은 표를 그래프로 그려줘",
        history=[
            ChatMessage(
                id="message-1",
                role="user",
                content="지방세 징수액 알려줘",
                createdAt="2026-08-10T00:00:00Z",
            ),
            ChatMessage(
                id="message-2",
                role="assistant",
                content="2024년 지방세 징수액입니다.",
                createdAt="2026-08-10T00:00:01Z",
                traceIds=["trace-1"],
            ),
            ChatMessage(
                id="message-3",
                role="user",
                content="시도별로 나눠서 보여줘",
                createdAt="2026-08-10T00:00:02Z",
            ),
        ],
        traces=[trace],
    )


def _http_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat/stream",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


class StubMcpGateway:
    """MCP 세션의 열기·닫기와 도구 호출 취소 여부를 기록한다."""

    def __init__(self, _settings: Settings):
        self.closed = False
        self.tool_calls: list[str] = []
        self.tool_call_cancelled = False

    async def __aenter__(self) -> "StubMcpGateway":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        self.closed = True

    @property
    def tool_specs_cache_hit(self) -> bool:
        return False

    async def list_tool_specs(self) -> list[ToolSpec]:
        return [ToolSpec(name="search_statistics", description="검색", input_schema={})]

    def prepare_tool_arguments(self, _name: str, arguments: dict) -> dict:
        return dict(arguments)

    async def call_tool(self, name: str, _arguments: dict) -> dict:
        self.tool_calls.append(name)
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.tool_call_cancelled = True
            raise
        return {}


class StubModelGateway:
    """준비된 턴을 모두 쓰면 무기한 생성 중인 모델을 흉내 낸다."""

    def __init__(self, turns: list[ModelTurn] | None = None):
        self.turns = list(turns or [])
        self.calls: list[dict] = []
        self.cancelled = False

    async def create_turn(self, **kwargs) -> ModelTurn:
        self.calls.append(kwargs)
        if self.turns:
            return self.turns.pop(0)
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ModelTurn(text="", tool_calls=[], state=None)


class StubStream:
    """조각을 하나 흘린 뒤 계속 생성 중인 모델 응답 스트림을 흉내 낸다."""

    def __init__(self):
        self.closed = False

    def __aiter__(self):
        async def iterate():
            yield _StubEvent("response.output_text.delta", delta="지방세 ")
            await asyncio.sleep(3600)

        return iterate()

    async def close(self) -> None:
        self.closed = True


class _StubEvent:
    def __init__(self, kind: str, **fields):
        self.type = kind
        self.__dict__.update(fields)


class StubStreamingClient:
    def __init__(self, stream: StubStream):
        self._stream = stream

    @property
    def responses(self):
        return self

    async def create(self, **_kwargs):
        return self._stream

    async def close(self) -> None:
        return None


class ChatStopTests(unittest.IsolatedAsyncioTestCase):
    # 멈춤은 도구를 기다리는 중에도 도착한다. 호출과 MCP 세션이 함께 끝나야 한다.
    async def test_stopping_cancels_the_tool_call_and_closes_the_session(self) -> None:
        model = StubModelGateway(
            [
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(id="call-1", name="search_statistics", arguments={"query": "지방세"})
                    ],
                    state=None,
                )
            ]
        )
        service = ChatService(Settings(), model_gateway=model)
        gateways: list[StubMcpGateway] = []

        def build_gateway(settings: Settings) -> StubMcpGateway:
            gateway = StubMcpGateway(settings)
            gateways.append(gateway)
            return gateway

        with patch("backend.services.chat_service.McpGateway", build_gateway):
            task = asyncio.create_task(service.respond(_request()))
            await _wait_until(lambda: bool(gateways) and bool(gateways[0].tool_calls))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertTrue(gateways[0].tool_call_cancelled)
        self.assertTrue(gateways[0].closed)

    # 응답 생성 중에 멈추면 모델 호출이 끊기고 결과는 만들어지지 않아야 한다.
    async def test_stopping_during_generation_produces_no_response(self) -> None:
        model = StubModelGateway()
        service = ChatService(Settings(), model_gateway=model)
        progress: list[str] = []

        with self.assertLogs("backend.services.chat_service", level="INFO") as logs:
            with patch("backend.services.chat_service.McpGateway", StubMcpGateway):
                task = asyncio.create_task(
                    service.respond(
                        _request(),
                        on_progress=lambda event: progress.append(event.stage),
                    )
                )
                await _wait_until(lambda: bool(model.calls))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

        messages = [record.getMessage() for record in logs.records]
        self.assertTrue(model.cancelled)
        self.assertTrue(task.cancelled())
        self.assertNotIn("finalizing", progress)
        # 중단은 오류가 아니므로 요청 기록에도 그대로 남는다.
        self.assertTrue(any("outcome=stopped" in message for message in messages))

    # 멈춘 요청의 대화 상태와 도구 결과가 다음 질의로 새면 안 된다.
    async def test_next_request_starts_without_the_stopped_state(self) -> None:
        stopped_model = StubModelGateway()
        service = ChatService(Settings(), model_gateway=stopped_model)

        with patch("backend.services.chat_service.McpGateway", StubMcpGateway):
            task = asyncio.create_task(service.respond(_request()))
            await _wait_until(lambda: bool(stopped_model.calls))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            next_model = StubModelGateway([ModelTurn(text="새 답변", tool_calls=[], state=None)])
            service = ChatService(Settings(), model_gateway=next_model)
            response = await service.respond(_request())

        first_call = next_model.calls[0]
        self.assertEqual(response.message.content, "새 답변")
        self.assertIsNone(first_call["state"])
        self.assertEqual(first_call["tool_results"], [])
        self.assertEqual(
            [message.content for message in first_call["messages"]],
            ["지방세 징수액 알려줘"],
        )


class StoppedTurnFollowUpTests(unittest.IsolatedAsyncioTestCase):
    # 중단한 뒤 이어서 물으면 답을 받지 못한 질문과 앞선 대화·trace를 모두 알고 답해야 한다.
    async def test_follow_up_keeps_the_stopped_question_and_earlier_traces(self) -> None:
        model = StubModelGateway([ModelTurn(text="이어서 답합니다.", tool_calls=[], state=None)])
        service = ChatService(Settings(), model_gateway=model)

        with patch("backend.services.chat_service.McpGateway", StubMcpGateway):
            await service.respond(_follow_up_request())

        first_call = model.calls[0]
        contents = [message.content for message in first_call["messages"]]
        self.assertEqual(
            [content.split("\n")[0] for content in contents],
            [
                "지방세 징수액 알려줘",
                "2024년 지방세 징수액입니다.",
                "시도별로 나눠서 보여줘",
                "아까 찾은 표를 그래프로 그려줘",
            ],
        )
        # 앞선 답변에는 그때 사용한 MCP 요청·응답이 붙어 모델이 근거를 다시 읽을 수 있다.
        self.assertIn("search_statistics", contents[1])
        self.assertIn("지방세 징수액 통계표", contents[1])
        # 중단 안내는 모델이 만든 답이 아니므로 입력에 없어야 한다.
        self.assertNotIn("사용자에 의해 응답이 중단되었습니다", "\n".join(contents))
        # 직전 도구 맥락도 복원되어 그 도구의 응답 규칙이 이번 턴 지시문으로 전달된다.
        self.assertIn(SEARCH_STATISTICS_RESULT_PROMPT, first_call["turn_instructions"])
        # 라운드마다 달라지는 이 규칙이 고정 지시문에 섞이면 프롬프트 캐시가 끊긴다.
        self.assertNotIn(SEARCH_STATISTICS_RESULT_PROMPT, first_call["instructions"])

    # 답을 받지 못한 질문에는 배경 참고용이라는 표시가 붙어야, 맥락이 다른 새 질문에서 모델이
    # 두 질문에 모두 답하지 않는다. 이미 답한 질문에는 이 표시가 붙지 않는다.
    async def test_unanswered_question_is_marked_as_background_context(self) -> None:
        model = StubModelGateway([ModelTurn(text="이어서 답합니다.", tool_calls=[], state=None)])
        service = ChatService(Settings(), model_gateway=model)

        with patch("backend.services.chat_service.McpGateway", StubMcpGateway):
            await service.respond(_follow_up_request())

        contents = [message.content for message in model.calls[0]["messages"]]
        self.assertIn(UNANSWERED_QUESTION_NOTE, contents[2])
        self.assertNotIn(UNANSWERED_QUESTION_NOTE, contents[0])
        # 이번 질문 자체는 표시 없이 그대로 전달된다.
        self.assertEqual(contents[3], "아까 찾은 표를 그래프로 그려줘")


class ChatStreamStopTests(unittest.IsolatedAsyncioTestCase):
    # 멈춤 버튼은 스트림을 끊는다. 서버는 실행 중이던 채팅 task를 함께 취소해야 한다.
    async def test_closing_the_stream_cancels_the_running_chat(self) -> None:
        cancelled = asyncio.Event()

        class SlowService:
            async def respond(self, _payload, on_progress=None, on_text_delta=None):
                on_progress(ChatProgress(stage="planning", message="분석 중입니다."))
                on_text_delta("지방세 ")
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        with patch.object(chat_controller, "_get_chat_service", SlowService):
            stream = chat_controller._stream_chat_events(_request())
            first = await anext(stream)
            await stream.aclose()

        self.assertIn(b'"type":"progress"', first)
        self.assertTrue(cancelled.is_set())

    # 브라우저가 요청을 끊으면 서버는 http.disconnect로 그 사실을 받는다. 응답을 끝까지
    # 기다리지 않고 그 자리에서 추론을 멈춰야 한다.
    async def test_client_disconnect_stops_the_response(self) -> None:
        cancelled = asyncio.Event()

        class SlowService:
            async def respond(self, _payload, on_progress=None, on_text_delta=None):
                on_progress(ChatProgress(stage="planning", message="분석 중입니다."))
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        with patch.object(chat_controller, "_get_chat_service", SlowService):
            response = await chat_controller.stream_chat(_request(), _http_request())
            body: list[bytes] = []
            disconnected = asyncio.Event()

            async def receive() -> dict:
                await disconnected.wait()
                return {"type": "http.disconnect"}

            async def send(message: dict) -> None:
                if message.get("body"):
                    body.append(message["body"])
                    # 첫 진행 상태를 받은 사용자가 멈춤 버튼을 누른다.
                    disconnected.set()

            await asyncio.wait_for(
                response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send),
                timeout=2.0,
            )

        self.assertIn(b'"type":"progress"', body[0])
        self.assertTrue(cancelled.is_set())


class ModelStreamStopTests(unittest.IsolatedAsyncioTestCase):
    # 생성 중 멈추면 모델 응답 스트림도 닫아 토큰을 계속 받지 않아야 한다.
    async def test_cancelling_a_turn_closes_the_model_stream(self) -> None:
        stream = StubStream()
        gateway = OpenAICompatibleGateway(Settings(), StubStreamingClient(stream))
        gateway._streaming_supported = True
        received: list[str] = []

        task = asyncio.create_task(
            gateway.create_turn(
                instructions="지시",
                messages=[ModelMessage(role="user", content="질문")],
                tools=[],
                on_text_delta=received.append,
            )
        )
        await _wait_until(lambda: bool(received))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertTrue(stream.closed)
        # 받다 만 조각은 이 요청 안에만 남아 있었으므로 이어 붙일 답변이 없다.
        self.assertEqual(received, ["지방세 "])


# 조건이 만족될 때까지 이벤트 루프에 제어를 넘기며 짧게 기다린다.
async def _wait_until(condition, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("조건이 제한 시간 안에 만족되지 않았습니다.")
        await asyncio.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
