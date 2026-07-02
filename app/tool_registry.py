# -*- coding: utf-8 -*-
from mcp.server.fastmcp import FastMCP

from app.tools import search_statistics, search_tables


# MCP 도구를 FastMCP 앱에 등록한다.
def register_tools(mcp: FastMCP) -> None:
    search_statistics.register(mcp)
    search_tables.register(mcp)
