# -*- coding: utf-8 -*-
"""통계 검색 도구를 Streamable HTTP로 제공하는 독립 MCP 서버."""
import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import AppSettings, settings
from app.observability import ObservedFastMCP
from app.tool_registry import register_tools
from utils.logging import configure_service_logging


BANNER_PATH = Path(__file__).with_name("banner.txt")


# 배너 파일이 있으면 서버 시작 시 콘솔에 출력한다.
def print_banner() -> None:
    if not BANNER_PATH.exists():
        return

    banner = BANNER_PATH.read_text(encoding="utf-8")
    print(f"\n{banner}\n", flush=True)


# MCP 인스턴스를 만들고 도구 및 상태 확인 경로를 등록한다.
def create_app(config: AppSettings = settings) -> ObservedFastMCP:
    mcp = ObservedFastMCP(
        "statyearbook",
        host=config.host,
        port=config.port,
        log_level=config.log_level,
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


configure_service_logging(settings.log_level)
mcp = create_app()


# MCP 앱을 Streamable HTTP transport로 실행한다.
def main() -> None:
    logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
    print_banner()
    try:
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        return
