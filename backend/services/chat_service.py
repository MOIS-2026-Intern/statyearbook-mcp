# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.config import Settings
from backend.gateways.mcp_gateway import McpGateway, describe_tool
from backend.gateways.model_gateway import ModelGateway, create_model_gateway
from backend.models.chat import (
    ChatMessage,
    ChatProgress,
    ChatProgressStage,
    ChatRequest,
    ChatResponse,
    McpTrace,
)
from backend.models.tooling import ModelMessage, ToolCall, ToolResult, ToolSpec
from backend.prompts import build_system_prompt
from backend.serializers.mcp_result_serializer import (
    json_dumps,
    truncate_jsonable,
    truncate_text,
)

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[ChatProgress], None]


class ChatService:
    # 대화 설정과 선택된 모델 gateway를 서비스에 연결한다.
    def __init__(self, settings: Settings, model_gateway: ModelGateway | None = None):
        self._settings = settings
        self._model = model_gateway or create_model_gateway(settings)

    # MCP 도구 발견과 모델 루프를 실행해 최종 채팅 응답을 구성한다.
    async def respond(
        self,
        request: ChatRequest,
        on_progress: ProgressCallback | None = None,
    ) -> ChatResponse:
        started = time.perf_counter()
        metrics = _new_pipeline_metrics()
        outcome = "error"
        connect_recorded = False
        traces: list[McpTrace] = []
        messages = _model_messages_from_request(request, self._settings.tool_output_max_chars)

        self._emit_progress(
            on_progress,
            "connecting_mcp",
            "MCP 호스트에 연결하는 중입니다.",
        )
        connect_started = time.perf_counter()
        try:
            async with McpGateway(self._settings) as mcp:
                metrics["mcp_connect_ms"] += _elapsed_ms(connect_started)
                connect_recorded = True
                self._emit_progress(
                    on_progress,
                    "discovering_tools",
                    "사용 가능한 통계 도구를 확인하는 중입니다.",
                )
                discovery_started = time.perf_counter()
                tools = await self._list_tools(mcp, traces)
                metrics["mcp_discovery_ms"] += _elapsed_ms(discovery_started)

                final_text = await self._run_model_loop(
                    request=request,
                    mcp=mcp,
                    traces=traces,
                    messages=messages,
                    tools=tools,
                    on_progress=on_progress,
                    metrics=metrics,
                )

            returned_traces = traces if request.includeMcpTrace else []
            trace_ids = [trace.id for trace in returned_traces] or None
            outcome = "success"

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
        finally:
            if not connect_recorded:
                metrics["mcp_connect_ms"] = _elapsed_ms(connect_started)
            _log_pipeline(
                settings=self._settings,
                metrics=metrics,
                total_ms=_elapsed_ms(started),
                outcome=outcome,
            )

    # 애플리케이션이 공유한 모델 HTTP 클라이언트의 연결 풀을 종료한다.
    async def close(self) -> None:
        close = getattr(self._model, "close", None)
        if close is not None:
            await close()

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
                summary=(
                    f"{len(tools)}개 도구 로드됨"
                    + (" (캐시 사용)" if mcp.tool_specs_cache_hit else "")
                ),
                durationMs=_elapsed_ms(started),
                request={
                    **self._mcp_connection_info(),
                    "cacheHit": mcp.tool_specs_cache_hit,
                },
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
        on_progress: ProgressCallback | None = None,
        metrics: dict[str, int] | None = None,
    ) -> str:
        pipeline_metrics = metrics if metrics is not None else _new_pipeline_metrics()
        state: object | None = None
        tool_results: list[ToolResult] = []
        historical_tool_names = _historical_tool_names(request)
        visualize_result_cache: dict[str, dict[str, Any]] = {}
        tool_call_counts: dict[str, int] = {}

        for round_index in range(self._settings.max_tool_rounds):
            if round_index == 0:
                self._emit_progress(
                    on_progress,
                    "planning",
                    "질문을 분석해 필요한 자료를 정하는 중입니다.",
                )
            else:
                self._emit_progress(
                    on_progress,
                    "reviewing_results",
                    "MCP 도구의 답변을 검토해 다음 내용을 정리하는 중입니다.",
                )
            response_tool_names = _response_tool_names(tool_results, historical_tool_names)
            model_started = time.perf_counter()
            try:
                turn = await self._model.create_turn(
                    instructions=build_system_prompt(response_tool_names),
                    messages=messages,
                    tools=tools,
                    model_profile=request.modelProfile,
                    tool_results=tool_results,
                    state=state,
                )
            finally:
                pipeline_metrics["model_ms"] += _elapsed_ms(model_started)
                pipeline_metrics["model_calls"] += 1
            state = turn.state

            if not turn.tool_calls:
                return turn.text

            tool_results = []
            for call in turn.tool_calls:
                prior_calls = tool_call_counts.get(call.name, 0)
                tool_call_counts[call.name] = prior_calls + 1
                self._emit_progress(
                    on_progress,
                    "calling_tool",
                    _tool_progress_message(call.name, repeated=prior_calls > 0),
                    tool=call.name or None,
                )
                tool_started = time.perf_counter()
                try:
                    tool_results.append(
                        await self._execute_tool_call(
                            mcp,
                            call,
                            traces,
                            visualize_result_cache,
                        )
                    )
                finally:
                    pipeline_metrics["mcp_tools_ms"] += _elapsed_ms(tool_started)
                    pipeline_metrics["tool_calls"] += 1

            if tool_results and all(result.is_error for result in tool_results):
                logger.warning(
                    "event=chat.tool_results outcome=failed tools=%s",
                    ",".join(result.name or "unknown" for result in tool_results),
                )
                return _tool_failure_message(tool_results)

            if tool_results and all(_tool_result_has_no_data(result) for result in tool_results):
                logger.info(
                    "event=chat.tool_results outcome=no_results tools=%s",
                    ",".join(result.name or "unknown" for result in tool_results),
                )
                return _tool_no_results_message(tool_results)

        self._emit_progress(
            on_progress,
            "finalizing",
            "확인한 자료를 바탕으로 최종 답변을 정리하는 중입니다.",
        )
        model_started = time.perf_counter()
        try:
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
        finally:
            pipeline_metrics["model_ms"] += _elapsed_ms(model_started)
            pipeline_metrics["model_calls"] += 1
        return final_turn.text

    # 진행 콜백 오류가 실제 채팅 실행에 영향을 주지 않도록 격리해 전달한다.
    @staticmethod
    def _emit_progress(
        callback: ProgressCallback | None,
        stage: ChatProgressStage,
        message: str,
        *,
        tool: str | None = None,
    ) -> None:
        if callback is None:
            return
        try:
            callback(ChatProgress(stage=stage, message=message, tool=tool))
        except Exception:
            logger.warning("event=chat.progress.error", exc_info=True)

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


