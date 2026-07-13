import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from app.db import connect
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
    ) -> CallToolResult:
        table = _fetch_table(stat_id, table_seq)
        if table is None:
            return _error_result("해당 stat_id/table_seq 통계표를 찾지 못했습니다.", stat_id, table_seq)

        spec = build_plot_spec(
            table, query, chart_type, x, y, group, top_n, total_mode,
            year=year, city=city, column_family_name=column_family,
        )
        spec["vega_lite"] = build_vega_lite_spec(spec)

        return CallToolResult(
            content=[TextContent(type="text", text=summary_text(spec))],
            structuredContent=spec,
        )
