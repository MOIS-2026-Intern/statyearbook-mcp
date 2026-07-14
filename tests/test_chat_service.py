import asyncio
import unittest

from backend.config import Settings
from backend.models.chat import ChatMessage, ChatRequest, McpTrace
from backend.models.tooling import ModelTurn, ToolResult, ToolSpec
from backend.services.chat_service import (
    ChatService,
    _historical_tool_names,
    _model_result_for_tool,
    _successful_tool_names,
)


class PassiveModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_turn(self, **kwargs) -> ModelTurn:
        self.calls.append(kwargs)
        return ModelTurn(text="자세한 내용입니다.", state="done")


def historical_search_tables_request() -> ChatRequest:
    trace = McpTrace(
        id="table-trace",
        kind="tool_call",
        status="success",
        title="search_tables 호출",
        timestamp="2026-07-14T00:00:00Z",
        server="statyearbook",
        tool="search_tables",
        response={"content": [], "isError": False},
    )
    return ChatRequest(
        conversationId="follow-up",
        message="구체적으로 알려줘",
        history=[
            ChatMessage(
                id="assistant-1",
                role="assistant",
                content="재외공관 근무 인원은 1,492명입니다.",
                createdAt="2026-07-14T00:00:01Z",
                traceIds=[trace.id],
            )
        ],
        traces=[trace],
    )


class ChatServiceModelResultTests(unittest.TestCase):
    def test_multiturn_follow_up_reuses_tool_prompt_without_recalling_tool(self) -> None:
        model = PassiveModel()
        service = ChatService(Settings(), model_gateway=model)

        text = asyncio.run(
            service._run_model_loop(
                request=historical_search_tables_request(),
                mcp=object(),
                traces=[],
                messages=[],
                tools=[ToolSpec(name="search_tables", description="표 조회", input_schema={})],
            )
        )

        self.assertEqual(text, "자세한 내용입니다.")
        self.assertEqual(len(model.calls), 1)
        self.assertIn("search_tables 결과 응답 형식", model.calls[0]["instructions"])
        self.assertEqual(model.calls[0]["tool_results"], [])

    def test_restores_search_tables_tool_name_from_history(self) -> None:
        names = _historical_tool_names(historical_search_tables_request())

        self.assertEqual(names, ("search_tables",))

    def test_result_prompt_names_exclude_failed_tools(self) -> None:
        results = [
            ToolResult(call_id="ok", name="search_tables", result={}, is_error=False),
            ToolResult(call_id="error", name="visualize", result={}, is_error=True),
        ]

        self.assertEqual(_successful_tool_names(results), ("search_tables",))

    def test_visualize_result_is_compacted_for_model_but_keeps_answer_metadata(self) -> None:
        result = {
            "content": [{"type": "text", "text": "긴 시각화 설명"}],
            "structuredContent": {
                "ok": True,
                "stat": {
                    "stat_id": 8,
                    "ref_id": "1-1-5",
                    "publication_year": 2025,
                    "title_ko": "행정기관 위원회",
                    "unit": "개",
                    "base_date": "2024.12.31.",
                    "table_seq": 2,
                },
                "chart": {"title": "행정기관 위원회 - 2024", "type": "bar"},
                "data": {"record_count": 3},
                "vega_lite": {"mark": "bar"},
                "warnings": [],
            },
            "isError": False,
        }

        compact = _model_result_for_tool("visualize", result)
        structured = compact["structuredContent"]

        self.assertTrue(structured["visualization_created"])
        self.assertEqual(structured["stat"]["title_ko"], "행정기관 위원회")
        self.assertNotIn("vega_lite", structured)
        self.assertNotIn("data", structured)
        self.assertNotIn("type", structured["chart"])

    def test_non_visualize_result_is_not_compacted(self) -> None:
        result = {"structuredContent": {"count": 1}, "isError": False}

        self.assertIs(_model_result_for_tool("search_statistics", result), result)

    def test_search_tables_parses_json_text_for_model_context(self) -> None:
        result = {
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"found":true,"stat_id":14,"title_ko":"외무공무원",'
                        '"unit":"명","tables":[{"table_md":"| 연도 | 소계 |"}]}'
                    ),
                }
            ],
            "isError": False,
        }

        compact = _model_result_for_tool("search_tables", result)

        self.assertEqual(compact["structuredContent"]["unit"], "명")
        self.assertEqual(compact["structuredContent"]["tables"][0]["table_md"], "| 연도 | 소계 |")


if __name__ == "__main__":
    unittest.main()