# 실패한 도구 이름과 반환된 원인을 사용자에게 설명하는 종료 문구를 만든다.
def _tool_failure_message(results: list[ToolResult]) -> str:
    tool_names = list(
        dict.fromkeys(_tool_display_name(result.name) for result in results)
    )
    reasons = list(
        dict.fromkeys(_tool_error_reason(result) for result in results)
    )
    return (
        f"{', '.join(tool_names)} 호출이 실패해 답변에 필요한 자료를 확인하지 못했습니다. "
        f"원인: {'; '.join(reasons)} "
        "확인되지 않은 값은 추측해 답하지 않겠습니다."
    )


# 도구 오류 payload에서 사용자에게 필요한 실패 이유만 추출한다.
def _tool_error_reason(result: ToolResult) -> str:
    detail = _tool_error_detail(result)
    lowered = detail.casefold()
    if "session terminated" in lowered:
        return "MCP 연결 세션이 종료되었습니다."
    if "timed out" in lowered or "timeout" in lowered:
        return "통계 도구가 제한 시간 안에 응답하지 않았습니다."
    if "limit" in lowered and (
        "less than or equal to 20" in lowered
        or "less_than_equal" in lowered
    ):
        return "요청한 검색 결과 개수(limit)가 허용 범위인 20 이하를 벗어났습니다."
    if "validation error" in lowered or "input should be" in lowered:
        return "도구 호출 입력값이 허용 형식이나 범위를 벗어났습니다."
    if not detail:
        return "통계 도구가 오류 결과를 반환했습니다."
    return truncate_text(" ".join(detail.split()), 240)


# 구조화 오류, 일반 error 필드, text content 순서로 원문 오류를 찾는다.
def _tool_error_detail(result: ToolResult) -> str:
    if not isinstance(result.result, dict):
        return str(result.result or "")

    error = result.result.get("error")
    if error:
        return str(error)

    structured = _structured_content_from_result(result.result)
    if isinstance(structured, dict):
        error = structured.get("error") or structured.get("message")
        if error:
            return str(error)

    for item in result.result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            return str(item["text"])
    return ""


