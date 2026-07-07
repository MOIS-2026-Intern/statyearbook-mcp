# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.config import Settings
from backend.serializers.mcp_result_serializer import sanitize_mcp_result, to_jsonable


class McpGatewayError(RuntimeError):
    pass


class McpGateway:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "McpGateway":
        server = StdioServerParameters(
            command=self._settings.mcp_command,
            args=self._settings.mcp_args,
            cwd=self._settings.mcp_cwd,
        )

        self._stack = AsyncExitStack()
        read_stream, write_stream = await self._stack.enter_async_context(stdio_client(server))
        self._session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._session = None
        self._stack = None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise McpGatewayError("MCP session is not initialized")
        return self._session

    async def list_tools(self) -> list[Any]:
        result = await self.session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        args = dict(arguments)
        if self._settings.force_visualize_without_inline_image and name == "visualize":
            args["include_image"] = False

        result = await self.session.call_tool(
            name,
            args,
            read_timeout_seconds=timedelta(seconds=self._settings.mcp_call_timeout_seconds),
        )
        return sanitize_mcp_result(result)


def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    payload = to_jsonable(schema)
    if not isinstance(payload, dict) or payload.get("type") != "object":
        return {"type": "object", "properties": {}}
    return payload


def openai_tool_from_mcp(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "name": getattr(tool, "name"),
        "description": getattr(tool, "description", None) or f"MCP tool {getattr(tool, 'name')}",
        "parameters": _tool_schema(tool),
        "strict": False,
    }


def describe_tool(tool: Any) -> dict[str, Any]:
    return {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", None),
        "input_schema": _tool_schema(tool),
    }
