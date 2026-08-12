from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.tools.service.visualization.chart_spec_builder import ChartType, SortOrder
from app.tools.service.visualization.table_interpreter import TotalMode
from app.tools.service.visualization.visualization_service import VisualizationService
from app.tool_descriptions import (
    METRIC_SELECTION_FIELDS,
    SELECTION_FILTER_FIELDS,
    SERIES_SOURCE_FIELDS,
    VISUALIZE,
    VISUALIZE_FIELDS,
)


VISUALIZATION_SERVICE = VisualizationService()


class SelectionFilter(BaseModel):
    column: str = Field(description=SELECTION_FILTER_FIELDS["column"])
    value: str = Field(description=SELECTION_FILTER_FIELDS["value"])


class MetricSelection(BaseModel):
    column: str = Field(description=METRIC_SELECTION_FIELDS["column"])
    label: str | None = Field(default=None, description=METRIC_SELECTION_FIELDS["label"])
    unit: str | None = Field(default=None, description=METRIC_SELECTION_FIELDS["unit"])


class SeriesSource(BaseModel):
    stat_id: int = Field(description=SERIES_SOURCE_FIELDS["stat_id"])
    table_handle: str | None = Field(
        default=None, description=SERIES_SOURCE_FIELDS["table_handle"]
    )
    label: str | None = Field(default=None, description=SERIES_SOURCE_FIELDS["label"])
    key: str | None = Field(default=None, description=SERIES_SOURCE_FIELDS["key"])
    value: str | None = Field(default=None, description=SERIES_SOURCE_FIELDS["value"])
    unit: str | None = Field(default=None, description=SERIES_SOURCE_FIELDS["unit"])
    year: int | None = Field(default=None, description=SERIES_SOURCE_FIELDS["year"])
    filters: list[SelectionFilter] | None = Field(
        default=None, description=SERIES_SOURCE_FIELDS["filters"]
    )


# visualize MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # 통계표를 프론트엔드 렌더링용 Vega-Lite spec으로 반환한다.
    @mcp.tool(description=VISUALIZE)
    def visualize(
        stat_id: Annotated[
            int | None,
            Field(description=VISUALIZE_FIELDS["stat_id"]),
        ] = None,
        sources: Annotated[
            list[SeriesSource] | None,
            Field(description=VISUALIZE_FIELDS["sources"]),
        ] = None,
        table_seq: Annotated[
            int,
            Field(description=VISUALIZE_FIELDS["table_seq"]),
        ] = 1,
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
        top_n: Annotated[int | None, Field(description=VISUALIZE_FIELDS["top_n"])] = None,
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
        orientation: Annotated[
            Literal["vertical", "horizontal"],
            Field(description=VISUALIZE_FIELDS["orientation"]),
        ] = "vertical",
        sort_order: Annotated[
            SortOrder,
            Field(description=VISUALIZE_FIELDS["sort_order"]),
        ] = "auto",
    ):
        selected_sources = [item.model_dump() for item in sources] if sources else []
        # 표를 둘 이상 받은 요청만 공통 항목으로 맞춰 한 차트에 겹친다.
        if len(selected_sources) > 1:
            return VISUALIZATION_SERVICE.visualize_sources(
                sources=selected_sources,
                query=query,
                title=title,
                chart_type=chart_type,
                top_n=top_n,
                total_mode=total_mode,
                year=year,
                orientation=orientation,
                sort_order=sort_order,
            )

        # 표가 하나뿐이면 sources의 선택 조건을 단일 표 인자로 옮겨 기존 경로를 그대로 쓴다.
        single = selected_sources[0] if selected_sources else {}
        if single:
            stat_id = single["stat_id"]
            table_handle = single.get("table_handle") or table_handle
            x = single.get("key") or x
            year = single.get("year") if single.get("year") is not None else year
        if stat_id is None:
            return VISUALIZATION_SERVICE.error_result(
                "stat_id 또는 sources 중 하나는 반드시 전달해야 합니다.", None, table_seq
            )

        selected_filters = single.get("filters") or (
            [item.model_dump() for item in filters] if filters is not None else None
        )
        selected_metrics = (
            [{"column": single["value"], "label": single.get("label"), "unit": single.get("unit")}]
            if single.get("value")
            else [item.model_dump() for item in metrics] if metrics is not None else None
        )
        return VISUALIZATION_SERVICE.visualize(
            stat_id=stat_id,
            table_seq=table_seq,
            table_handle=table_handle,
            query=query,
            title=title,
            chart_type=chart_type,
            x=x,
            y=y,
            group=group,
            top_n=top_n,
            total_mode=total_mode,
            year=year,
            city=city,
            column_family=column_family,
            filters=selected_filters,
            metrics=selected_metrics,
            orientation=orientation,
            sort_order=sort_order,
        )
