# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.config import Settings
from backend.gateways.mcp_gateway import McpGateway, describe_tool
from backend.gateways.model_gateway import ModelGateway, create_model_gateway
from backend.models.chat import ChatMessage, ChatRequest, ChatResponse, McpTrace
from backend.models.tooling import ModelMessage, ToolCall, ToolResult, ToolSpec
from backend.prompts import build_system_prompt
from backend.serializers.mcp_result_serializer import (
    json_dumps,
    truncate_jsonable,
    truncate_text,
)


class ChatService:
    # 대화 설정과 선택된 모델 gateway를 서비스에 연결한다.
    def __init__(self, settings: Settings, model_gateway: ModelGateway | None = None):
        self._settings = settings
        self._model = model_gateway or create_model_gateway(settings)

    # MCP 도구 발견과 모델 루프를 실행해 최종 채팅 응답을 구성한다.
    async def respond(self, request: ChatRequest) -> ChatResponse:
        traces: list[McpTrace] = []
        messages = _model_messages_from_request(request, self._settings.tool_output_max_chars)

        async with McpGateway(self._settings) as mcp:
            tools = await self._list_tools(mcp, traces)

            final_text = await self._run_model_loop(
                request=request,
                mcp=mcp,
                traces=traces,
                messages=messages,
                tools=tools,
            )

        returned_traces = traces if request.includeMcpTrace else []
        trace_ids = [trace.id for trace in returned_traces] or None

        return ChatResponse(
            message=ChatMessage(
                id=str(uuid4()),
                role="assistant",
                content=final_text,
                createdAt=_now_iso(),
                traceIds=trace_ids,
            ),
            traces=returned_traces,
        )

    # MCP 도구 목록을 조회하고 성공 또는 실패 trace를 남긴다.
    async def _list_tools(self, mcp: McpGateway, traces: list[McpTrace]) -> list[ToolSpec]:
        started = time.perf_counter()
        trace_id = str(uuid4())
        try:
            tools = await mcp.list_tool_specs()
        except Exception as exc:
            traces.append(
                McpTrace(
                    id=trace_id,
                    kind="error",
                    status="error",
                    title="MCP 도구 목록 조회 실패",
                    timestamp=_now_iso(),
                    server=self._settings.mcp_server_label,
                    summary=str(exc),
                    durationMs=_elapsed_ms(started),
                    request=self._mcp_connection_info(),
                    response={"error": str(exc)},
                )
            )
            raise

        traces.append(
            McpTrace(
                id=trace_id,
                kind="tool_discovery",
                status="success",
                title="MCP 도구 목록 조회",
                timestamp=_now_iso(),
                server=self._settings.mcp_server_label,
                summary=f"{len(tools)}개 도구 로드됨",
                durationMs=_elapsed_ms(started),
                request=self._mcp_connection_info(),
                response={"tools": [describe_tool(tool) for tool in tools]},
            )
        )
        return tools

    # 모델이 답을 완성하거나 최대 횟수에 도달할 때까지 도구 호출을 반복한다.
    async def _run_model_loop(
        self,
        *,
        request: ChatRequest,
        mcp: McpGateway,
        traces: list[McpTrace],
        messages: list[ModelMessage],
        tools: list[ToolSpec],
    ) -> str:
        state: object | None = None
        tool_results: list[ToolResult] = []
        historical_tool_names = _historical_tool_names(request)
        visualize_result_cache: dict[str, dict[str, Any]] = {}

        for _ in range(self._settings.max_tool_rounds):
            response_tool_names = _response_tool_names(tool_results, historical_tool_names)
            turn = await self._model.create_turn(
                instructions=build_system_prompt(response_tool_names),
                messages=messages,
                tools=tools,
                model_profile=request.modelProfile,
                tool_results=tool_results,
                state=state,
            )
            state = turn.state

            if not turn.tool_calls:
                return turn.text

            tool_results = []
            for call in turn.tool_calls:
                tool_results.append(await self._execute_tool_call(mcp, call, traces, visualize_result_cache))

        final_turn = await self._model.create_turn(
            instructions=(
                build_system_prompt(
                    _response_tool_names(tool_results, historical_tool_names)
                )
                + "\n\n도구 호출 횟수 제한에 도달했습니다. 지금까지 받은 도구 결과만 사용해 답하세요."
            ),
            messages=messages,
            tools=[],
            model_profile=request.modelProfile,
            tool_results=tool_results,
            state=state,
        )
        return final_turn.text

    # 단일 MCP 도구 호출을 실행·캐시하고 모델 결과와 trace를 함께 생성한다.
    async def _execute_tool_call(
        self,
        mcp: McpGateway,
        call: ToolCall,
        traces: list[McpTrace],
        visualize_result_cache: dict[str, dict[str, Any]],
    ) -> ToolResult:
        trace_id = str(uuid4())
        started = time.perf_counter()
        request_arguments = call.raw_arguments if call.arguments_error else call.arguments

        try:
            if call.arguments_error:
                raise ValueError(call.arguments_error)
            if not call.name:
                raise ValueError("tool name is missing")

            arguments = mcp.prepare_tool_arguments(call.name, call.arguments)
            request_arguments = arguments
            cache_key = json_dumps(arguments)
            reused = call.name == "visualize" and cache_key in visualize_result_cache
            if reused:
                result = visualize_result_cache[cache_key]
            else:
                result = await mcp.call_tool(call.name, arguments)
                if call.name == "visualize":
                    visualize_result_cache[cache_key] = result
            model_payload = _model_result_for_tool(call.name, result)
            model_result = truncate_jsonable(model_payload, self._settings.tool_output_max_chars)
            status = "error" if result.get("isError") else "success"

            traces.append(
                McpTrace(
                    id=trace_id,
                    kind="tool_call",
                    status=status,
                    title=f"{call.name} 호출",
                    timestamp=_now_iso(),
                    server=self._settings.mcp_server_label,
                    tool=call.name,
                    summary=(f"{_tool_summary(result)} (동일 호출 결과 재사용)" if reused else _tool_summary(result)),
                    durationMs=_elapsed_ms(started),
                    request={"arguments": arguments},
                    response=truncate_jsonable(result, self._settings.tool_output_max_chars),
                )
            )
            return ToolResult(
                call_id=call.id,
                name=call.name,
                result=model_result,
                is_error=bool(result.get("isError")),
            )
        except Exception as exc:
            error_payload = {
                "error": str(exc),
                "tool": call.name,
                "arguments": request_arguments,
            }
            traces.append(
                McpTrace(
                    id=trace_id,
                    kind="error",
                    status="error",
                    title=f"{call.name or 'unknown'} 호출 실패",
                    timestamp=_now_iso(),
                    server=self._settings.mcp_server_label,
                    tool=call.name,
                    summary=str(exc),
                    durationMs=_elapsed_ms(started),
                    request={"arguments": error_payload["arguments"]},
                    response=error_payload,
                )
            )
            return ToolResult(call_id=call.id, name=call.name, result=error_payload, is_error=True)

    # trace에 표시할 현재 MCP 연결 정보를 구성한다.
    def _mcp_connection_info(self) -> dict[str, Any]:
        return {
            "transport": "streamable-http",
            "url": self._settings.mcp_url,
        }


