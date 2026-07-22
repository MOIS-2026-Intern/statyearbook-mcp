# -*- coding: utf-8 -*-
"""OpenAI Responses API 호환 provider가 공유하는 응답·tool-call 처리."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from backend.config import Settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.models.tooling import ModelMessage, ModelTurn, ToolCall, ToolResult, ToolSpec
from backend.serializers.mcp_result_serializer import (
    json_dumps,
    parse_json_object,
    to_jsonable,
)


@dataclass(frozen=True)
class OpenAIContinuationState:
    input_items: list[Any]


class OpenAICompatibleGateway:
    # 공통 모델 설정과 OpenAI 호환 클라이언트를 보관한다.
    def __init__(self, settings: Settings, client: AsyncOpenAI):
        self._settings = settings
        self._client = client

    # 현재 입력과 도구 사양으로 Responses API 요청을 실행한다.
    async def create_response(
        self,
        *,
        instructions: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
        model_profile: str,
    ) -> Any:
        reasoning = _reasoning_for_profile(model_profile)
        kwargs: dict[str, Any] = {
            "model": self._settings.chat_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "parallel_tool_calls": False,
        }
        if reasoning is not None:
            kwargs["reasoning"] = reasoning

        return await self._client.responses.create(**kwargs)

    # 대화 상태와 도구 결과를 이어 모델의 한 턴을 구성한다.
    async def create_turn(
        self,
        *,
        instructions: str,
        messages: list[ModelMessage],
        tools: list[ToolSpec],
        model_profile: str,
        tool_results: list[ToolResult] | None = None,
        state: object | None = None,
    ) -> ModelTurn:
        input_items = _input_items_from_state(state, messages)
        input_items.extend(_function_call_output(result) for result in tool_results or [])

        response = await self.create_response(
            instructions=instructions,
            input_items=input_items,
            tools=[_openai_tool_from_spec(tool) for tool in tools],
            model_profile=model_profile,
        )

        output_items = to_jsonable(getattr(response, "output", []))
        input_items.extend(output_items)
        tool_calls = _function_calls(response)
        return ModelTurn(
            text=_response_text(response, default="" if tool_calls else _missing_text_message()),
            tool_calls=tool_calls,
            state=OpenAIContinuationState(input_items=input_items),
        )


# UI 모델 프로필을 Responses API reasoning 강도로 변환한다.
def _reasoning_for_profile(model_profile: str) -> dict[str, str] | None:
    if model_profile == "fast":
        return {"effort": "none"}
    if model_profile == "deep":
        return {"effort": "medium"}
    return {"effort": "low"}


# 최초 메시지 또는 직전 응답 상태에서 API 입력 항목을 복원한다.
def _input_items_from_state(state: object | None, messages: list[ModelMessage]) -> list[Any]:
    if state is None:
        return [{"role": message.role, "content": message.content} for message in messages]

    if not isinstance(state, OpenAIContinuationState):
        raise ModelGatewayConfigurationError(
            "Invalid OpenAI-compatible continuation state"
        )

    return list(state.input_items)


# 내부 도구 사양을 Responses API의 function tool 형식으로 바꾼다.
def _openai_tool_from_spec(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
        "strict": False,
    }


# MCP 도구 결과를 Responses API에 이어 보낼 function output으로 직렬화한다.
def _function_call_output(result: ToolResult) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": result.call_id,
        "output": json_dumps(result.result),
    }


# 모델 응답에서 function call을 추출하고 인자 파싱 오류를 보존한다.
def _function_calls(response: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in getattr(response, "output", []):
        if _get(item, "type") != "function_call":
            continue

        raw_arguments = _get(item, "arguments")
        try:
            arguments = parse_json_object(raw_arguments)
            arguments_error = None
        except Exception as exc:
            arguments = {}
            arguments_error = str(exc)

        calls.append(
            ToolCall(
                id=str(_get(item, "call_id") or _get(item, "id") or ""),
                name=str(_get(item, "name") or ""),
                arguments=arguments,
                raw_arguments=raw_arguments,
                arguments_error=arguments_error,
            )
        )
    return calls


# Responses API의 편의 필드 또는 output message에서 표시할 텍스트를 추출한다.
def _response_text(response: Any, *, default: str) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    payload = to_jsonable(response)
    chunks: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)

    text = "\n".join(chunks).strip()
    if text:
        return text
    return default


# 응답에 표시 가능한 텍스트가 없을 때의 안내 메시지를 반환한다.
def _missing_text_message() -> str:
    return "응답을 생성했지만 표시할 텍스트를 찾지 못했습니다."


# 딕셔너리와 SDK 객체에서 동일한 방식으로 필드를 읽는다.
def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
