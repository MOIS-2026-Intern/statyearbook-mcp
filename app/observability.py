"""MCP protocol logging kept separate from tool implementations."""
from __future__ import annotations

import logging

from copy import deepcopy
from time import perf_counter
from typing import Any

from mcp.server.fastmcp import FastMCP

from utils.logging import compact_json, configure_service_logging


logger = logging.getLogger(__name__)


class ObservedFastMCP(FastMCP):
    """FastMCP with concise protocol-boundary timing logs."""

    # Start Uvicorn and reapply service filters after its logging configuration.
    async def run_streamable_http_async(self) -> None:
        import uvicorn

        starlette_app = self.streamable_http_app()
        log_config = deepcopy(uvicorn.config.LOGGING_CONFIG)
        log_config["formatters"]["access"]["fmt"] = (
            "%(levelprefix)s event=http request=\"%(request_line)s\" "
            "status=%(status_code)s"
        )
        config = uvicorn.Config(
            starlette_app,
            host=self.settings.host,
            port=self.settings.port,
            log_level=self.settings.log_level.lower(),
            log_config=log_config,
        )
        configure_service_logging(self.settings.log_level)
        server = uvicorn.Server(config)
        await server.serve()

    # Log MCP tool discovery at the protocol boundary.
    async def list_tools(self):
        try:
            return await super().list_tools()
        except Exception as exc:
            logger.exception(
                "event=mcp.tools.error error_type=%s",
                exc.__class__.__name__,
            )
            raise

    # Log incoming MCP tool arguments and total tool execution time.
    async def call_tool(self, name: str, arguments: dict[str, Any]):
        started = perf_counter()
        try:
            result = await super().call_tool(name, arguments)
        except Exception as exc:
            logger.exception(
                "event=tool.error tool=%s duration_ms=%s error_type=%s\n    args=%s",
                name,
                _elapsed_ms(started),
                exc.__class__.__name__,
                compact_json(arguments, max_chars=300),
            )
            raise
        is_error = bool(
            getattr(result, "isError", False)
            or (isinstance(result, dict) and result.get("isError"))
        )
        log = logger.error if is_error else logger.debug
        log(
            "event=%s tool=%s duration_ms=%s\n    args=%s",
            "tool.error" if is_error else "tool.call",
            name,
            _elapsed_ms(started),
            compact_json(arguments, max_chars=300),
        )
        return result


# Convert a monotonic start timestamp into rounded milliseconds.
def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
