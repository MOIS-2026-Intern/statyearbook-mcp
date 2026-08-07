from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.tools.service.visualization.chart_spec_builder import ChartType, SortOrder
from app.tools.service.visualization.table_interpreter import TotalMode
from app.tools.service.visualization.visualization_service import VisualizationService
from app.tool_descriptions import (
    METRIC_SELECTION_FIELDS,
    SELECTION_FILTER_FIELDS,
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


# visualize MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # 통계표를 프론트엔드 렌더링용 Vega-Lite spec으로 반환한다.
    @mcp.tool(description=VISUALIZE)
    def visualize(
        stat_id: int,
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
            filters=[item.model_dump() for item in filters] if filters is not None else None,
            metrics=[item.model_dump() for item in metrics] if metrics is not None else None,
            orientation=orientation,
            sort_order=sort_order,
        )
