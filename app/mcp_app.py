# -*- coding: utf-8 -*-
import logging

from mcp.server.fastmcp import FastMCP

from app.tool_registry import register_tools


# FastMCP 앱을 만들고 도구를 등록한다.
def create_app() -> FastMCP:
    app = FastMCP("statyearbook")
    register_tools(app)
    return app


mcp = create_app()


# MCP 서버를 stdio 전송으로 실행한다.
def main() -> None:
    # "Processing request of type ..." 로그를 숨긴다.
    logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
    mcp.run()
