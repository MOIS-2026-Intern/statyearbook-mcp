# -*- coding: utf-8 -*-
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.tools.service.statistics_search_service import search_statistics_data
from app.tool_descriptions import SEARCH_STATISTICS, SEARCH_STATISTICS_FIELDS


# 자연어 통계표 검색 MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    @mcp.tool(description=SEARCH_STATISTICS)
    def search_statistics(
        query: Annotated[str, Field(description=SEARCH_STATISTICS_FIELDS["query"])],
        publication_year: Annotated[
            int | None,
            Field(description=SEARCH_STATISTICS_FIELDS["publication_year"]),
        ] = None,
        limit: Annotated[
            int,
            Field(description=SEARCH_STATISTICS_FIELDS["limit"], ge=1, le=20),
        ] = 5,
    ) -> dict:
        return search_statistics_data(query, publication_year, limit)