# 빈 검색 결과의 검색어·발간연도·식별자를 사용해 답할 수 없는 이유를 설명한다.
def _tool_no_results_message(results: list[ToolResult]) -> str:
    for result in results:
        if not isinstance(result.result, dict):
            continue
        structured = _structured_content_from_result(result.result)
        if not isinstance(structured, dict):
            continue

        if result.name == "search_statistics":
            query = str(structured.get("query") or "").strip()
            publication_year = structured.get("applied_publication_year")
            scope = f"{publication_year}년 발간판에서 " if publication_year else ""
            query_text = f"검색어 '{query}'와 일치하는 " if query else ""
            return (
                f"{scope}{query_text}통계표 후보가 반환되지 않아 답변에 필요한 자료를 "
                "확인하지 못했습니다. 확인되지 않은 내용은 추측해 답하지 않겠습니다."
            )

        if result.name == "search_contacts":
            stat_id = structured.get("stat_id")
            identifier = f"stat_id {stat_id}에 해당하는 " if stat_id is not None else ""
            return (
                f"{identifier}통계표가 없어 담당 정보를 확인하지 못했습니다. "
                "확인되지 않은 내용은 추측해 답하지 않겠습니다."
            )

        if result.name == "search_tables":
            stat_id = structured.get("stat_id")
            identifier = f"stat_id {stat_id}에 해당하는 " if stat_id is not None else ""
            return (
                f"{identifier}통계표 원문이 없어 답변에 필요한 수치를 확인하지 못했습니다. "
                "확인되지 않은 내용은 추측해 답하지 않겠습니다."
            )

    return (
        "통계 도구가 빈 결과를 반환해 답변에 필요한 자료를 확인하지 못했습니다. "
        "확인되지 않은 내용은 추측해 답하지 않겠습니다."
    )


# 내부 도구 이름을 사용자에게 읽기 쉬운 명칭으로 바꾼다.
def _tool_display_name(tool_name: str) -> str:
    return {
        "search_contacts": "담당 정보 조회 도구",
        "search_statistics": "통계표 검색 도구",
        "search_tables": "통계표 원문 조회 도구",
        "visualize": "시각화 도구",
    }.get(tool_name, "통계 도구")


# 검색 도구가 명시적으로 빈 결과를 반환했는지 판별한다.
def _tool_result_has_no_data(result: ToolResult) -> bool:
    if result.is_error or result.name not in {
        "search_contacts",
        "search_statistics",
        "search_tables",
    }:
        return False
    if not isinstance(result.result, dict):
        return False

    structured = _structured_content_from_result(result.result)
    if not isinstance(structured, dict):
        return False
    if result.name == "search_statistics":
        return structured.get("count") == 0 or structured.get("results") == []
    return structured.get("found") is False


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


# 도구 종류와 반복 여부에 따라 내부 추론을 노출하지 않는 짧은 진행 문구를 만든다.
def _tool_progress_message(tool_name: str, *, repeated: bool) -> str:
    display_name = tool_name or "MCP"
    if repeated:
        return f"{display_name} MCP 도구로 더 정확한 답변을 위해 추가 자료를 탐색하는 중입니다."
    if tool_name == "search_contacts":
        return "search_contacts MCP 도구로 통계표 담당 정보를 확인하는 중입니다."
    if tool_name == "search_statistics":
        return "search_statistics MCP 도구로 관련 통계자료를 찾는 중입니다."
    if tool_name == "search_tables":
        return "search_tables MCP 도구로 통계표 원문을 확인하는 중입니다."
    if tool_name == "visualize":
        return "visualize MCP 도구로 시각화를 준비하는 중입니다."
    return f"{display_name} MCP 도구를 호출하고 호스트의 답변을 기다리는 중입니다."


# 요청 단위 병목 로그에 누적할 지연과 호출 횟수의 초기값을 만든다.
def _new_pipeline_metrics() -> dict[str, int]:
    return {
        "mcp_connect_ms": 0,
        "mcp_discovery_ms": 0,
        "model_ms": 0,
        "mcp_tools_ms": 0,
        "model_calls": 0,
        "tool_calls": 0,
    }


# 각 요청의 누적 구간 중 가장 오래 걸린 병목과 전체 시간을 한 줄로 기록한다.
def _log_pipeline(
    *,
    settings: Settings,
    metrics: dict[str, int],
    total_ms: int,
    outcome: str,
) -> None:
    stage_durations = {
        "mcp_connect": metrics["mcp_connect_ms"],
        "mcp_discovery": metrics["mcp_discovery_ms"],
        "model": metrics["model_ms"],
        "mcp_tools": metrics["mcp_tools_ms"],
    }
    bottleneck = max(stage_durations, key=stage_durations.get)
    logger.info(
        "event=chat.pipeline outcome=%s provider=%s model=%s duration_ms=%s "
        "bottleneck=%s mcp_connect_ms=%s mcp_discovery_ms=%s "
        "model_ms=%s mcp_tools_ms=%s model_calls=%s tool_calls=%s",
        outcome,
        settings.model_provider,
        settings.chat_model,
        total_ms,
        bottleneck,
        metrics["mcp_connect_ms"],
        metrics["mcp_discovery_ms"],
        metrics["model_ms"],
        metrics["mcp_tools_ms"],
        metrics["model_calls"],
        metrics["tool_calls"],
    )


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
