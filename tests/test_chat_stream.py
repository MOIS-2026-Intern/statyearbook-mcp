import asyncio
import json
import unittest

from backend.controllers import chat_controller
from backend.models.chat import ChatMessage, ChatProgress, ChatRequest, ChatResponse


class FakeStreamingChatService:
    async def respond(self, _payload, on_progress=None) -> ChatResponse:
        on_progress(
            ChatProgress(
                stage="connecting_mcp",
                message="MCP 호스트에 연결하는 중입니다.",
            )
        )
        on_progress(
            ChatProgress(
                stage="calling_tool",
                message="search_tables MCP 도구로 통계표 원문을 확인하는 중입니다.",
                tool="search_tables",
            )
        )
        return ChatResponse(
            message=ChatMessage(
                id="assistant",
                role="assistant",
                content="응답입니다.",
                createdAt="2026-07-28T00:00:00Z",
            ),
            traces=[],
        )


class ChatStreamTests(unittest.TestCase):
    def test_stream_emits_progress_before_final_result(self) -> None:
        original_service = chat_controller._chat_service
        chat_controller._chat_service = FakeStreamingChatService()

        async def collect_events() -> list[dict]:
            chunks = [
                chunk
                async for chunk in chat_controller._stream_chat_events(
                    ChatRequest(conversationId="stream", message="통계표를 알려줘")
                )
            ]
            return [json.loads(chunk) for chunk in chunks]

        try:
            events = asyncio.run(collect_events())
        finally:
            chat_controller._chat_service = original_service

        self.assertEqual(
            [event["type"] for event in events],
            ["progress", "progress", "result"],
        )
        self.assertEqual(events[1]["progress"]["tool"], "search_tables")
        self.assertEqual(events[2]["response"]["message"]["content"], "응답입니다.")


if __name__ == "__main__":
    unittest.main()