# 성공한 도구 결과에서 호출 순서대로 도구 이름을 추출한다.
def _successful_tool_names(results: list[ToolResult]) -> tuple[str, ...]:
    return tuple(result.name for result in results if not result.is_error)


# 새 도구 결과가 있으면 과거 도구 컨텍스트보다 우선한다.
def _response_tool_names(
    current_results: list[ToolResult],
    historical_names: tuple[str, ...],
) -> tuple[str, ...]:
    """새 도구 결과가 있으면 과거 도구 컨텍스트보다 우선한다."""
    return _successful_tool_names(current_results) or historical_names


# 가장 최근 도구 사용 assistant 턴의 성공한 도구 이름을 복원한다.
def _historical_tool_names(request: ChatRequest) -> tuple[str, ...]:
    """가장 최근 도구 사용 assistant 턴의 성공한 도구 이름을 복원한다."""
    trace_by_id = {trace.id: trace for trace in request.traces}
    for message in reversed(request.history):
        if message.role != "assistant":
            continue

        names: list[str] = []
        for trace_id in message.traceIds or []:
            trace = trace_by_id.get(trace_id)
            if (
                trace is None
                or trace.kind != "tool_call"
                or trace.status != "success"
                or not trace.tool
            ):
                continue
            names.append(trace.tool)
        if names:
            return tuple(dict.fromkeys(names))
    return ()


# 구조화 결과나 text content에서 trace용 짧은 실행 요약을 만든다.
def _tool_summary(result: dict[str, Any]) -> str:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        if structured.get("ok") is False:
            return str(structured.get("error") or "MCP 도구가 오류를 반환했습니다.")
        if "count" in structured:
            return f"{structured.get('count')}건 반환"
        stat = structured.get("stat")
        chart = structured.get("chart")
        if isinstance(stat, dict) and isinstance(chart, dict):
            return f"{stat.get('title_ko', '통계표')} / {chart.get('type', 'chart')}"

    content = result.get("content") or []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            text = str(item["text"])
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                if "count" in parsed:
                    return f"{parsed.get('count')}건 반환"
                if parsed.get("found") is False:
                    return "통계표를 찾지 못했습니다."
                if parsed.get("found") is True and parsed.get("title_ko"):
                    return str(parsed["title_ko"])
            return truncate_text(text.replace("\n", " "), 140)

    if result.get("isError"):
        return "MCP 도구가 오류를 반환했습니다."
    return "MCP 도구 호출 완료"


