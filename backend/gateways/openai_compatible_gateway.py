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
    truncate_text,
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

# 항목 없는 응답은 같은 요청을 다시 보내면 대개 정상으로 돌아온다. 재현 실험에서 23회 중
# 3회 발생했으므로 1회 재시도로 약 1.7%까지 내려간다. 실패마다 입력을 다시 보내므로
# 값을 키우면 지연과 비용이 그만큼 늘어난다.
_EMPTY_OUTPUT_RETRIES = 1

# 게이트웨이가 모델별 어댑터로 요청을 옮기다 보면 공급자가 표현하지 못하는 파라미터가 있다.
# 이 값들은 없어도 답변을 만들 수 있으므로, 거부당하면 빼고 다시 보낸다. 나머지 파라미터는
# 빼면 요청의 뜻이 달라지므로 그대로 오류를 올린다.
_DROPPABLE_PARAMS = frozenset({"tool_choice", "parallel_tool_calls", "reasoning"})


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
        # 공급자가 표현하지 못한 파라미터는 한 번 확인한 뒤 다음 요청부터 아예 싣지 않는다.
        self._unsupported_params: set[str] = set()

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
        tool_choice: str | None = None,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> Any:
        reasoning = _reasoning_config(self._settings.model_reasoning_effort)
        kwargs: dict[str, Any] = {
            "model": self._settings.chat_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "parallel_tool_calls": False,
            "max_output_tokens": self._settings.model_max_output_tokens,
        }
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if reasoning is not None:
            kwargs["reasoning"] = reasoning
        for name in self._unsupported_params:
            kwargs.pop(name, None)

        started = perf_counter()
        try:
            response, streamed = await self._send(kwargs, on_text_delta)
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

    # 공급자가 표현하지 못한 선택 파라미터를 하나씩 덜어내며 요청을 성사시킨다.
    async def _send(
        self,
        kwargs: dict[str, Any],
        on_text_delta: TextDeltaCallback | None,
    ) -> tuple[Any, bool]:
        while True:
            try:
                return await self._request(kwargs, on_text_delta)
            except Exception as exc:
                param = _unsupported_parameter(exc)
                if param is None or param not in kwargs:
                    raise
                self._unsupported_params.add(param)
                kwargs.pop(param)
                logger.warning(
                    "event=model.parameter_unsupported provider=%s model=%s param=%s error=%s",
                    self._settings.model_provider,
                    self._settings.chat_model,
                    param,
                    truncate_text(str(exc), 300),
                )

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
                # 파라미터를 못 옮겨 실패한 요청은 스트리밍 문제가 아니므로, 그 이유로
                # 이후 요청의 스트리밍까지 끄면 안 된다.
                if _unsupported_parameter(exc.cause):
                    raise exc.cause from exc
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
        tool_results: list[ToolResult] | None = None,
        state: object | None = None,
        tool_choice: str | None = None,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ModelTurn:
        input_items = _input_items_from_state(state, messages)
        input_items.extend(_function_call_output(result) for result in tool_results or [])
        openai_tools = [_openai_tool_from_spec(tool) for tool in tools]
        streamed: list[str] = []

        # 되돌릴 수 없는 지점을 알기 위해 이미 내보낸 조각을 함께 모아 둔다.
        def collect(text: str) -> None:
            streamed.append(text)
            on_text_delta(text)

        attempt = 0
        while True:
            response = await self.create_response(
                instructions=instructions,
                input_items=input_items,
                tools=openai_tools,
                tool_choice=tool_choice,
                on_text_delta=None if on_text_delta is None else collect,
            )
            output_items = to_jsonable(getattr(response, "output", []))
            tool_calls = _function_calls(response)
            text = _response_text(response, default="")

            # 조각으로는 받았는데 완료 응답에 본문이 빠져 있으면 받은 조각을 그대로 쓴다.
            if not text and streamed:
                text = "".join(streamed).strip()
            if text or tool_calls:
                break

            # 공급자가 항목이 하나도 없는 응답을 완료 상태로 돌려주는 일이 있다. 사용자에게는
            # 안내 문구만 남으므로 무엇이 왔는지 남기고, 되돌릴 수 있으면 같은 요청을 다시 보낸다.
            incomplete_reason = _get(getattr(response, "incomplete_details", None), "reason")
            logger.warning(
                "event=model.empty_output provider=%s model=%s status=%s"
                " incomplete_reason=%s attempt=%s item_types=%s items=%s",
                self._settings.model_provider,
                self._settings.chat_model,
                getattr(response, "status", None),
                incomplete_reason,
                attempt + 1,
                [_get(item, "type") for item in output_items],
                truncate_text(json_dumps(output_items), 1200),
            )
            # 출력 토큰을 다 써서 빈 응답이면 같은 요청을 다시 보내도 같은 자리에서 끊긴다.
            if incomplete_reason == "max_output_tokens":
                text = _truncated_text_message()
                break
            if attempt >= _EMPTY_OUTPUT_RETRIES:
                text = _missing_text_message()
                break
            attempt += 1

        input_items.extend(output_items)
        return ModelTurn(
            text=text,
            tool_calls=tool_calls,
            state=OpenAIContinuationState(input_items=input_items),
        )


# 오류 본문에서 공급자가 지목한 파라미터 이름을 찾는다. 게이트웨이마다 error를 한 겹 더
# 감싸기도 하므로 두 형태를 모두 본다.
def _error_param(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    detail = body.get("error")
    if isinstance(detail, dict):
        return _error_param(detail)
    param = body.get("param")
    return param if isinstance(param, str) else None


# 요청이 파라미터를 옮기지 못해 막힌 것인지 보고, 빼도 되는 파라미터면 그 이름을 준다.
def _unsupported_parameter(exc: BaseException) -> str | None:
    if getattr(exc, "status_code", None) not in {400, 422}:
        return None

    param = _error_param(getattr(exc, "body", None)) or getattr(exc, "param", None)
    if isinstance(param, str):
        # 공급자가 지목한 파라미터가 있으면 그 값만 믿는다.
        return param if param in _DROPPABLE_PARAMS else None
    message = str(exc)
    return next((name for name in _DROPPABLE_PARAMS if f"'{name}'" in message), None)


# 설정에 고정된 추론 강도를 Responses API reasoning 필드로 만든다. 값이 비어 있으면
# 필드를 실어 보내지 않아 공급자 기본값을 그대로 쓴다.
def _reasoning_config(effort: str) -> dict[str, str] | None:
    effort = effort.strip()
    if not effort:
        return None
    return {"effort": effort}


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


# 응답에 표시 가능한 텍스트가 없을 때의 안내 메시지를 반환한다. 사용자가 할 수 있는 일이
# 다시 물어보는 것뿐이므로 원인과 함께 그 방법을 알린다.
def _missing_text_message() -> str:
    return (
        "답변을 받아오지 못했습니다. 확인한 자료가 있어도 표시할 내용이 오지 않아 "
        "이번 질문에는 답할 수 없습니다. 같은 질문을 다시 보내면 대부분 정상적으로 답변합니다."
    )


# 출력 토큰 한도에 걸려 본문이 하나도 오지 않았을 때의 안내 메시지를 반환한다.
def _truncated_text_message() -> str:
    return (
        "답변이 출력 한도에 걸려 본문이 생성되지 않았습니다. "
        "질문의 범위를 좁혀 다시 물어보면 답변을 받을 수 있습니다."
    )


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
