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
from backend.prompts import SYSTEM_PROMPT
from backend.serializers.mcp_result_serializer import (
    json_dumps,
    truncate_jsonable,
    truncate_text,
)


class ChatService:
    def __init__(self, settings: Settings, model_gateway: ModelGateway | None = None):
        self._settings = settings
        self._model = model_gateway or create_model_gateway(settings)

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

        for _ in range(self._settings.max_tool_rounds):
            turn = await self._model.create_turn(
                instructions=SYSTEM_PROMPT,
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
                tool_results.append(await self._execute_tool_call(mcp, call, traces))

        final_turn = await self._model.create_turn(
            instructions=(
                SYSTEM_PROMPT
                + "\n\n도구 호출 횟수 제한에 도달했습니다. 지금까지 받은 도구 결과만 사용해 답하세요."
            ),
            messages=messages,
            tools=[],
            model_profile=request.modelProfile,
            tool_results=tool_results,
            state=state,
        )
        return final_turn.text

    async def _execute_tool_call(self, mcp: McpGateway, call: ToolCall, traces: list[McpTrace]) -> ToolResult:
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
            result = await mcp.call_tool(call.name, arguments)
            model_result = truncate_jsonable(result, self._settings.tool_output_max_chars)
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
                    summary=_tool_summary(result),
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

    def _mcp_connection_info(self) -> dict[str, Any]:
        return {
            "transport": "stdio",
            "command": self._settings.mcp_command,
            "args": self._settings.mcp_args,
            "cwd": self._settings.mcp_cwd,
        }


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
            "response": trace.response,
        }
        context.append({key: value for key, value in payload.items() if value is not None})
    return context


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
