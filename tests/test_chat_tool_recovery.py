# -*- coding: utf-8 -*-
"""도구 입력 오류 뒤 모델이 한 번 경로를 교정할 수 있는지 검증한다."""
import asyncio
import json
import unittest

from backend.config import Settings
from backend.models.chat import ChatRequest
from backend.models.tooling import ModelMessage, ModelTurn, ToolCall, ToolSpec
from backend.services.chat_service import ChatService, _model_result_for_tool


class StubModelGateway:
    def __init__(self, turns: list[ModelTurn]):
        self.turns = list(turns)
        self.calls: list[dict] = []

    async def create_turn(self, **kwargs) -> ModelTurn:
        self.calls.append(kwargs)
        return self.turns.pop(0)


class StubMcpGateway:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def prepare_tool_arguments(self, _name: str, arguments: dict) -> dict:
        return dict(arguments)

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        return self.responses.pop(0)


def _request() -> ChatRequest:
    return ChatRequest(
        conversationId="conversation-1",
        message="마을세무사 관련해서 누구한테 물어봐야 해",
    )


def _messages() -> list[ModelMessage]:
    return [
        ModelMessage(
            role="user",
            content="마을세무사 관련해서 누구한테 물어봐야 해",
        )
    ]


def _input_error() -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "Error executing tool analyze_publications: unsupported "
                    "value_filters field for subject=contacts: statistic_title"
                ),
            }
        ],
        "isError": True,
    }


