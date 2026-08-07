# -*- coding: utf-8 -*-
"""OpenAI Responses API 호환 provider가 공유하는 응답·tool-call 처리."""

from __future__ import annotations

import inspect
import logging

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI

from backend.config import Settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError, TextDeltaCallback
from backend.models.tooling import ModelMessage, ModelTurn, ToolCall, ToolResult, ToolSpec
from backend.serializers.mcp_result_serializer import (
    json_dumps,
    parse_json_object,
    to_jsonable,
)


logger = logging.getLogger(__name__)


# 스트림이 시작되기 전에 실패해 비스트리밍으로 되돌릴 수 있는 상황을 표시한다.
class _StreamingUnsupportedError(Exception):
    def __init__(self, cause: BaseException):
        super().__init__(str(cause))
        self.cause = cause


# 응답이 끝났음을 알리며 완성된 response 객체를 실어 오는 이벤트들이다.
_TERMINAL_STREAM_EVENTS = frozenset(
    {"response.completed", "response.incomplete", "response.failed"}
)


@dataclass(frozen=True)
class OpenAIContinuationState:
    input_items: list[Any]


class OpenAICompatibleGateway:
    # 공통 모델 설정과 OpenAI 호환 클라이언트를 보관한다.
    def __init__(self, settings: Settings, client: AsyncOpenAI):
        self._settings = settings
        self._client = client
        # 공급자나 모델이 스트리밍을 거부하면 이후 요청은 곧바로 비스트리밍으로 보낸다.
        self._streaming_supported = settings.model_streaming

    # 여러 채팅 요청이 재사용한 HTTP 클라이언트의 연결 풀을 정리한다.
    async def close(self) -> None:
        await self._client.close()

    # 현재 입력과 도구 사양으로 Responses API 요청을 실행한다.
    async def create_response(
        self,
        *,
        instructions: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
        model_profile: str,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> Any:
        reasoning = _reasoning_for_profile(model_profile)
        kwargs: dict[str, Any] = {
            "model": self._settings.chat_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "parallel_tool_calls": False,
            "max_output_tokens": self._settings.model_max_output_tokens,
        }
        if reasoning is not None:
            kwargs["reasoning"] = reasoning

        started = perf_counter()
        try:
            response, streamed = await self._request(kwargs, on_text_delta)
        except Exception as exc:
            logger.exception(
                "event=model.error provider=%s model=%s duration_ms=%s error_type=%s",
                self._settings.model_provider,
                self._settings.chat_model,
                _elapsed_ms(started),
                exc.__class__.__name__,
            )
            raise
        output = getattr(response, "output", []) or []
        tool_call_count = sum(_get(item, "type") == "function_call" for item in output)
        usage = getattr(response, "usage", None)
        incomplete_reason = _get(getattr(response, "incomplete_details", None), "reason")
        logger.debug(
            "event=model.call provider=%s model=%s duration_ms=%s tool_calls=%s streamed=%s"
            " status=%s incomplete_reason=%s max_output_tokens=%s"
            " input_tokens=%s output_tokens=%s reasoning_tokens=%s",
            self._settings.model_provider,
            self._settings.chat_model,
            _elapsed_ms(started),
            tool_call_count,
            streamed,
            getattr(response, "status", None),
            incomplete_reason,
            self._settings.model_max_output_tokens,
            _get(usage, "input_tokens"),
            _get(usage, "output_tokens"),
            _reasoning_tokens(usage),
        )
        # 응답이 잘리면 사용자에게는 정상 답변처럼 보이므로 로그로만 드러난다.
        if incomplete_reason:
            logger.warning(
                "event=model.incomplete provider=%s model=%s reason=%s"
                " max_output_tokens=%s output_tokens=%s reasoning_tokens=%s",
                self._settings.model_provider,
                self._settings.chat_model,
                incomplete_reason,
                self._settings.model_max_output_tokens,
                _get(usage, "output_tokens"),
                _reasoning_tokens(usage),
            )
        return response

    # 스트리밍을 먼저 시도하고 공급자가 거부하면 같은 요청을 비스트리밍으로 되돌린다.
    async def _request(
        self,
        kwargs: dict[str, Any],
        on_text_delta: TextDeltaCallback | None,
    ) -> tuple[Any, bool]:
        if self._streaming_supported and on_text_delta is not None:
            try:
                return await self._stream_response(kwargs, on_text_delta), True
            except _StreamingUnsupportedError as exc:
                # 조각을 하나도 내보내기 전에 실패했으므로 이번 요청부터 되돌릴 수 있다.
                self._streaming_supported = False
                logger.warning(
                    "event=model.streaming_unsupported provider=%s model=%s"
                    " error_type=%s error=%s",
                    self._settings.model_provider,
                    self._settings.chat_model,
                    exc.cause.__class__.__name__,
                    exc,
                )
        return await self._client.responses.create(**kwargs), False

    # 텍스트 조각을 흘려보내고 종료 이벤트가 실어 온 완성 응답을 반환한다.
    async def _stream_response(
        self,
        kwargs: dict[str, Any],
        on_text_delta: TextDeltaCallback,
    ) -> Any:
        emitted = False
        final: Any = None
        try:
            stream = await self._client.responses.create(**kwargs, stream=True)
            try:
                async for event in stream:
                    kind = _get(event, "type")
                    if kind == "response.output_text.delta":
                        delta = _get(event, "delta") or ""
                        if delta:
                            emitted = True
                            on_text_delta(delta)
                    elif kind in _TERMINAL_STREAM_EVENTS:
                        final = _get(event, "response")
            finally:
                await _close_stream(stream)
        except Exception as exc:
            # 이미 사용자에게 보낸 조각이 있으면 되돌릴 수 없으므로 그대로 전달한다.
            if emitted:
                raise
            raise _StreamingUnsupportedError(exc) from exc

        if final is None:
            missing = RuntimeError("streaming response ended without a terminal event")
            if emitted:
                raise missing
            raise _StreamingUnsupportedError(missing)
        return final

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
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ModelTurn:
        input_items = _input_items_from_state(state, messages)
        input_items.extend(_function_call_output(result) for result in tool_results or [])

        response = await self.create_response(
            instructions=instructions,
            input_items=input_items,
            tools=[_openai_tool_from_spec(tool) for tool in tools],
            model_profile=model_profile,
            on_text_delta=on_text_delta,
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


# 스트림을 끝까지 읽지 못한 경우에도 HTTP 연결을 확실히 반납한다.
async def _close_stream(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:  # 정리 실패가 본래 오류를 가리지 않도록 삼킨다.
        logger.debug("event=model.stream_close_failed", exc_info=True)


# Responses API usage에서 추론 토큰 수를 꺼낸다. 공급자가 제공하지 않으면 None이다.
def _reasoning_tokens(usage: Any) -> Any:
    return _get(_get(usage, "output_tokens_details"), "reasoning_tokens")


# 딕셔너리와 SDK 객체에서 동일한 방식으로 필드를 읽는다.
def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


# Convert a monotonic start timestamp into rounded milliseconds.
def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
