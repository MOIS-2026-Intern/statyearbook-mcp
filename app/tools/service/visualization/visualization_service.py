# -*- coding: utf-8 -*-
"""통계표 선택부터 Vega-Lite 응답 생성까지의 시각화 유스케이스를 담당한다."""
import json
from typing import Any, Literal

from mcp.types import CallToolResult, TextContent

from app.tools.repository.visualization_repository import VisualizationRepository
from app.tools.service.table_service import merge_bodies
from app.tools.service.visualization.chart_spec_builder import (
    ChartType,
    SortOrder,
    build_plot_spec,
)
from app.tools.service.visualization.multi_table_spec_builder import (
    MAX_SOURCES,
    build_multi_source_spec,
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
    def error_result(message: str, stat_id: int | None, table_seq: int) -> CallToolResult:
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

    # 캐시 핸들 또는 stat_id로 원본 표 하나를 가져온다.
    # 핸들은 재조회를 아끼는 수단일 뿐이므로, 못 쓰게 됐어도 stat_id로 다시 읽어 요청을 살린다.
    def resolve_table(
        self, stat_id: int, table_handle: str | None,
    ) -> tuple[dict | None, str | None, str | None]:
        note: str | None = None
        if table_handle:
            table = get_cached_table(table_handle)
            if table is None:
                note = (
                    "직전 요청에서 받은 table_handle이 이번 세션에 없어 stat_id로 표를 다시 읽었습니다. "
                    "table_handle은 같은 요청 안에서만 쓸 수 있습니다."
                )
            elif table["stat_id"] != stat_id:
                note = "table_handle이 가리키는 표가 stat_id와 달라 stat_id로 표를 다시 읽었습니다."
            else:
                return table, None, None

        table = self.fetch_table(stat_id)
        if table is None:
            return None, f"stat_id {stat_id} 통계표를 찾지 못했습니다.", note
        return table, None, note

    # 완성된 spec에 Vega-Lite 명세를 붙여 MCP 응답으로 감싼다.
    @staticmethod
    def _tool_result(spec: dict[str, Any]) -> CallToolResult:
        spec["vega_lite"] = build_vega_lite_spec(spec)
        return CallToolResult(
            content=[TextContent(type="text", text=summary_text(spec))],
            structuredContent=spec,
        )

    # 여러 통계표의 지표를 공통 항목으로 맞춰 하나의 차트로 만든다.
    def visualize_sources(
        self,
        *,
        sources: list[dict],
        query: str | None,
        title: str | None,
        chart_type: ChartType,
        top_n: int | None,
        total_mode: TotalMode,
        year: int | None,
        orientation: Literal["vertical", "horizontal"],
        sort_order: SortOrder,
        derive: dict | None = None,
    ) -> CallToolResult:
        if len(sources) > MAX_SOURCES:
            return self.error_result(
                f"한 번에 함께 그릴 수 있는 표는 최대 {MAX_SOURCES}개입니다.",
                sources[0].get("stat_id"),
                1,
            )

        resolved: list[dict] = []
        notes: list[str] = []
        for source in sources:
            stat_id = source.get("stat_id")
            if stat_id is None:
                return self.error_result("sources의 각 항목에는 stat_id가 필요합니다.", None, 1)
            table, error, note = self.resolve_table(stat_id, source.get("table_handle"))
            if note:
                notes.append(note)
            if table is None:
                return self.error_result(error or "통계표를 찾지 못했습니다.", stat_id, 1)
            resolved.append({"table": table, "request": source})

        spec = build_multi_source_spec(
            resolved,
            query=query,
            chart_type=chart_type,
            top_n=top_n,
            total_mode=total_mode,
            year=year,
            title=title,
            orientation=orientation,
            sort_order=sort_order,
            derive=derive,
        )
        # 표마다 같은 안내가 붙으므로 한 번만 남긴다.
        spec["warnings"] = list(dict.fromkeys(notes)) + spec["warnings"]
        return self._tool_result(spec)

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
        derive: dict | None = None,
    ) -> CallToolResult:
        table, error, note = self.resolve_table(stat_id, table_handle)
        if table is None:
            return self.error_result(
                error or "해당 stat_id 통계표를 찾지 못했습니다.", stat_id, table_seq,
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
            derive=derive,
        )
        if note:
            spec["warnings"] = [note, *spec["warnings"]]
        spec["request"]["table_handle"] = table_handle
        spec["request"]["table_source"] = (
            "database" if note or not table_handle else "search_tables_cache"
        )
        spec["request"]["orientation"] = orientation
        spec["chart"]["orientation"] = orientation
        return self._tool_result(spec)
