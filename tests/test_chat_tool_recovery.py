# -*- coding: utf-8 -*-
"""도구 입력 오류 뒤 모델이 한 번 경로를 교정할 수 있는지 검증한다."""
import asyncio
import unittest

from backend.config import Settings
from backend.models.chat import ChatRequest
from backend.models.tooling import ModelMessage, ModelTurn, ToolCall
from backend.services.chat_service import ChatService


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


if __name__ == "__main__":
    unittest.main()
