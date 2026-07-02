# -*- coding: utf-8 -*-
"""FastMCP 앱을 구성하고 실행한다.

개별 도구 로직은 app/tools/ 아래 각 모듈에 있고, 등록 목록은 app/tool_registry.py 에 있다.
실행 진입점은 루트의 server.py 다.
"""
from mcp.server.fastmcp import FastMCP

from app.tool_registry import register_tools

mcp = FastMCP("statyearbook")
register_tools(mcp)


def main() -> None:
    mcp.run()  # 기본 전송 = stdio