class ChatToolRecoveryTests(unittest.TestCase):
    # 잘못 고른 analyze_publications 입력 오류를 모델에 돌려줘 검색 도구로 교정하게 한다.
    def test_retries_once_after_tool_input_error(self) -> None:
        model = StubModelGateway(
            [
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="analyze_publications",
                            arguments={"operation": "list", "subject": "contacts"},
                        )
                    ],
                ),
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="call-2",
                            name="search_statistics",
                            arguments={"query": "마을세무사"},
                        )
                    ],
                ),
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="call-3",
                            name="search_contacts",
                            arguments={"stat_id": 1},
                        )
                    ],
                ),
                ModelTurn(text="담당 정보를 확인했습니다."),
            ]
        )
        mcp = StubMcpGateway(
            [
                _input_error(),
                {
                    "content": [{"type": "text", "text": "통계표 후보 1건"}],
                    "structuredContent": {
                        "count": 1,
                        "results": [{"stat_id": 1, "title_ko": "마을세무사 운영"}],
                    },
                    "isError": False,
                },
                {
                    "content": [{"type": "text", "text": "담당 정보 1건"}],
                    "structuredContent": {
                        "found": True,
                        "stat_id": 1,
                        "contacts": [
                            {
                                "department": "지방세정책과",
                                "officer": "홍길동",
                                "phone": "044-000-0000",
                            }
                        ],
                    },
                    "isError": False,
                },
            ]
        )
        service = ChatService(Settings(max_tool_rounds=5), model_gateway=model)

        result = asyncio.run(
            service._run_model_loop(
                request=_request(),
                mcp=mcp,
                traces=[],
                messages=_messages(),
                tools=[],
            )
        )

        self.assertEqual(result, "담당 정보를 확인했습니다.")
        self.assertEqual(
            [name for name, _arguments in mcp.calls],
            ["analyze_publications", "search_statistics", "search_contacts"],
        )
        self.assertTrue(model.calls[1]["tool_results"][0].is_error)
        self.assertFalse(model.calls[2]["tool_results"][0].is_error)
        self.assertFalse(model.calls[3]["tool_results"][0].is_error)

    # 성공했지만 질문과 대상이 다른 결과를 받아도 루프가 끝나지 않고 다른 도구로 이어갈 수 있어야 한다.
    def test_allows_tool_switch_after_off_target_success(self) -> None:
        model = StubModelGateway(
            [
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="analyze_publications",
                            arguments={"operation": "count", "subject": "organizations"},
                        )
                    ],
                ),
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="call-2",
                            name="search_statistics",
                            arguments={"query": "중앙행정기관"},
                        )
                    ],
                ),
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(id="call-3", name="search_tables", arguments={"stat_id": 7}),
                    ],
                ),
                ModelTurn(text="중앙행정기관은 통계표 기준으로 확인했습니다."),
            ]
        )
        mcp = StubMcpGateway(
            [
                {
                    "content": [{"type": "text", "text": "담당 부서 집계"}],
                    "structuredContent": {
                        "ok": True,
                        "operation": "count",
                        "subject": "organizations",
                        "basis": "contacts.dept를 공백 정규화한 DISTINCT 값",
                        "count": 87,
                        "matched_publications": 1,
                    },
                    "isError": False,
                },
                {
                    "content": [{"type": "text", "text": "통계표 후보 1건"}],
                    "structuredContent": {
                        "count": 1,
                        "results": [{"stat_id": 7, "title_ko": "정부조직 변천"}],
                    },
                    "isError": False,
                },
                {
                    "content": [{"type": "text", "text": "통계표 원문"}],
                    "structuredContent": {"found": True, "stat_id": 7, "table_md": "| 부 | 처 |"},
                    "isError": False,
                },
            ]
        )
        service = ChatService(Settings(max_tool_rounds=5), model_gateway=model)

        result = asyncio.run(
            service._run_model_loop(
                request=_request(),
                mcp=mcp,
                traces=[],
                messages=_messages(),
                tools=[],
            )
        )

        self.assertEqual(result, "중앙행정기관은 통계표 기준으로 확인했습니다.")
        self.assertEqual(
            [name for name, _arguments in mcp.calls],
            ["analyze_publications", "search_statistics", "search_tables"],
        )

    # 교정 호출도 입력 오류면 반복하지 않고 기존 실패 응답으로 종료해야 한다.
    def test_stops_after_one_input_error_retry(self) -> None:
        model = StubModelGateway(
            [
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="analyze_publications",
                            arguments={"operation": "list"},
                        )
                    ],
                ),
                ModelTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="call-2",
                            name="analyze_publications",
                            arguments={"operation": "list"},
                        )
                    ],
                ),
            ]
        )
        mcp = StubMcpGateway([_input_error(), _input_error()])
        service = ChatService(Settings(max_tool_rounds=5), model_gateway=model)

        result = asyncio.run(
            service._run_model_loop(
                request=_request(),
                mcp=mcp,
                traces=[],
                messages=_messages(),
                tools=[],
            )
        )

        self.assertIn("호출이 실패해", result)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(len(mcp.calls), 2)

    # 검색 결과가 0건이면 종료 문구로 끝내지 말고 모델이 검색어를 다시 잡을 기회를 한 번 줘야 한다.
    def test_retries_once_when_search_returns_no_results(self) -> None:
        empty = {
            "content": [{"type": "text", "text": "결과 없음"}],
            "structuredContent": {"query": "중앙행정기관 현황", "count": 0, "results": []},
            "isError": False,
        }
        model = StubModelGateway(
            [
                ModelTurn(text="", tool_calls=[ToolCall(
                    id="call-1", name="search_statistics",
                    arguments={"query": "중앙행정기관 현황"})]),
                ModelTurn(text="", tool_calls=[ToolCall(
                    id="call-2", name="search_statistics",
                    arguments={"query": "정부조직"})]),
                ModelTurn(text="정부조직 변천 표로 확인했습니다."),
            ]
        )
        mcp = StubMcpGateway(
            [
                empty,
                {
                    "content": [{"type": "text", "text": "후보 1건"}],
                    "structuredContent": {
                        "count": 1,
                        "results": [{"stat_id": 330, "title_ko": "정부조직 변천"}],
                    },
                    "isError": False,
                },
            ]
        )
        service = ChatService(Settings(max_tool_rounds=5), model_gateway=model)

        result = asyncio.run(service._run_model_loop(
            request=_request(), mcp=mcp, traces=[], messages=_messages(), tools=[]))

        self.assertEqual(result, "정부조직 변천 표로 확인했습니다.")
        self.assertEqual([q["query"] for _n, q in mcp.calls],
                         ["중앙행정기관 현황", "정부조직"])

    # 재검색도 0건이면 반복하지 않고 못 찾았다고 답해야 한다.
    def test_stops_after_one_no_results_retry(self) -> None:
        empty = {
            "content": [{"type": "text", "text": "결과 없음"}],
            "structuredContent": {"query": "없는통계", "count": 0, "results": []},
            "isError": False,
        }
        model = StubModelGateway(
            [
                ModelTurn(text="", tool_calls=[ToolCall(
                    id="call-1", name="search_statistics", arguments={"query": "없는통계"})]),
                ModelTurn(text="", tool_calls=[ToolCall(
                    id="call-2", name="search_statistics", arguments={"query": "없는통계2"})]),
            ]
        )
        mcp = StubMcpGateway([empty, empty])
        service = ChatService(Settings(max_tool_rounds=5), model_gateway=model)

        result = asyncio.run(service._run_model_loop(
            request=_request(), mcp=mcp, traces=[], messages=_messages(), tools=[]))

        self.assertIn("확인하지 못했습니다", result)
        self.assertEqual(len(mcp.calls), 2)

    # 마지막 턴의 대화에는 도구 호출 기록이 남아 있다. 도구 목록을 빼고 보내면 모델이 그
    # 기록을 해석하지 못해 빈 응답을 돌려주므로, 목록은 남기고 호출만 막아야 한다.
    def test_final_turn_keeps_the_tools_and_forbids_calling_them(self) -> None:
        tools = [ToolSpec(name="search_statistics", description="검색", input_schema={})]
        found = {
            "content": [{"type": "text", "text": "후보 1건"}],
            "structuredContent": {"count": 1, "results": [{"stat_id": 1}]},
            "isError": False,
        }
        call = ModelTurn(text="", tool_calls=[ToolCall(
            id="call-1", name="search_statistics", arguments={"query": "통계"})])
        model = StubModelGateway([call, call, ModelTurn(text="정리한 답변입니다.")])
        mcp = StubMcpGateway([found, found])
        service = ChatService(Settings(max_tool_rounds=2), model_gateway=model)

        result = asyncio.run(service._run_model_loop(
            request=_request(), mcp=mcp, traces=[], messages=_messages(), tools=tools))

        self.assertEqual(result, "정리한 답변입니다.")
        final_call = model.calls[-1]
        self.assertEqual(final_call["tools"], tools)
        self.assertEqual(final_call["tool_choice"], "none")

    # tool_choice를 받지 못하는 공급자에서는 마지막 턴이 또 도구를 부르며 본문을 비울 수
    # 있다. 그대로 두면 사용자에게 빈 답이 나가므로 안내 문구로 갈음해야 한다.
    def test_final_turn_without_text_returns_a_message(self) -> None:
        found = {
            "content": [{"type": "text", "text": "후보 1건"}],
            "structuredContent": {"count": 1, "results": [{"stat_id": 1}]},
            "isError": False,
        }
        call = ModelTurn(text="", tool_calls=[ToolCall(
            id="call-1", name="search_statistics", arguments={"query": "통계"})])
        model = StubModelGateway([call, call, call])
        mcp = StubMcpGateway([found, found])
        service = ChatService(Settings(max_tool_rounds=2), model_gateway=model)

        result = asyncio.run(service._run_model_loop(
            request=_request(), mcp=mcp, traces=[], messages=_messages(), tools=[]))

        self.assertIn("도구 호출 횟수", result)
        self.assertIn("좁혀", result)

    # 도구를 부르는 도중의 턴까지 호출을 막으면 필요한 자료를 더 찾을 수 없다.
    def test_tool_rounds_leave_tool_choice_unset(self) -> None:
        model = StubModelGateway([ModelTurn(text="바로 답합니다.")])
        service = ChatService(Settings(max_tool_rounds=2), model_gateway=model)

        asyncio.run(service._run_model_loop(
            request=_request(), mcp=StubMcpGateway([]), traces=[],
            messages=_messages(), tools=[]))

        self.assertIsNone(model.calls[0].get("tool_choice"))


