# -*- coding: utf-8 -*-
"""통계 검색 도구를 Streamable HTTP 또는 stdio로 제공하는 독립 MCP 서버."""
import argparse
import logging
import os
import sys

from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import AppSettings, settings
from app.observability import ObservedFastMCP
from app.tool_registry import register_tools
from utils.logging import configure_service_logging


BANNER_PATH = Path(__file__).with_name("banner.txt")
STDIO_TRANSPORT = "stdio"
STREAMABLE_HTTP_TRANSPORT = "streamable-http"
TRANSPORTS = (STREAMABLE_HTTP_TRANSPORT, STDIO_TRANSPORT)


# 배너 파일이 있으면 서버 시작 시 선택한 스트림에 출력한다.
def print_banner(stream: TextIO = sys.stdout) -> None:
    if not BANNER_PATH.exists():
        return

    banner = BANNER_PATH.read_text(encoding="utf-8")
    print(f"\n{banner}\n", flush=True, file=stream)


# 환경변수 기본값을 검증해 실행 인자가 없을 때 쓸 transport를 정한다.
def _default_transport() -> str:
    transport = os.environ.get(
        "STATYEARBOOK_APP_TRANSPORT", STREAMABLE_HTTP_TRANSPORT
    ).strip().lower()
    if transport not in TRANSPORTS:
        allowed = ", ".join(TRANSPORTS)
        raise RuntimeError(f"STATYEARBOOK_APP_TRANSPORT must be one of: {allowed}")
    return transport


# 실행 인자에서 transport를 읽고 없으면 환경변수 기본값을 사용한다.
def parse_transport(argv: Sequence[str] | None = None) -> str:
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="통계연보 MCP 서버를 실행한다.",
    )
    parser.add_argument(
        "--transport",
        choices=TRANSPORTS,
        default=_default_transport(),
        help="MCP transport (기본값: streamable-http, MCP 클라이언트가 직접 실행하면 stdio)",
    )
    return parser.parse_args(argv).transport


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


# MCP 앱을 선택한 transport로 실행한다.
def main(argv: Sequence[str] | None = None) -> None:
    transport = parse_transport(argv)
    logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
    # stdio는 stdout이 JSON-RPC 채널이므로 배너를 stderr로 보낸다.
    print_banner(sys.stderr if transport == STDIO_TRANSPORT else sys.stdout)
    try:
        mcp.run(transport=transport)
    except KeyboardInterrupt:
        return
