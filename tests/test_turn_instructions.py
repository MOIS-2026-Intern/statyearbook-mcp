# -*- coding: utf-8 -*-
"""라운드마다 달라지는 지시문을 프롬프트 앞이 아니라 대화 끝에 싣는지 검증한다."""
import asyncio
import unittest

from backend.config import Settings
from backend.gateways.openai_compatible_gateway import OpenAICompatibleGateway
from backend.models.tooling import ModelMessage
from backend.prompts import (
    build_base_system_prompt,
    build_system_prompt,
    build_tool_result_guidance,
)


BASE = "고정 지시문"
TURN = "이번 턴 지시문"
MESSAGES = [ModelMessage(role="user", content="질문")]


class StubResponse:
    def __init__(self, text: str = "답변"):
        self.output = [{"type": "message", "content": [{"type": "output_text", "text": text}]}]
        self.output_text = text
        self.status = "completed"
        self.usage = None
        self.incomplete_details = None

    def model_dump(self, **_kwargs) -> dict:
        return {"output": self.output, "status": self.status}


class StubRoleRejection(Exception):
    """공급자가 대화 끝 지시문 항목을 거부한 상황을 흉내 낸다."""

    status_code = 400
    body = None

    def __str__(self) -> str:
        return "Unsupported role 'developer' in input items"


class StubClient:
    def __init__(self, results: list):
        self._results = list(results)
        self.kwargs: list[dict] = []

    @property
    def responses(self):
        return self

    async def create(self, **kwargs):
        # input 리스트는 호출 뒤에도 gateway가 이어 쓰므로 보낸 시점 그대로 남겨 둔다.
        self.kwargs.append({**kwargs, "input": list(kwargs["input"])})
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self) -> None:
        return None


def _gateway(results: list) -> tuple[OpenAICompatibleGateway, StubClient]:
    client = StubClient(results)
    settings = Settings(openai_api_key="test", model_streaming=False)
    return OpenAICompatibleGateway(settings, client), client


def _turn(gateway, **overrides):
    kwargs = {
        "instructions": BASE,
        "messages": MESSAGES,
        "tools": [],
        "turn_instructions": TURN,
    }
    kwargs.update(overrides)
    return asyncio.run(gateway.create_turn(**kwargs))


class TurnInstructionPlacementTests(unittest.TestCase):
    # 프롬프트 앞이 라운드마다 달라지면 그 뒤의 도구 스키마와 대화 이력까지 캐시가 끊긴다.
    def test_fixed_instructions_stay_clean_and_turn_rules_go_last(self) -> None:
        gateway, client = _gateway([StubResponse()])

        _turn(gateway)

        sent = client.kwargs[0]
        self.assertEqual(sent["instructions"], BASE)
        self.assertEqual(sent["input"][-1], {"role": "developer", "content": TURN})
        self.assertEqual(sent["input"][0], {"role": "user", "content": "질문"})

    # 이번 턴 지시문이 상태에 남으면 라운드마다 쌓이고 서로 다른 도구 규칙이 겹친다.
    def test_turn_rules_are_not_carried_into_the_next_round(self) -> None:
        gateway, client = _gateway([StubResponse(), StubResponse()])

        first = _turn(gateway)
        _turn(gateway, state=first.state, turn_instructions="다음 턴 지시문")

        second = client.kwargs[1]["input"]
        self.assertEqual([item for item in second if item.get("role") == "developer"],
                         [{"role": "developer", "content": "다음 턴 지시문"}])
        self.assertNotIn(TURN, str(second))

    # 지시문이 없는 턴까지 빈 항목을 붙이면 캐시 접두사만 흔들린다.
    def test_no_item_is_added_without_turn_instructions(self) -> None:
        gateway, client = _gateway([StubResponse()])

        _turn(gateway, turn_instructions=None)

        self.assertEqual(client.kwargs[0]["input"], [{"role": "user", "content": "질문"}])

    # 공급자가 이 항목을 거부해도 답변이 끊기면 안 되므로 예전처럼 합쳐 한 번 더 보낸다.
    def test_rejected_item_falls_back_to_merged_instructions(self) -> None:
        gateway, client = _gateway([StubRoleRejection(), StubResponse(), StubResponse()])

        _turn(gateway)
        _turn(gateway)

        retried, following = client.kwargs[1], client.kwargs[2]
        self.assertEqual(retried["instructions"], f"{BASE}\n\n{TURN}")
        self.assertEqual(retried["input"], [{"role": "user", "content": "질문"}])
        # 한 번 거부당했으면 다음 요청부터는 시도하지 않는다.
        self.assertEqual(following["instructions"], f"{BASE}\n\n{TURN}")


class ComposedPromptTests(unittest.TestCase):
    # 나눠 보내더라도 모델이 받는 규칙의 총합은 이전과 같아야 한다.
    def test_split_prompts_compose_to_the_previous_prompt(self) -> None:
        for scope in ("all", "yearbook", "major_statistics"):
            for tools in ([], ["search_tables"], ["search_statistics", "visualize"]):
                with self.subTest(scope=scope, tools=tools):
                    guidance = build_tool_result_guidance(tools)
                    composed = build_base_system_prompt(scope)
                    if guidance:
                        composed = f"{composed}\n\n{guidance}"

                    self.assertEqual(composed, build_system_prompt(tools, scope))

    # 고정부에 도구 결과 규칙이 섞이면 라운드마다 프롬프트 앞이 달라진다.
    def test_base_prompt_has_no_tool_result_rules(self) -> None:
        base = build_base_system_prompt("all")

        self.assertNotIn("search_tables 결과 응답 형식", base)
        self.assertNotIn("visualize 결과 응답 형식", base)


if __name__ == "__main__":
    unittest.main()
