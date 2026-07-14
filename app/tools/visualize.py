import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from app.db import connect
from app.table_cache import get_cached_table
from app.tool_descriptions import VISUALIZE
from app.tools.visualize_service.chart_spec_builder import ChartType, build_plot_spec
from app.tools.visualize_service.table_interpreter import TotalMode
from app.tools.visualize_service.vega_lite_renderer import build_vega_lite_spec, summary_text


TABLE_SQL = """
    SELECT s.stat_id, s.ref_id, s.year, s.title_ko, s.title_en,
           s.unit, s.base_date,
           t.seq AS table_seq, t.caption, t.n_rows, t.n_cols,
           t.body, t.table_md
    FROM statistics s
    JOIN stat_tables t ON t.stat_id = s.stat_id
    WHERE s.stat_id = %s AND t.seq = %s
"""


class SelectionFilter(BaseModel):
    column: str = Field(description="search_tables 표에 나온 정확한 필터 컬럼명")
    value: str = Field(description="search_tables 표에 나온 정확한 셀 값")


class MetricSelection(BaseModel):
    column: str = Field(description="search_tables 표에 나온 정확한 숫자 컬럼명")
    label: str | None = Field(default=None, description="차트에 표시할 짧은 지표명")
    unit: str | None = Field(default=None, description="표 메타데이터와 일치하는 지표 단위")


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
            Field(description="직전 search_tables가 해당 표에 발급한 캐시 핸들"),
        ] = None,
        query: str | None = None,
        chart_type: ChartType = "auto",
        x: Annotated[str | None, Field(description="실제 x축 컬럼명 또는 연도·분류 같은 역할")] = None,
        y: Annotated[str | None, Field(description="실제 y축 숫자 컬럼명 또는 값·정원 같은 역할")] = None,
        group: str | None = None,
        top_n: int | None = None,
        total_mode: TotalMode = "auto",
        year: Annotated[
            int | None,
            Field(description="사용자가 특정한 데이터 행의 연도. 날짜가 있으면 연도 정수만 추출"),
        ] = None,
        city: Annotated[
            str | None,
            Field(description="사용자가 특정한 도시·시도·지역명. 표의 실제 행 값과 서버에서 대조"),
        ] = None,
        column_family: Annotated[
            str | None,
            Field(description="'상위 헤더_하위 헤더'로 평탄화된 컬럼 중 요청한 상위 헤더명"),
        ] = None,
        filters: Annotated[
            list[SelectionFilter] | None,
            Field(description="원본 행을 고르는 정확한 컬럼-값 조건. search_tables 값을 그대로 사용"),
        ] = None,
        metrics: Annotated[
            list[MetricSelection] | None,
            Field(description="시각화할 정확한 숫자 컬럼 목록. 여러 지표 비교 시 모두 전달"),
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
        )
        spec["request"]["table_handle"] = table_handle
        spec["request"]["table_source"] = "search_tables_cache" if table_handle else "database"
        spec["vega_lite"] = build_vega_lite_spec(spec)

        return CallToolResult(
            content=[TextContent(type="text", text=summary_text(spec))],
            structuredContent=spec,
        )
