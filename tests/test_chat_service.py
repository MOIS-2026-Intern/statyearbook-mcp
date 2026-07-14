import asyncio
import unittest

from backend.config import Settings
from backend.models.chat import ChatMessage, ChatRequest, McpTrace
from backend.models.tooling import ToolResult
from backend.models.tooling import ModelTurn, ToolCall, ToolSpec
from backend.services.chat_service import (
    ChatService,
    _model_result_for_tool,
    _historical_tool_results,
    _search_tables_answer_violations,
    _successful_tool_names,
)


class RepairModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_turn(self, **kwargs) -> ModelTurn:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return ModelTurn(
                text="",
                tool_calls=[ToolCall(id="call-1", name="search_tables", arguments={"stat_id": 14})],
                state="searched",
            )
        if len(self.calls) == 2:
            return ModelTurn(text="재외공관 소계: 1,492명\n필요하시면 알려주세요.", state="bad-answer")
        return ModelTurn(
            text=(
                "2024년 재외공관 근무 외무공무원 현황입니다.\n\n"
                "| 구분 | 인원(명) |\n|---|---:|\n| 재외공관 소계 | 1,492 |\n\n"
                "사용 표: 외무공무원 (stat_id: 14) · 기준일: 2024.12.31. · 단위: 명"
            ),
            state="repaired",
        )


class TableMcp:
    def prepare_tool_arguments(self, _name: str, arguments: dict) -> dict:
        return arguments

    async def call_tool(self, _name: str, _arguments: dict) -> dict:
        return {
            "content": [{"type": "text", "text": "원문"}],
            "structuredContent": {
                "found": True,
                "stat_id": 14,
                "title_ko": "외무공무원",
                "unit": "명",
                "base_date": "2024.12.31.",
                "tables": [
                    {
                        "table_md": (
                            "| 연도 Year | 재 외 공 관 Overseas Missions_소계 Sub-Total | "
                            "재 외 공 관 Overseas Missions_14 등급 GR 14 | "
                            "재 외 공 관 Overseas Missions_고위 공무원단 Senior Civil Service |\n"
                            "|---|---:|---:|---:|\n| 2024 | 1,492 | 13 | 232 |"
                        )
                    }
                ],
            },
            "isError": False,
        }


class HistoricalRepairModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_turn(self, **kwargs) -> ModelTurn:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return ModelTurn(
                text="GR 14: 13명\n고위공무원단: 232명\n필요하시면 알려주세요.",
                state="bad-follow-up",
            )
        return ModelTurn(
            text="| 등급 | 인원(명) |\n|---|---:|\n| 14등급 | 13 |\n| 고위공무원단 | 232 |",
            state="repaired-follow-up",
        )


class StubbornHistoricalRepairModel(HistoricalRepairModel):
    async def create_turn(self, **kwargs) -> ModelTurn:
        self.calls.append(kwargs)
        return ModelTurn(text="지침에 따라 설명은 생략했습니다.", state=f"bad-{len(self.calls)}")


