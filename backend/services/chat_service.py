# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.config import Settings
from backend.gateways.mcp_gateway import McpGateway, describe_tool
from backend.gateways.model_gateway import ModelGateway, create_model_gateway
from backend.models.chat import ChatMessage, ChatRequest, ChatResponse, McpTrace
from backend.models.tooling import ModelMessage, ToolCall, ToolResult, ToolSpec
from backend.prompts import SEARCH_TABLES_REPAIR_PROMPT, build_system_prompt
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
        historical_tool_results = _historical_tool_results(request)
        visualize_result_cache: dict[str, dict[str, Any]] = {}

        for _ in range(self._settings.max_tool_rounds):
            response_context = _response_context_results(tool_results, historical_tool_results)
            turn = await self._model.create_turn(
                instructions=build_system_prompt(_successful_tool_names(response_context)),
                messages=messages,
                tools=tools,
                model_profile=request.modelProfile,
                tool_results=tool_results,
                state=state,
            )
            state = turn.state

            if not turn.tool_calls:
                answer = turn.text
                answer_state = state
                for _ in range(2):
                    violations = _search_tables_answer_violations(
                        answer,
                        _follow_up_query_text(request),
                        response_context,
                    )
                    if not violations:
                        return answer
                    repair_turn = await self._model.create_turn(
                        instructions=(
                            build_system_prompt(_successful_tool_names(response_context))
                            + "\n\n"
                            + SEARCH_TABLES_REPAIR_PROMPT
                            + "\n위반 항목: "
                            + ", ".join(violations)
                            + "\n\n[재작성에 사용할 search_tables 결과]\n"
                            + _search_tables_context_text(response_context)
                        ),
                        messages=messages,
                        tools=[],
                        model_profile=request.modelProfile,
                        tool_results=[],
                        state=answer_state,
                    )
                    answer = repair_turn.text
                    answer_state = repair_turn.state
                return _fallback_search_tables_answer(request, response_context) or answer

            tool_results = []
            for call in turn.tool_calls:
                tool_results.append(await self._execute_tool_call(mcp, call, traces, visualize_result_cache))

        final_turn = await self._model.create_turn(
            instructions=(
                build_system_prompt(
                    _successful_tool_names(_response_context_results(tool_results, historical_tool_results))
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

    def _mcp_connection_info(self) -> dict[str, Any]:
        return {
            "transport": "stdio",
            "command": self._settings.mcp_command,
            "args": self._settings.mcp_args,
            "cwd": self._settings.mcp_cwd,
        }


def _successful_tool_names(results: list[ToolResult]) -> tuple[str, ...]:
    return tuple(result.name for result in results if not result.is_error)


def _response_context_results(
    current_results: list[ToolResult],
    historical_results: list[ToolResult],
) -> list[ToolResult]:
    """새 도구 결과가 있으면 과거 표 컨텍스트보다 우선한다."""
    return current_results or historical_results


def _historical_tool_results(request: ChatRequest) -> list[ToolResult]:
    """가장 최근 도구 사용 assistant 턴을 후속 질문의 응답 컨텍스트로 복원한다."""
    trace_by_id = {trace.id: trace for trace in request.traces}
    for message in reversed(request.history):
        if message.role != "assistant":
            continue

        results: list[ToolResult] = []
        for trace_id in message.traceIds or []:
            trace = trace_by_id.get(trace_id)
            if (
                trace is None
                or trace.kind != "tool_call"
                or trace.status != "success"
                or not trace.tool
                or not isinstance(trace.response, dict)
            ):
                continue
            results.append(
                ToolResult(
                    call_id=trace.id,
                    name=trace.tool,
                    result=_model_result_for_tool(trace.tool, trace.response),
                    is_error=False,
                )
            )
        if results:
            return results
    return []


def _search_tables_answer_violations(
    text: str,
    user_message: str,
    results: list[ToolResult],
) -> list[str]:
    if "search_tables" not in _successful_tool_names(results):
        return []

    metadata_only = bool(re.search(r"출처|주석|각주|담당자|연락처|전화번호", user_message)) and not bool(
        re.search(r"수치|몇\s*(명|개|건)|현황|내역|항목|표|원문|연도|합계|소계|등급", user_message)
    )
    violations: list[str] = []
    if not metadata_only and not _has_markdown_table(text):
        violations.append("Markdown 표 누락")
    if re.search(r"\b(?:title_ko|base_date|unit)\s*=", text):
        violations.append("원시 필드명 노출")
    if re.search(r"원하시면|필요하시면|알려\s*주세요", text):
        violations.append("불필요한 후속 제안")
    if re.search(r"\bGR\s*\d|Senior Civil Service|Head Office|Overseas Missions|\bTotal\b", text, re.I):
        violations.append("영문 병기 잔존")
    if _search_tables_unit(results) == "명" and re.search(r"(?:기관|공관|본부|외교원)\s*수(?:\b|\()", text):
        violations.append("인원 단위 표현 오류")
    unit = _search_tables_unit(results)
    if unit and text.count(f"({unit})") > 1:
        violations.append("표 머리글 단위 반복")
    if _has_wide_single_record_table(text):
        violations.append("단일 연도 가로형 표")
    if re.search(r"^\|.*_", text, re.MULTILINE):
        violations.append("평탄화 헤더 흔적")
    if _has_unrequested_family_items(text, user_message, results):
        violations.append("요청 밖 항목 포함")
    return violations


def _has_markdown_table(text: str) -> bool:
    rows = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return False
    return any(re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", row) for row in rows)


def _has_wide_single_record_table(text: str) -> bool:
    rows = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    for index, row in enumerate(rows):
        if not re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", row):
            continue
        header = rows[index - 1] if index else ""
        data_rows = rows[index + 1 :]
        column_count = max(0, header.count("|") - 1)
        return column_count > 4 and len(data_rows) == 1
    return False


def _has_unrequested_family_items(
    text: str,
    query_text: str,
    results: list[ToolResult],
) -> bool:
    structured = _search_tables_structured_content(results)
    if structured is None:
        return False
    tables = structured.get("tables")
    if not isinstance(tables, list):
        return False
    source_md = next(
        (str(table["table_md"]) for table in tables if isinstance(table, dict) and table.get("table_md")),
        None,
    )
    source_table = _parse_markdown_table(source_md) if source_md else None
    answer_table = _parse_markdown_table(text)
    if source_table is None or answer_table is None:
        return False

    source_headers, _ = source_table
    indexes, family_label = _matching_column_family(source_headers, query_text)
    if not indexes or not family_label:
        return False
    expected = {
        _compact_label(_display_column_label(source_headers[index], family_label))
        for index in indexes
    }
    _, answer_records = answer_table
    for record in answer_records:
        if not record:
            continue
        label = _compact_label(record[0])
        if label in expected:
            continue
        without_family = label.removeprefix(_compact_label(family_label))
        if without_family in expected:
            continue
        return True
    return False


def _compact_label(value: str) -> str:
    return re.sub(r"[^가-힣0-9·･]", "", value).replace("･", "·")


def _search_tables_unit(results: list[ToolResult]) -> str | None:
    structured = _search_tables_structured_content(results)
    if structured is not None and structured.get("unit"):
        return str(structured["unit"])
    return None


def _search_tables_context_text(results: list[ToolResult]) -> str:
    for result in results:
        if result.name != "search_tables" or result.is_error or not isinstance(result.result, dict):
            continue
        structured = result.result.get("structuredContent")
        if isinstance(structured, dict):
            return truncate_text(json_dumps(structured), 20_000)
    return "사용 가능한 search_tables 결과가 없습니다."


def _fallback_search_tables_answer(request: ChatRequest, results: list[ToolResult]) -> str | None:
    """모델 재작성도 실패하면 이전 원문 표에서 요청 연도·항목군을 직접 Markdown으로 만든다."""
    structured = _search_tables_structured_content(results)
    if structured is None:
        return None
    tables = structured.get("tables")
    if not isinstance(tables, list):
        return None

    table_md = next(
        (
            str(table["table_md"])
            for table in tables
            if isinstance(table, dict) and table.get("table_md")
        ),
        None,
    )
    parsed = _parse_markdown_table(table_md) if table_md else None
    if parsed is None:
        return None
    headers, records = parsed

    query_text = _follow_up_query_text(request)
    year = _requested_year(query_text)
    record = next(
        (row for row in records if year and any(cell.strip() == year for cell in row)),
        records[-1] if len(records) == 1 else None,
    )
    if record is None:
        return _table_with_metadata(table_md, structured)

    family_indexes, family_label = _matching_column_family(headers, query_text)
    year_indexes = {
        index
        for index, header in enumerate(headers)
        if "연도" in _korean_label(header) or (index < len(record) and record[index].strip() == year)
    }
    selected_indexes = family_indexes or [
        index for index in range(min(len(headers), len(record))) if index not in year_indexes
    ]

    items: list[tuple[str, str]] = []
    for index in selected_indexes:
        if index >= len(record) or index in year_indexes:
            continue
        label = _display_column_label(headers[index], family_label)
        value = record[index].strip()
        if label and value:
            items.append((label, value))
    if not items:
        return _table_with_metadata(table_md, structured)

    unit = str(structured.get("unit") or "").strip()
    value_header = f"인원({unit})" if unit == "명" else f"값({unit})" if unit else "값"
    lines = [f"{year + '년 ' if year else ''}{family_label or '요청 항목'} 현황입니다.", ""]
    lines.extend([f"| 항목 | {value_header} |", "|---|---:|"])
    lines.extend(f"| {label} | {value} |" for label, value in items)
    lines.extend(["", _metadata_line(structured)])
    return "\n".join(lines)


def _search_tables_structured_content(results: list[ToolResult]) -> dict[str, Any] | None:
    for result in results:
        if result.name != "search_tables" or result.is_error or not isinstance(result.result, dict):
            continue
        structured = _structured_content_from_result(result.result)
        if structured is not None:
            return structured
    return None


def _parse_markdown_table(table_md: str) -> tuple[list[str], list[list[str]]] | None:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in table_md.splitlines()
        if line.strip().startswith("|")
    ]
    if len(rows) < 3:
        return None
    separator_index = next(
        (index for index, row in enumerate(rows) if row and all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)),
        None,
    )
    if separator_index is None or separator_index == 0:
        return None
    return rows[separator_index - 1], rows[separator_index + 1 :]


def _follow_up_query_text(request: ChatRequest) -> str:
    user_messages = [message.content for message in request.history if message.role == "user"]
    return " ".join([*user_messages, request.message])


def _requested_year(query_text: str) -> str | None:
    matches = re.findall(r"(?:19|20)\d{2}", query_text)
    return matches[-1] if matches else None


def _matching_column_family(headers: list[str], query_text: str) -> tuple[list[int], str | None]:
    compact_query = re.sub(r"\s+", "", query_text)
    families: dict[str, list[int]] = {}
    labels: dict[str, str] = {}
    for index, header in enumerate(headers):
        if "_" not in header:
            continue
        family = _korean_label(header.split("_", 1)[0])
        compact_family = re.sub(r"\s+", "", family)
        if not compact_family:
            continue
        families.setdefault(compact_family, []).append(index)
        labels[compact_family] = compact_family

    matches = [family for family in families if family in compact_query]
    if not matches:
        return [], None
    family = max(matches, key=len)
    return families[family], labels[family]


def _display_column_label(header: str, family_label: str | None) -> str:
    leaf = header.rsplit("_", 1)[-1]
    label = re.sub(r"\s+", "", _korean_label(leaf)).replace("･", "·")
    if label == "소계" and family_label:
        return f"{family_label} 소계"
    return label


def _korean_label(value: str) -> str:
    korean_part = re.split(r"[A-Za-z]", value, maxsplit=1)[0]
    return re.sub(r"[^가-힣0-9·･\s]", "", korean_part).strip()


def _table_with_metadata(table_md: str, structured: dict[str, Any]) -> str:
    return f"{table_md}\n\n{_metadata_line(structured)}"


def _metadata_line(structured: dict[str, Any]) -> str:
    return (
        f"사용 표: **{structured.get('title_ko') or '-'}** "
        f"(stat_id: {structured.get('stat_id') or '-'}) · "
        f"기준일: **{structured.get('base_date') or '-'}** · "
        f"단위: **{structured.get('unit') or '-'}**"
    )


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


def _select_keys(value: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in keys if value.get(key) is not None}


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
            "response": (
                _model_result_for_tool(trace.tool, trace.response)
                if isinstance(trace.response, dict)
                else trace.response
            ),
        }
        context.append({key: value for key, value in payload.items() if value is not None})
    return context


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
