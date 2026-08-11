# -*- coding: utf-8 -*-
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.tools.repository.publication_comparison_repository import (
    CompareField,
    CompareMatchBy,
    CompareOperation,
    CompareSubject,
)
from app.tools.service.publication_comparison_service import compare_publications_data
from app.tool_descriptions import COMPARE_PUBLICATIONS, COMPARE_PUBLICATIONS_FIELDS


# 발간판 비교 도구를 MCP에 등록한다.
def register(mcp: FastMCP) -> None:
    @mcp.tool(description=COMPARE_PUBLICATIONS)
    def compare_publications(
        operation: Annotated[
            CompareOperation,
            Field(description=COMPARE_PUBLICATIONS_FIELDS["operation"]),
        ],
        subject: Annotated[
            CompareSubject,
            Field(description=COMPARE_PUBLICATIONS_FIELDS["subject"]),
        ] = "statistics",
        match_by: Annotated[
            CompareMatchBy,
            Field(description=COMPARE_PUBLICATIONS_FIELDS["match_by"]),
        ] = "title",
        base_publication_year: Annotated[
            int | None,
            Field(
                description=COMPARE_PUBLICATIONS_FIELDS["base_publication_year"],
                ge=1900,
                le=2200,
            ),
        ] = None,
        target_publication_year: Annotated[
            int | None,
            Field(
                description=COMPARE_PUBLICATIONS_FIELDS["target_publication_year"],
                ge=1900,
                le=2200,
            ),
        ] = None,
        fields: Annotated[
            list[CompareField] | None,
            Field(description=COMPARE_PUBLICATIONS_FIELDS["fields"]),
        ] = None,
        compare_fields: Annotated[
            list[CompareField] | None,
            Field(description=COMPARE_PUBLICATIONS_FIELDS["compare_fields"]),
        ] = None,
        limit: Annotated[
            int,
            Field(
                description=COMPARE_PUBLICATIONS_FIELDS["limit"],
                ge=1,
                le=500,
            ),
        ] = 500,
        offset: Annotated[
            int,
            Field(description=COMPARE_PUBLICATIONS_FIELDS["offset"], ge=0),
        ] = 0,
    ) -> dict[str, Any]:
        return compare_publications_data(
            operation=operation,
            subject=subject,
            match_by=match_by,
            base_publication_year=base_publication_year,
            target_publication_year=target_publication_year,
            fields=fields,
            compare_fields=compare_fields,
            limit=limit,
            offset=offset,
        )
