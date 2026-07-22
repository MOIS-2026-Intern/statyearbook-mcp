# -*- coding: utf-8 -*-
from __future__ import annotations

import logging

from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.config import Settings
from backend.models.tooling import ToolSpec
from backend.serializers.mcp_result_serializer import sanitize_mcp_result, to_jsonable


logger = logging.getLogger("uvicorn.error")


class McpGatewayError(RuntimeError):
    pass


class McpGateway:
    # MCP 연결 설정과 세션 상태를 초기화한다.
    def __init__(self, settings: Settings):
        self._settings = settings
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    # streamable HTTP 연결을 열고 MCP 세션을 초기화한다.
    async def __aenter__(self) -> "McpGateway":
        self._stack = AsyncExitStack()
        read_stream, write_stream, _ = await self._stack.enter_async_context(
            streamable_http_client(self._settings.mcp_url)
        )
        self._session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
        await self._session.initialize()
        return self

    # 컨텍스트 종료 시 MCP 연결 자원과 세션 상태를 정리한다.
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._session = None
        self._stack = None

    # 초기화된 MCP 세션만 반환하고 미연결 상태는 오류로 알린다.
    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise McpGatewayError("MCP session is not initialized")
        return self._session

    # MCP 서버가 공개한 원본 도구 목록을 조회한다.
    async def list_tools(self) -> list[Any]:
        result = await self.session.list_tools()
        return list(result.tools)

    # MCP 도구 메타데이터를 모델이 사용하는 사양으로 변환한다.
    async def list_tool_specs(self) -> list[ToolSpec]:
        return [tool_spec_from_mcp(tool) for tool in await self.list_tools()]

    # 인자를 정규화해 MCP 도구를 호출하고 결과를 안전한 JSON 형태로 반환한다.
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        args = self.prepare_tool_arguments(name, arguments)
        logger.info("MCP tool called name=%s", name)

        result = await self.session.call_tool(
            name,
            args,
            read_timeout_seconds=timedelta(seconds=self._settings.mcp_call_timeout_seconds),
        )
        return sanitize_mcp_result(result)

    # 도구 호출 인자를 변경 가능한 복사본으로 준비한다.
    def prepare_tool_arguments(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return dict(arguments)


# MCP 도구의 입력 스키마를 유효한 JSON object 스키마로 정규화한다.
def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    payload = to_jsonable(schema)
    if not isinstance(payload, dict) or payload.get("type") != "object":
        return {"type": "object", "properties": {}}
    return payload


# MCP 도구 객체를 모델 gateway용 도구 사양으로 변환한다.
def tool_spec_from_mcp(tool: Any) -> ToolSpec:
    name = str(getattr(tool, "name", ""))
    return ToolSpec(
        name=name,
        description=getattr(tool, "description", None) or f"MCP tool {name}",
        input_schema=_tool_schema(tool),
    )


# trace에 담을 수 있도록 도구 사양을 일반 딕셔너리로 풀어낸다.
def describe_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }
