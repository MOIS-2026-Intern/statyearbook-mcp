"""Structured service logging behavior."""

import asyncio
import logging
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.types import CallToolResult, TextContent
from starlette.responses import JSONResponse

from app import observability
from app.observability import ObservedFastMCP
from backend.config import Settings
from backend.middleware import access_log
from backend.middleware.access_log import add_access_log_middleware
from utils.logging import (
    SERVICE_HANDLER_MARKER,
    AccessLogFilter,
    compact_json,
    configure_service_logging,
)


class AccessLogFilterTests(unittest.TestCase):
    def _record(self, path: str, status: int) -> logging.LogRecord:
        return logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:5000", "GET", path, "1.1", status),
            None,
        )

    def test_suppresses_successful_health_access_log(self) -> None:
        self.assertFalse(AccessLogFilter().filter(self._record("/health", 200)))

    def test_promotes_failed_health_access_log_to_error(self) -> None:
        record = self._record("/health?probe=remote", 503)

        self.assertTrue(AccessLogFilter().filter(record))
        self.assertEqual(record.levelno, logging.ERROR)

    def test_suppresses_mcp_transport_access_log(self) -> None:
        self.assertFalse(AccessLogFilter().filter(self._record("/mcp", 200)))

    def test_keeps_normal_http_access_log_at_info(self) -> None:
        record = self._record("/other", 200)

        self.assertTrue(AccessLogFilter().filter(record))
        self.assertEqual(record.levelno, logging.INFO)

    def test_error_level_keeps_only_failed_health_access_log(self) -> None:
        access_filter = AccessLogFilter("ERROR")

        self.assertFalse(access_filter.filter(self._record("/mcp", 200)))
        self.assertTrue(access_filter.filter(self._record("/health", 503)))


class BackendAccessLogTests(unittest.TestCase):
    def _client(self, health_status: int = 200) -> TestClient:
        app = FastAPI()
        add_access_log_middleware(app)

        @app.get("/health")
        async def health() -> JSONResponse:
            return JSONResponse({"status": "ok"}, status_code=health_status)

        @app.get("/data")
        async def data() -> dict[str, bool]:
            return {"ok": True}

        return TestClient(app)

    def test_successful_health_has_no_application_log(self) -> None:
        with self.assertNoLogs("backend.middleware.access_log", level="INFO"):
            response = self._client().get("/health")

        self.assertEqual(response.status_code, 200)

    def test_failed_health_is_logged_as_error(self) -> None:
        with self.assertLogs("backend.middleware.access_log", level="ERROR") as captured:
            response = self._client(503).get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertIn("event=health.error", captured.output[0])

    def test_normal_http_request_is_logged_as_info(self) -> None:
        with self.assertLogs("backend.middleware.access_log", level="INFO") as captured:
            response = self._client().get("/data")

        self.assertEqual(response.status_code, 200)
        self.assertIn("event=http method=GET", captured.output[0])


class McpProtocolLogTests(unittest.TestCase):
    def test_tool_boundary_logs_one_concise_completion(self) -> None:
        server = ObservedFastMCP("test", log_level="DEBUG")

        @server.tool()
        def double(value: int) -> int:
            return value * 2

        with self.assertLogs("app.observability", level="DEBUG") as captured:
            asyncio.run(server.call_tool("double", {"value": 4}))

        output = "\n".join(captured.output)
        self.assertEqual(len(captured.output), 1)
        self.assertIn("event=tool.call", output)
        self.assertIn("tool=double", output)
        self.assertIn("duration_ms=", output)
        self.assertIn('args={"value":4}', output)

    def test_tool_error_result_is_logged_as_error(self) -> None:
        server = ObservedFastMCP("test", log_level="DEBUG")

        @server.tool()
        def fail() -> CallToolResult:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text="failed")],
            )

        with self.assertLogs("app.observability", level="ERROR") as captured:
            asyncio.run(server.call_tool("fail", {}))

        self.assertIn("event=tool.error", captured.output[0])


class LoggingSettingsTests(unittest.TestCase):
    def test_service_handler_uses_uvicorn_color_formatter(self) -> None:
        configure_service_logging("DEBUG")
        handler = next(
            item
            for item in logging.getLogger().handlers
            if getattr(item, SERVICE_HANDLER_MARKER, False)
        )

        self.assertEqual(handler.formatter.__class__.__name__, "DefaultFormatter")
        self.assertEqual(handler.formatter._fmt, "%(levelprefix)s %(message)s")

    def test_application_loggers_use_module_names(self) -> None:
        self.assertEqual(observability.logger.name, "app.observability")
        self.assertEqual(access_log.logger.name, "backend.middleware.access_log")

    def test_log_level_is_normalized(self) -> None:
        self.assertEqual(Settings(log_level="info").log_level, "INFO")

    def test_unknown_log_level_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "BACKEND_LOG_LEVEL"):
            Settings(log_level="trace")

    def test_compact_json_escapes_lines_and_bounds_large_values(self) -> None:
        value = compact_json({"message": "first\n" + "x" * 100}, max_chars=30)

        self.assertNotIn("\n", value)
        self.assertIn("<omitted=", value)


if __name__ == "__main__":
    unittest.main()
