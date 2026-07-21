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
    def __init__(self, settings: Settings, client: AsyncOpenAI):
        self._settings = settings
        self._client = client

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
            "model": self._settings.openai_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "parallel_tool_calls": False,
        }
        if reasoning is not None:
            kwargs["reasoning"] = reasoning

        return await self._client.responses.create(**kwargs)

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


def _reasoning_for_profile(model_profile: str) -> dict[str, str] | None:
    if model_profile == "fast":
        return {"effort": "none"}
    if model_profile == "deep":
        return {"effort": "medium"}
    return {"effort": "low"}


def _input_items_from_state(state: object | None, messages: list[ModelMessage]) -> list[Any]:
    if state is None:
        return [{"role": message.role, "content": message.content} for message in messages]

    if not isinstance(state, OpenAIContinuationState):
        raise ModelGatewayConfigurationError(
            "Invalid OpenAI-compatible continuation state"
        )

    return list(state.input_items)


def _openai_tool_from_spec(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
        "strict": False,
    }


def _function_call_output(result: ToolResult) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": result.call_id,
        "output": json_dumps(result.result),
    }


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


def _missing_text_message() -> str:
    return "응답을 생성했지만 표시할 텍스트를 찾지 못했습니다."


def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
