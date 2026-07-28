import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.config import Settings
from backend.gateways.mcp_gateway import McpGateway, clear_tool_specs_cache


class McpGatewayToolCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_tool_specs_cache()

    def tearDown(self) -> None:
        clear_tool_specs_cache()

    def test_tool_specs_are_reused_within_ttl(self) -> None:
        settings = Settings(
            mcp_url="http://cache-test.invalid/mcp",
            mcp_tool_cache_ttl_seconds=300,
        )
        first = McpGateway(settings)
        first.list_tools = AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="search_statistics",
                    description="통계표 검색",
                    inputSchema={"type": "object", "properties": {}},
                )
            ]
        )
        second = McpGateway(settings)
        second.list_tools = AsyncMock(side_effect=AssertionError("cache miss"))

        first_specs = asyncio.run(first.list_tool_specs())
        second_specs = asyncio.run(second.list_tool_specs())

        self.assertFalse(first.tool_specs_cache_hit)
        self.assertTrue(second.tool_specs_cache_hit)
        self.assertEqual(first_specs, second_specs)
        first.list_tools.assert_awaited_once()
        second.list_tools.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
