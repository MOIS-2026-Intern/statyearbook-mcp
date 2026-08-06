# -*- coding: utf-8 -*-
"""이전 턴의 MCP 결과가 새 질문의 답으로 재사용되지 않도록 이력 경계를 검증한다."""
import unittest

from backend.models.chat import ChatMessage, ChatRequest, McpTrace
from backend.prompts import SEARCH_STATISTICS_RESULT_PROMPT, SYSTEM_PROMPT
from backend.services.chat_service import _model_messages_from_request


def _request() -> ChatRequest:
    return ChatRequest(
        conversationId="conversation-1",
        message="정부 부처는 총 몇개야?",
        history=[
            ChatMessage(
                id="message-1",
                role="user",
                content="중앙행정기관은 총 몇개야?",
                createdAt="2026-08-06T00:00:00Z",
            ),
            ChatMessage(
                id="message-2",
                role="assistant",
                content="중앙행정기관은 총 73개입니다.",
                createdAt="2026-08-06T00:00:01Z",
                traceIds=["trace-1"],
            ),
        ],
        traces=[
            McpTrace(
                id="trace-1",
                kind="tool_call",
                status="success",
                title="search_tables 호출",
                timestamp="2026-08-06T00:00:01Z",
                server="statyearbook",
                tool="search_tables",
                request={"arguments": {"stat_id": 381}},
                response={
                    "structuredContent": {"found": True, "stat_id": 381, "table_md": "| 중앙 | 73 |"},
                    "isError": False,
                },
            )
        ],
    )


class ChatHistoryContextTests(unittest.TestCase):
    # 이전 도구 결과는 그때 질문의 근거라는 표시와 함께 전달해야 한다.
    def test_previous_trace_block_is_labelled_as_history(self) -> None:
        messages = _model_messages_from_request(_request(), 60_000)

        assistant_content = next(
            message.content for message in messages if message.role == "assistant"
        )
        self.assertIn("[이전 질문에 사용한 MCP 요청/응답", assistant_content)
        self.assertIn("이번 요청의 도구 결과로 다시 확인한다", assistant_content)
        self.assertIn("stat_id", assistant_content)

    # 새 사용자 질문은 이력 뒤에 그대로 이어져야 한다.
    def test_new_question_is_last_message(self) -> None:
        messages = _model_messages_from_request(_request(), 60_000)

        self.assertEqual(messages[-1].role, "user")
        self.assertEqual(messages[-1].content, "정부 부처는 총 몇개야?")

    # 이전 답의 숫자를 그대로 옮기지 못하게 하는 규칙이 프롬프트에 있어야 한다.
    def test_prompts_forbid_reusing_previous_answer(self) -> None:
        self.assertIn("이전 답변의 숫자를 그대로 옮기지", SYSTEM_PROMPT)
        self.assertIn("이전 질문과 말만 바꾼 질문도 새 질문", SYSTEM_PROMPT)
        self.assertIn(
            "이전 대화에서 본 숫자도", SEARCH_STATISTICS_RESULT_PROMPT
        )


if __name__ == "__main__":
    unittest.main()
