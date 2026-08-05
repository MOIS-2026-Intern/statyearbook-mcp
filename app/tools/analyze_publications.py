# -*- coding: utf-8 -*-
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.tools.repository.publication_analysis_repository import (
    AnalysisField,
    AnalysisGroup,
    AnalysisOperation,
    AnalysisSubject,
    AnalysisValueFilterField,
)
from app.tools.service.publication_analysis_service import analyze_publications_data
from app.tool_descriptions import (
    ANALYZE_PUBLICATIONS,
    ANALYZE_PUBLICATIONS_FIELDS,
    VALUE_FILTER_FIELDS,
)


class ValueFilter(BaseModel):
    field: AnalysisValueFilterField = Field(description=VALUE_FILTER_FIELDS["field"])
    contains: str = Field(description=VALUE_FILTER_FIELDS["contains"])


# 연보 단위 집계·목록 도구를 MCP에 등록한다.
def register(mcp: FastMCP) -> None:
    @mcp.tool(description=ANALYZE_PUBLICATIONS)
    def analyze_publications(
        operation: Annotated[
            AnalysisOperation,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["operation"]),
        ],
        subject: Annotated[
            AnalysisSubject,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["subject"]),
        ] = "statistics",
        group_by: Annotated[
            AnalysisGroup | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["group_by"]),
        ] = None,
        distinct_field: Annotated[
            AnalysisField | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["distinct_field"]),
        ] = None,
        fields: Annotated[
            list[AnalysisField] | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["fields"]),
        ] = None,
        required_fields: Annotated[
            list[AnalysisField] | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["required_fields"]),
        ] = None,
        value_filters: Annotated[
            list[ValueFilter] | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["value_filters"]),
        ] = None,
        deduplicate: Annotated[
            bool | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["deduplicate"]),
        ] = None,
        publication_year: Annotated[
            int | None,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["publication_year"],
                ge=1900,
                le=2200,
            ),
        ] = None,
        all_publication_years: Annotated[
            bool,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["all_publication_years"]),
        ] = False,
        chapter_no: Annotated[
            int | None,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["chapter_no"],
                ge=1,
            ),
        ] = None,
        section_no: Annotated[
            int | None,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["section_no"],
                ge=1,
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["limit"],
                ge=1,
                le=500,
            ),
        ] = 500,
        offset: Annotated[
            int,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["offset"],
                ge=0,
            ),
        ] = 0,
    ) -> dict[str, Any]:
        return analyze_publications_data(
            operation=operation,
            subject=subject,
            group_by=group_by,
            distinct_field=distinct_field,
            fields=fields,
            required_fields=required_fields,
            value_filters=(
                [item.model_dump() for item in value_filters]
                if value_filters is not None
                else None
            ),
            deduplicate=deduplicate,
            publication_year=publication_year,
            all_publication_years=all_publication_years,
            chapter_no=chapter_no,
            section_no=section_no,
            limit=limit,
            offset=offset,
        )
