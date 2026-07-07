# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.config import Settings
from backend.gateways.mcp_gateway import McpGateway, describe_tool, openai_tool_from_mcp
from backend.gateways.openai_gateway import OpenAIGateway
from backend.models.chat import ChatMessage, ChatRequest, ChatResponse, McpTrace
from backend.prompts import SYSTEM_PROMPT
from backend.serializers.mcp_result_serializer import (
    json_dumps,
    parse_json_object,
    to_jsonable,
    truncate_jsonable,
    truncate_text,
)


class ChatService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._openai = OpenAIGateway(settings)

    async def respond(self, request: ChatRequest) -> ChatResponse:
        traces: list[McpTrace] = []
        input_items: list[Any] = [{"role": "user", "content": request.message}]

        async with McpGateway(self._settings) as mcp:
            mcp_tools = await self._list_tools(mcp, traces)
            openai_tools = [openai_tool_from_mcp(tool) for tool in mcp_tools]

            final_text = await self._run_model_loop(
                request=request,
                mcp=mcp,
                traces=traces,
                input_items=input_items,
                openai_tools=openai_tools,
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

    async def _list_tools(self, mcp: McpGateway, traces: list[McpTrace]) -> list[Any]:
        started = time.perf_counter()
        trace_id = str(uuid4())
        try:
            tools = await mcp.list_tools()
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
        input_items: list[Any],
        openai_tools: list[dict[str, Any]],
    ) -> str:
        tools_for_turn = openai_tools

        for _ in range(self._settings.max_tool_rounds):
            response = await self._openai.create_response(
                instructions=SYSTEM_PROMPT,
                input_items=input_items,
                tools=tools_for_turn,
                model_profile=request.modelProfile,
            )
            input_items.extend(to_jsonable(getattr(response, "output", [])))

            function_calls = _function_calls(response)
            if not function_calls:
                return _response_text(response)

            for call in function_calls:
                tool_output = await self._execute_tool_call(mcp, call, traces)
                input_items.append(tool_output)

        final_response = await self._openai.create_response(
            instructions=(
                SYSTEM_PROMPT
                + "\n\n도구 호출 횟수 제한에 도달했습니다. 지금까지 받은 도구 결과만 사용해 답하세요."
            ),
            input_items=input_items,
            tools=[],
            model_profile=request.modelProfile,
        )
        return _response_text(final_response)

    async def _execute_tool_call(self, mcp: McpGateway, call: Any, traces: list[McpTrace]) -> dict[str, Any]:
        call_id = _get(call, "call_id")
        tool_name = _get(call, "name")
        raw_arguments = _get(call, "arguments")
        trace_id = str(uuid4())
        started = time.perf_counter()

        try:
            arguments = parse_json_object(raw_arguments)
            if self._settings.force_visualize_without_inline_image and tool_name == "visualize":
                arguments["include_image"] = False

            result = await mcp.call_tool(tool_name, arguments)
            model_result = truncate_jsonable(result, self._settings.tool_output_max_chars)
            status = "error" if result.get("isError") else "success"

            traces.append(
                McpTrace(
                    id=trace_id,
                    kind="tool_call",
                    status=status,
                    title=f"{tool_name} 호출",
                    timestamp=_now_iso(),
                    server=self._settings.mcp_server_label,
                    tool=tool_name,
                    summary=_tool_summary(result),
                    durationMs=_elapsed_ms(started),
                    request={"arguments": arguments},
                    response=truncate_jsonable(result, self._settings.tool_output_max_chars),
                )
            )
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json_dumps(model_result),
            }
        except Exception as exc:
            error_payload = {"error": str(exc), "tool": tool_name, "arguments": raw_arguments}
            traces.append(
                McpTrace(
                    id=trace_id,
                    kind="error",
                    status="error",
                    title=f"{tool_name or 'unknown'} 호출 실패",
                    timestamp=_now_iso(),
                    server=self._settings.mcp_server_label,
                    tool=tool_name,
                    summary=str(exc),
                    durationMs=_elapsed_ms(started),
                    request={"arguments": raw_arguments},
                    response=error_payload,
                )
            )
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json_dumps(error_payload),
            }

    def _mcp_connection_info(self) -> dict[str, Any]:
        return {
            "transport": "stdio",
            "command": self._settings.mcp_command,
            "args": self._settings.mcp_args,
            "cwd": self._settings.mcp_cwd,
        }


def _function_calls(response: Any) -> list[Any]:
    return [item for item in getattr(response, "output", []) if _get(item, "type") == "function_call"]


def _response_text(response: Any) -> str:
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
    return "응답을 생성했지만 표시할 텍스트를 찾지 못했습니다."


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


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
