# -*- coding: utf-8 -*-
from mcp.server.fastmcp import FastMCP

from app.tool_registry import register_tools

# FastMCP 앱을 만들고 도구를 등록한다.
mcp = FastMCP("statyearbook")
register_tools(mcp)


# MCP 서버를 stdio 전송으로 실행한다.
def main() -> None:
    mcp.run()
