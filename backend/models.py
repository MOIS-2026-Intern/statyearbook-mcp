# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant", "system"]
McpTraceKind = Literal["tool_discovery", "tool_call", "tool_result", "resource_read", "error"]
McpTraceStatus = Literal["queued", "running", "success", "error"]


class ChatRequest(BaseModel):
    conversationId: str
    message: str = Field(min_length=1)
    modelProfile: str = "balanced"
    includeMcpTrace: bool = True


class McpTrace(BaseModel):
    id: str
    kind: McpTraceKind
    status: McpTraceStatus
    title: str
    timestamp: str
    server: str
    tool: str | None = None
    summary: str | None = None
    durationMs: int | None = None
    request: Any | None = None
    response: Any | None = None


class ChatMessage(BaseModel):
    id: str
    role: MessageRole
    content: str
    createdAt: str
    traceIds: list[str] | None = None


class ChatResponse(BaseModel):
    message: ChatMessage
    traces: list[McpTrace]


class HealthResponse(BaseModel):
    status: str
    app: str
    openaiModel: str
    openaiConfigured: bool
    mcp: dict[str, Any]
