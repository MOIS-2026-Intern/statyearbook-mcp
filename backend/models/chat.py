# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from utils.publication_kind import DEFAULT_PUBLICATION_KIND, PublicationKind


MessageRole = Literal["user", "assistant", "system"]
McpTraceKind = Literal["tool_discovery", "tool_call", "tool_result", "resource_read", "error"]
McpTraceStatus = Literal["queued", "running", "success", "error"]
ChatProgressStage = Literal[
    "connecting_mcp",
    "discovering_tools",
    "planning",
    "calling_tool",
    "reviewing_results",
    "finalizing",
]


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


class ChatRequest(BaseModel):
    conversationId: str
    message: str = Field(min_length=1)
    modelProfile: str = "balanced"
    publicationKind: PublicationKind = DEFAULT_PUBLICATION_KIND
    includeMcpTrace: bool = True
    history: list[ChatMessage] = Field(default_factory=list)
    traces: list[McpTrace] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: ChatMessage
    traces: list[McpTrace]


class ChatProgress(BaseModel):
    stage: ChatProgressStage
    message: str
    tool: str | None = None
