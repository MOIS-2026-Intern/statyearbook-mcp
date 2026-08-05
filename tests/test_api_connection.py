# -*- coding: utf-8 -*-
"""app MCP 서버와 chat backend API가 응답하고 공개 도구를 노출하는지 검증한다."""
import asyncio
import unittest

from fastapi.testclient import TestClient

from app.server import create_app as create_mcp_app
from backend.main import create_app as create_backend_app


PUBLIC_TOOLS = {
    "analyze_publications",
    "compare_publications",
    "search_contacts",
    "search_statistics",
    "search_tables",
    "visualize",
}


class ApiConnectionTests(unittest.TestCase):
    # 두 서비스의 health 경로가 열리고 backend가 기대하는 MCP 도구가 등록되어야 한다.
    def test_service_health_endpoints_and_mcp_tools_are_reachable(self) -> None:
        mcp = create_mcp_app()
        app_health = TestClient(mcp.streamable_http_app()).get("/health")
        backend_health = TestClient(create_backend_app()).get("/health")
        tool_names = {tool.name for tool in asyncio.run(mcp.list_tools())}

        self.assertEqual(app_health.status_code, 200)
        self.assertEqual(app_health.json()["status"], "ok")
        self.assertEqual(backend_health.status_code, 200)
        self.assertEqual(backend_health.json()["status"], "ok")
        self.assertEqual(tool_names, PUBLIC_TOOLS)


if __name__ == "__main__":
    unittest.main()
