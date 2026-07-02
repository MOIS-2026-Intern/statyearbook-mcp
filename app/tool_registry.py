# -*- coding: utf-8 -*-
"""MCP 도구 등록 목록.

각 도구 모듈은 register(mcp) 함수를 제공한다.
새 도구를 추가하려면 app/tools/ 아래에 모듈을 만들고 register_tools 에 한 줄 추가한다.
"""
from mcp.server.fastmcp import FastMCP

from app.tools import search_statistics, search_tables


def register_tools(mcp: FastMCP) -> None:
    search_statistics.register(mcp)
    search_tables.register(mcp)