def historical_search_tables_request(message: str = "구체적으로 알려줘") -> ChatRequest:
    trace = McpTrace(
        id="table-trace",
        kind="tool_call",
        status="success",
        title="search_tables 호출",
        timestamp="2026-07-14T00:00:00Z",
        server="statyearbook",
        tool="search_tables",
        response={
            "content": [{"type": "text", "text": "원문"}],
            "structuredContent": {
                "found": True,
                "stat_id": 14,
                "title_ko": "외무공무원",
                "unit": "명",
                "base_date": "2024.12.31.",
                "tables": [
                    {
                        "table_md": (
                            "| 연도 Year | 재 외 공 관 Overseas Missions_소계 Sub-Total | "
                            "재 외 공 관 Overseas Missions_14 등급 GR 14 | "
                            "재 외 공 관 Overseas Missions_고위 공무원단 Senior Civil Service |\n"
                            "|---|---:|---:|---:|\n| 2024 | 1,492 | 13 | 232 |"
                        )
                    }
                ],
            },
            "isError": False,
        },
    )
    return ChatRequest(
        conversationId="follow-up",
        message=message,
        history=[
            ChatMessage(
                id="user-1",
                role="user",
                content="2024년 외무공무원 재외공관 수 알려줘",
                createdAt="2026-07-14T00:00:00Z",
            ),
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
    def test_restores_recent_search_tables_result_from_history(self) -> None:
        results = _historical_tool_results(historical_search_tables_request())

        self.assertEqual(_successful_tool_names(results), ("search_tables",))
        self.assertEqual(results[0].result["structuredContent"]["unit"], "명")

    def test_multiturn_follow_up_reuses_table_prompt_without_recalling_tool(self) -> None:
        model = HistoricalRepairModel()
        service = ChatService(Settings(), model_gateway=model)

        text = asyncio.run(
            service._run_model_loop(
                request=historical_search_tables_request(),
                mcp=TableMcp(),
                traces=[],
                messages=[],
                tools=[ToolSpec(name="search_tables", description="표 조회", input_schema={})],
            )
        )

        self.assertIn("| 등급 | 인원(명) |", text)
        self.assertEqual(len(model.calls), 2)
        self.assertIn("search_tables 결과 응답 형식", model.calls[0]["instructions"])
        self.assertEqual(model.calls[0]["tool_results"], [])
        self.assertIn("Markdown 표 누락", model.calls[1]["instructions"])
        self.assertIn("table_md", model.calls[1]["instructions"])

    def test_revalidates_first_repair_before_returning(self) -> None:
        model = StubbornHistoricalRepairModel()
        service = ChatService(Settings(), model_gateway=model)

        text = asyncio.run(
            service._run_model_loop(
                request=historical_search_tables_request(),
                mcp=TableMcp(),
                traces=[],
                messages=[],
                tools=[ToolSpec(name="search_tables", description="표 조회", input_schema={})],
            )
        )

        self.assertIn("| 항목 | 인원(명) |", text)
        self.assertIn("| 재외공관 소계 | 1,492 |", text)
        self.assertIn("| 14등급 | 13 |", text)
        self.assertIn("| 고위공무원단 | 232 |", text)
        self.assertEqual(len(model.calls), 3)

    def test_rewrites_non_markdown_search_tables_answer(self) -> None:
        model = RepairModel()
        service = ChatService(Settings(), model_gateway=model)
        request = ChatRequest(
            conversationId="test",
            message="2024년 외무공무원 재외공관 수를 알려줘",
            includeMcpTrace=False,
        )

        text = asyncio.run(
            service._run_model_loop(
                request=request,
                mcp=TableMcp(),
                traces=[],
                messages=[],
                tools=[ToolSpec(name="search_tables", description="표 조회", input_schema={})],
            )
        )

        self.assertIn("| 구분 | 인원(명) |", text)
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(model.calls[2]["tools"], [])
        self.assertIn("Markdown 표 누락", model.calls[2]["instructions"])

    def test_detects_reported_bad_answer(self) -> None:
        bad_answer = (
            "재외공관(소계): 1,492명\nGR 14: 13명\n"
            "추가로 그래프가 필요하시면 알려주세요."
        )
        results = [ToolResult(call_id="1", name="search_tables", result={}, is_error=False)]

        self.assertEqual(
            _search_tables_answer_violations(
                bad_answer,
                "2024년 외무공무원 재외공관 수를 알려줘",
                results,
            ),
            ["Markdown 표 누락", "불필요한 후속 제안", "영문 병기 잔존"],
        )

    def test_detects_english_labels_and_count_word_for_people(self) -> None:
        answer = (
            "| 항목 | 인원(명) |\n|---|---:|\n"
            "| 재외공관 수(소계) | 1,492 |\n"
            "| 14등급 (GR 14) | 13 |\n"
            "| 고위공무원단 (Senior Civil Service) | 232 |"
        )
        results = [
            ToolResult(
                call_id="1",
                name="search_tables",
                result={"structuredContent": {"unit": "명"}},
                is_error=False,
            )
        ]

        self.assertEqual(
            _search_tables_answer_violations(
                answer,
                "2024년 외무공무원 재외공관 수와 등급별 인원을 알려줘",
                results,
            ),
            ["영문 병기 잔존", "인원 단위 표현 오류"],
        )

    def test_detects_wide_single_year_table_and_repeated_units(self) -> None:
        answer = (
            "| 연도 | 소계 (명) | 14등급 (명) | 고위공무원단 (명) | 13등급 (명) |\n"
            "|---:|---:|---:|---:|---:|\n"
            "| 2024 | 1,492 | 13 | 232 | 2 |"
        )
        results = [
            ToolResult(
                call_id="1",
                name="search_tables",
                result={"structuredContent": {"unit": "명"}},
                is_error=False,
            )
        ]

        self.assertEqual(
            _search_tables_answer_violations(answer, "구체적으로 알려줘", results),
            ["표 머리글 단위 반복", "단일 연도 가로형 표"],
        )

    def test_detects_flattened_headers_and_items_outside_requested_family(self) -> None:
        answer = (
            "| 항목 | 값(명) |\n|---|---:|\n"
            "| 본부 | 707 |\n"
            "| 재외공관_소계 | 1,492 |\n"
            "| 재외공관_14등급 | 13 |\n"
            "| 국립외교원 | 38 |"
        )
        results = _historical_tool_results(historical_search_tables_request())

        self.assertEqual(
            _search_tables_answer_violations(
                answer,
                "2024년 외무공무원 재외공관 수 알려줘 구체적으로 알려줘",
                results,
            ),
            ["평탄화 헤더 흔적", "요청 밖 항목 포함"],
        )

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
                "chart": {
                    "title": "행정기관 위원회 - 2024",
                    "type": "bar",
                    "decision_source": "selection_plan",
                    "reason": "원본 표와 대조한 행과 지표를 사용했습니다.",
                },
                "request": {"year": 2024, "metrics": ["대통령", "국무총리", "각 부처"]},
                "data": {"record_count": 3, "records": [{"x": "대통령", "value": 19}]},
                "vega_lite": {"mark": "bar", "data": {"values": []}},
                "warnings": [],
            },
            "isError": False,
        }

        compact = _model_result_for_tool("visualize", result)
        structured = compact["structuredContent"]

        self.assertTrue(structured["visualization_created"])
        self.assertEqual(structured["stat"]["title_ko"], "행정기관 위원회")
        self.assertEqual(structured["stat"]["stat_id"], 8)
        self.assertNotIn("vega_lite", structured)
        self.assertNotIn("data", structured)
        self.assertNotIn("request", structured)
        self.assertNotIn("decision_source", structured["chart"])
        self.assertNotIn("type", structured["chart"])
        self.assertNotIn("reason", structured["chart"])

    def test_non_visualize_result_is_not_compacted(self) -> None:
        result = {"structuredContent": {"count": 1}, "isError": False}

        self.assertIs(_model_result_for_tool("search_statistics", result), result)

    def test_search_tables_removes_duplicate_text_but_keeps_structured_table(self) -> None:
        structured = {
            "found": True,
            "title_ko": "외무공무원",
            "unit": "명",
            "tables": [{"table_md": "| 연도 | 계 |\n| --- | --- |\n| 2024 | 2,237 |"}],
        }
        result = {
            "content": [{"type": "text", "text": "원문 JSON 전체"}],
            "structuredContent": structured,
            "isError": False,
        }

        compact = _model_result_for_tool("search_tables", result)

        self.assertIs(compact["structuredContent"], structured)
        self.assertNotIn("원문 JSON 전체", compact["content"][0]["text"])

    def test_search_tables_parses_json_text_when_mcp_has_no_structured_content(self) -> None:
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
