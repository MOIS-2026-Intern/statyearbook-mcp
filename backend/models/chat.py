# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from utils.publication_kind import DEFAULT_PUBLICATION_SCOPE, PublicationScope


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
    # 생략한 기존 클라이언트는 배포 환경의 기본 모델을 사용한다. 값이 있으면 백엔드의
    # 허용 목록을 통과한 모델별 gateway로 요청을 보낸다.
    model: str | None = Field(default=None, min_length=1)
    # 화면 버튼이 고른 조회 범위다. 발간물 하나(yearbook·major_statistics) 또는 둘 다(all)이며,
    # 필드 이름은 기존 클라이언트가 보내는 값을 그대로 받기 위해 유지한다.
    publicationKind: PublicationScope = DEFAULT_PUBLICATION_SCOPE
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


class ChatModelOption(BaseModel):
    id: str
    label: str


class ChatModelsResponse(BaseModel):
    defaultModel: str
    models: list[ChatModelOption]
