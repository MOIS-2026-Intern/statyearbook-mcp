# -*- coding: utf-8 -*-
"""통계표 선택부터 Vega-Lite 응답 생성까지의 시각화 유스케이스를 담당한다."""
import json
from typing import Literal

from mcp.types import CallToolResult, TextContent

from app.tools.repository.visualization_repository import VisualizationRepository
from app.tools.service.table_service import merge_bodies
from app.tools.service.visualization.chart_spec_builder import (
    ChartType,
    SortOrder,
    build_plot_spec,
)
from app.tools.service.visualization.table_interpreter import TotalMode
from app.tools.service.visualization.vega_lite_renderer import (
    build_vega_lite_spec,
    summary_text,
)
from app.table_cache import get_cached_table


class VisualizationService:
    def __init__(self, repository: VisualizationRepository | None = None):
        self._repository = repository or VisualizationRepository()

    # DB 표 조각을 시각화가 사용하는 하나의 논리 표로 합친다.
    def fetch_table(self, stat_id: int) -> dict | None:
        rows = self._repository.select_table_rows(stat_id)
        if not rows:
            return None
        bodies = [
            json.loads(row["body"]) if isinstance(row["body"], str) else row["body"]
            for row in rows
        ]
        table = rows[0]
        table["body"] = bodies[0] if len(bodies) == 1 else merge_bodies(bodies)
        return table

    # MCP 오류 응답 객체를 만든다.
    @staticmethod
    def error_result(message: str, stat_id: int, table_seq: int) -> CallToolResult:
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

    # 선택 조건을 검증하고 프론트엔드용 Vega-Lite 응답을 만든다.
    def visualize(
        self,
        *,
        stat_id: int,
        table_seq: int,
        table_handle: str | None,
        query: str | None,
        title: str | None,
        chart_type: ChartType,
        x: str | None,
        y: str | None,
        group: str | None,
        top_n: int | None,
        total_mode: TotalMode,
        year: int | None,
        city: str | None,
        column_family: str | None,
        filters: list[dict] | None,
        metrics: list[dict] | None,
        orientation: Literal["vertical", "horizontal"],
        sort_order: SortOrder,
    ) -> CallToolResult:
        if table_handle:
            table = get_cached_table(table_handle)
            if table is None:
                return self.error_result(
                    "table_handle이 만료되었거나 현재 MCP 세션에 없습니다. search_tables를 다시 호출해 주세요.",
                    stat_id,
                    table_seq,
                )
            if table["stat_id"] != stat_id:
                return self.error_result(
                    "table_handle의 stat_id가 요청값과 일치하지 않습니다.",
                    stat_id,
                    table_seq,
                )
        else:
            table = self.fetch_table(stat_id)
            if table is None:
                return self.error_result(
                    "해당 stat_id 통계표를 찾지 못했습니다.", stat_id, table_seq
                )

        spec = build_plot_spec(
            table,
            query,
            chart_type,
            x,
            y,
            group,
            top_n,
            total_mode,
            year=year,
            city=city,
            column_family_name=column_family,
            filters=filters,
            metrics=metrics,
            title=title,
            sort_order=sort_order,
        )
        spec["request"]["table_handle"] = table_handle
        spec["request"]["table_source"] = (
            "search_tables_cache" if table_handle else "database"
        )
        spec["request"]["orientation"] = orientation
        spec["chart"]["orientation"] = orientation
        spec["vega_lite"] = build_vega_lite_spec(spec)
        return CallToolResult(
            content=[TextContent(type="text", text=summary_text(spec))],
            structuredContent=spec,
        )
