# -*- coding: utf-8 -*-
from mcp.server.fastmcp import FastMCP

from app.asset_server import ensure_asset_server
from app.tool_registry import register_tools


# FastMCP 앱을 만들고 도구를 등록한다.
def create_app() -> FastMCP:
    app = FastMCP("statyearbook")
    register_tools(app)
    return app


mcp = create_app()


# MCP 서버를 stdio 전송으로 실행한다.
def main() -> None:
    # 시각화 PNG를 서빙할 정적 서버를 미리 띄운다.
    ensure_asset_server()
    mcp.run()