class SearchTablesResultTextTests(unittest.TestCase):
    @staticmethod
    def _model_text(tables: list) -> str:
        result = _model_result_for_tool(
            "search_tables",
            {
                "structuredContent": {"found": True, "stat_id": 329, "tables": tables},
                "isError": False,
            },
        )
        return result["content"][0]["text"]

    # 조직도처럼 표가 없는 통계표는 조회가 성공해도 수치를 못 읽는다고 알려야 한다.
    def test_says_the_statistic_has_no_table_body(self) -> None:
        text = self._model_text([])

        self.assertIn("표 본문이 없습니다", text)
        self.assertIn("has_tables", text)

    # 표가 있으면 기존 문구를 그대로 유지해 불필요한 경로 변경을 유도하지 않는다.
    def test_keeps_the_normal_message_when_a_table_exists(self) -> None:
        text = self._model_text([{"seq": 1, "table_md": "| 구분 |\n|---|\n| 부 |"}])

        self.assertEqual(text, "통계표 원문과 메타데이터를 조회했습니다.")


class DuplicatedToolPayloadTests(unittest.TestCase):
    @staticmethod
    def _list_result(rows: int) -> dict:
        payload = {
            "ok": True,
            "operation": "list",
            "result_count": rows,
            "results": [{"ref_id": f"1-1-{i}", "statistic_title": "정부 조직도"} for i in range(rows)],
        }
        return {
            "content": [
                {"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}
            ],
            "structuredContent": payload,
            "isError": False,
        }

    # MCP가 같은 목록을 텍스트와 structuredContent로 두 번 실어 모델 입력 한도를 반으로 깎는다.
    def test_drops_the_text_copy_of_the_structured_payload(self) -> None:
        raw = self._list_result(200)

        result = _model_result_for_tool("analyze_publications", raw)

        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["text"], "도구 결과는 structuredContent에 있습니다.")
        self.assertLess(len(json.dumps(result, ensure_ascii=False)),
                        len(json.dumps(raw, ensure_ascii=False)) // 2)

    # 텍스트를 걷어내도 모델이 답에 쓸 행은 하나도 잃지 않아야 한다.
    def test_keeps_every_row_of_the_structured_payload(self) -> None:
        result = _model_result_for_tool("analyze_publications", self._list_result(200))

        self.assertEqual(result["structuredContent"]["result_count"], 200)
        self.assertEqual(len(result["structuredContent"]["results"]), 200)

    # 이미지처럼 structuredContent가 대신할 수 없는 블록은 남겨 둔다.
    def test_keeps_content_blocks_that_are_not_text(self) -> None:
        raw = self._list_result(2)
        raw["content"].append({"type": "image", "mimeType": "image/png", "omitted": True})

        result = _model_result_for_tool("analyze_publications", raw)

        self.assertEqual([item["type"] for item in result["content"]], ["text", "image"])

    # 오류 결과는 원인을 그대로 읽어야 하므로 축약하지 않는다.
    def test_leaves_error_results_untouched(self) -> None:
        raw = {"content": [{"type": "text", "text": "validation error"}], "isError": True}

        self.assertIs(_model_result_for_tool("analyze_publications", raw), raw)


if __name__ == "__main__":
    unittest.main()
