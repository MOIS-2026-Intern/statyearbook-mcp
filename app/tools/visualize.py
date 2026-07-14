import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from app.db import connect
from app.table_cache import get_cached_table
from app.tool_descriptions import (
    METRIC_SELECTION_FIELDS,
    SELECTION_FILTER_FIELDS,
    VISUALIZE,
    VISUALIZE_FIELDS,
)
from app.tools.visualize_service.chart_spec_builder import ChartType, build_plot_spec
from app.tools.visualize_service.table_interpreter import TotalMode
from app.tools.visualize_service.vega_lite_renderer import build_vega_lite_spec, summary_text


TABLE_SQL = """
    SELECT s.stat_id, s.ref_id, s.title_ko, s.title_en,
           s.unit, s.base_date, s.year AS publication_year,
           t.seq AS table_seq, t.caption, t.n_rows, t.n_cols,
           t.body, t.table_md
    FROM statistics s
    JOIN stat_tables t ON t.stat_id = s.stat_id
    WHERE s.stat_id = %s AND t.seq = %s
"""


class SelectionFilter(BaseModel):
    column: str = Field(description=SELECTION_FILTER_FIELDS["column"])
    value: str = Field(description=SELECTION_FILTER_FIELDS["value"])


class MetricSelection(BaseModel):
    column: str = Field(description=METRIC_SELECTION_FIELDS["column"])
    label: str | None = Field(default=None, description=METRIC_SELECTION_FIELDS["label"])
    unit: str | None = Field(default=None, description=METRIC_SELECTION_FIELDS["unit"])


# 시각화 대상 통계표를 DB에서 가져온다.
def _fetch_table(stat_id: int, table_seq: int) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(TABLE_SQL, (stat_id, table_seq))
        row = cur.fetchone()

    if row and isinstance(row.get("body"), str):
        row["body"] = json.loads(row["body"])
    return row


# MCP 오류 응답 객체를 만든다.
def _error_result(message: str, stat_id: int, table_seq: int) -> CallToolResult:
    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=message)],
        structuredContent={
            "ok": False,
            "stat_id": stat_id,
            "table_seq": table_seq,
            "error": message,
        },
    )


# visualize MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # 통계표를 프론트엔드 렌더링용 Vega-Lite spec으로 반환한다.
    @mcp.tool(description=VISUALIZE)
    def visualize(
        stat_id: int,
        table_seq: int = 1,
        table_handle: Annotated[
            str | None,
            Field(description=VISUALIZE_FIELDS["table_handle"]),
        ] = None,
        query: str | None = None,
        title: Annotated[
            str | None,
            Field(description=VISUALIZE_FIELDS["title"], min_length=1, max_length=80),
        ] = None,
        chart_type: ChartType = "auto",
        x: Annotated[str | None, Field(description=VISUALIZE_FIELDS["x"])] = None,
        y: Annotated[str | None, Field(description=VISUALIZE_FIELDS["y"])] = None,
        group: str | None = None,
        top_n: int | None = None,
        total_mode: Annotated[
            TotalMode,
            Field(description=VISUALIZE_FIELDS["total_mode"]),
        ] = "auto",
        year: Annotated[
            int | None,
            Field(description=VISUALIZE_FIELDS["year"]),
        ] = None,
        city: Annotated[
            str | None,
            Field(description=VISUALIZE_FIELDS["city"]),
        ] = None,
        column_family: Annotated[
            str | None,
            Field(description=VISUALIZE_FIELDS["column_family"]),
        ] = None,
        filters: Annotated[
            list[SelectionFilter] | None,
            Field(description=VISUALIZE_FIELDS["filters"]),
        ] = None,
        metrics: Annotated[
            list[MetricSelection] | None,
            Field(description=VISUALIZE_FIELDS["metrics"]),
        ] = None,
    ) -> CallToolResult:
        table = get_cached_table(table_handle) if table_handle else _fetch_table(stat_id, table_seq)
        if table is None:
            message = (
                "table_handle이 만료되었거나 현재 MCP 세션에 없습니다. search_tables를 다시 호출해 주세요."
                if table_handle
                else "해당 stat_id/table_seq 통계표를 찾지 못했습니다."
            )
            return _error_result(message, stat_id, table_seq)
        if table["stat_id"] != stat_id or table["table_seq"] != table_seq:
            return _error_result(
                "table_handle의 stat_id/table_seq가 요청값과 일치하지 않습니다.", stat_id, table_seq,
            )

        spec = build_plot_spec(
            table, query, chart_type, x, y, group, top_n, total_mode,
            year=year, city=city, column_family_name=column_family,
            filters=[item.model_dump() for item in filters] if filters is not None else None,
            metrics=[item.model_dump() for item in metrics] if metrics is not None else None,
            title=title,
        )
        spec["request"]["table_handle"] = table_handle
        spec["request"]["table_source"] = "search_tables_cache" if table_handle else "database"
        spec["vega_lite"] = build_vega_lite_spec(spec)

        return CallToolResult(
            content=[TextContent(type="text", text=summary_text(spec))],
            structuredContent=spec,
        )
