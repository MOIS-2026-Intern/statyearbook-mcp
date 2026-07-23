"""Small logging helpers shared by the HTTP services."""
from __future__ import annotations

import json
import logging

from typing import Any


VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
SERVICE_LOG_FORMAT = "%(levelprefix)s %(message)s"
SERVICE_HANDLER_MARKER = "_statyearbook_handler"


# Validate and normalize service log levels loaded from environment variables.
def normalize_log_level(value: str, env_name: str) -> str:
    """Return a supported upper-case logging level or fail with a useful setting name."""
    level = value.strip().upper()
    if level not in VALID_LOG_LEVELS:
        allowed = ", ".join(sorted(VALID_LOG_LEVELS))
        raise RuntimeError(f"{env_name} must be one of: {allowed}")
    return level


# Keep arbitrary structured values bounded and single-line in DEBUG logs.
def compact_json(value: Any, max_chars: int = 800) -> str:
    """Serialize a log value onto one bounded line."""
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        text = repr(value)
    text = text.replace("\n", "\\n").replace("\r", "\\r")
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}...<omitted={omitted}>"


class AccessLogFilter(logging.Filter):
    """Hide MCP transport and successful health access records."""

    # Store the configured service threshold for ordinary HTTP access records.
    def __init__(self, level: str = "DEBUG") -> None:
        super().__init__()
        self.minimum_level = getattr(logging, level)

    # Filter successful probes and reclassify failed probes before handlers run.
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return record.levelno >= self.minimum_level

        path = str(args[2]).split("?", 1)[0]
        if path == "/mcp":
            return False
        if path != "/health":
            return record.levelno >= self.minimum_level

        try:
            status_code = int(args[4])
        except (TypeError, ValueError):
            return record.levelno >= self.minimum_level
        if status_code < 400:
            return False

        record.levelno = logging.ERROR
        record.levelname = logging.getLevelName(logging.ERROR)
        return record.levelno >= self.minimum_level


# Configure the shared root handler plus Uvicorn and dependency logger levels.
def configure_service_logging(level: str) -> None:
    """Apply one application format while keeping third-party DEBUG output concise."""
    from uvicorn.logging import DefaultFormatter

    root_logger = logging.getLogger()
    service_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if getattr(handler, SERVICE_HANDLER_MARKER, False)
        ),
        None,
    )
    if service_handler is None:
        service_handler = logging.StreamHandler()
        setattr(service_handler, SERVICE_HANDLER_MARKER, True)
        root_logger.addHandler(service_handler)
    service_handler.setFormatter(
        DefaultFormatter(fmt=SERVICE_LOG_FORMAT, use_colors=None)
    )
    service_handler.setLevel(logging.NOTSET)
    root_logger.setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(logging.INFO)
    health_filters = [
        item for item in access_logger.filters if isinstance(item, AccessLogFilter)
    ]
    if health_filters:
        for item in health_filters:
            item.minimum_level = getattr(logging, level)
    else:
        access_logger.addFilter(AccessLogFilter(level))

    # Keep protocol clients from dumping duplicate requests or complete MCP payloads.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.getLogger("mcp.server.streamable_http_manager").setLevel(logging.WARNING)
    logging.getLogger("sse_starlette").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
