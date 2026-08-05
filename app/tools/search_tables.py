# -*- coding: utf-8 -*-
from mcp.server.fastmcp import FastMCP

from app.tools.service.table_service import search_tables_data
from app.tool_descriptions import SEARCH_TABLES


# 통계표 원문 조회 MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    @mcp.tool(description=SEARCH_TABLES)
    def search_tables(stat_id: int, table_seq: int | None = None) -> dict:
        return search_tables_data(stat_id)
