# -*- coding: utf-8 -*-
"""통계 검색 도구를 Streamable HTTP로 제공하는 독립 MCP 서버."""
import logging

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import AppSettings, settings
from app.tool_registry import register_tools


# MCP 인스턴스를 만들고 도구 및 상태 확인 경로를 등록한다.
def create_app(config: AppSettings = settings) -> FastMCP:
    mcp = FastMCP(
        "statyearbook",
        host=config.host,
        port=config.port,
        streamable_http_path="/mcp",
    )
    register_tools(mcp)

    # 현재 프로필과 임베딩 구성을 포함한 상태 정보를 반환한다.
    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "statyearbook-app",
                "profile": config.profile,
                "embeddingProvider": config.embedding.provider,
                "embeddingDimension": config.embedding.dimension,
            }
        )

    return mcp


mcp = create_app()


# MCP 앱을 Streamable HTTP transport로 실행한다.
def main() -> None:
    logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
    try:
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        return