# 후속 판단에 필요한 핵심만 모델에 넘기고 프런트엔드 trace용 원본은 보존한다.
def _model_result_for_tool(tool_name: str | None, result: dict[str, Any]) -> dict[str, Any]:
    """모델에는 후속 판단에 필요한 내용만 전달하고 프론트엔드 trace는 원본을 보존한다."""
    if result.get("isError"):
        return result

    if tool_name == "search_tables" and (structured := _structured_content_from_result(result)) is not None:
        return {
            "content": [{"type": "text", "text": "통계표 원문과 메타데이터를 조회했습니다."}],
            "structuredContent": structured,
            "isError": False,
        }

    if tool_name != "visualize":
        return result

    structured = result.get("structuredContent")
    if not isinstance(structured, dict) or structured.get("ok") is False:
        return result

    stat = structured.get("stat")
    chart = structured.get("chart")
    compact_stat = _select_keys(
        stat,
        "stat_id",
        "ref_id",
        "publication_year",
        "title_ko",
        "unit",
        "base_date",
        "table_seq",
    )
    visualization_created = isinstance(structured.get("vega_lite"), dict)
    compact_chart = _select_keys(chart, "title", "unit")
    if not visualization_created and isinstance(chart, dict) and chart.get("reason"):
        compact_chart["reason"] = chart["reason"]
    warnings = structured.get("warnings") if isinstance(structured.get("warnings"), list) else []

    if visualization_created:
        text = "시각화를 생성했습니다."
    else:
        reason = compact_chart.get("reason") or "시각화 사양이 생성되지 않았습니다."
        text = f"시각화를 생성하지 못했습니다. {reason}"

    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": {
            "ok": True,
            "visualization_created": visualization_created,
            "stat": compact_stat,
            "chart": compact_chart,
            "warnings": warnings,
        },
        "isError": False,
    }


# 구조화 필드를 우선하고 없으면 text content의 JSON object를 찾는다.
def _structured_content_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured

    for item in result.get("content") or []:
        if not isinstance(item, dict) or item.get("type") != "text" or not item.get("text"):
            continue
        try:
            parsed = json.loads(str(item["text"]))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


# 딕셔너리에서 값이 있는 요청 키만 선택한다.
def _select_keys(value: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in keys if value.get(key) is not None}


# 대화 이력과 연관 trace를 모델 입력 메시지로 구성한다.
def _model_messages_from_request(request: ChatRequest, max_trace_chars: int) -> list[ModelMessage]:
    trace_by_id = {trace.id: trace for trace in request.traces}
    messages: list[ModelMessage] = []

    for history_message in request.history:
        content = history_message.content.strip()
        if history_message.role == "assistant":
            trace_context = _trace_context_for_message(history_message, trace_by_id)
            if trace_context:
                trace_text = truncate_text(json_dumps(trace_context), max_trace_chars)
                content = (
                    f"{content}\n\n"
                    "[이전 MCP 요청/응답]\n"
                    f"{trace_text}"
                )

        if content:
            messages.append(ModelMessage(role=history_message.role, content=content))

    messages.append(ModelMessage(role="user", content=request.message))
    return messages


# assistant 메시지가 참조한 trace만 모델에 전달할 컨텍스트로 축약한다.
def _trace_context_for_message(
    message: ChatMessage,
    trace_by_id: dict[str, McpTrace],
) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for trace_id in message.traceIds or []:
        trace = trace_by_id.get(trace_id)
        if trace is None:
            continue

        payload: dict[str, Any] = {
            "kind": trace.kind,
            "status": trace.status,
            "title": trace.title,
            "server": trace.server,
            "tool": trace.tool,
            "summary": trace.summary,
            "request": trace.request,
            "response": (
                _model_result_for_tool(trace.tool, trace.response)
                if isinstance(trace.response, dict)
                else trace.response
            ),
        }
        context.append({key: value for key, value in payload.items() if value is not None})
    return context


# 현재 UTC 시각을 API 타임스탬프용 ISO 8601 문자열로 반환한다.
def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# 시작 시각부터의 경과 시간을 밀리초로 계산한다.
def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
