import json

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

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
        x: str | None = None,
        y: str | None = None,
        group: str | None = None,
        top_n: int | None = None,
        total_mode: TotalMode = "auto",
    ) -> CallToolResult:
        table = _fetch_table(stat_id, table_seq)
        if table is None:
            return _error_result("해당 stat_id/table_seq 통계표를 찾지 못했습니다.", stat_id, table_seq)

        spec = build_plot_spec(table, query, chart_type, x, y, group, top_n, total_mode)
        spec["vega_lite"] = build_vega_lite_spec(spec)

        return CallToolResult(
            content=[TextContent(type="text", text=summary_text(spec))],
            structuredContent=spec,
        )
