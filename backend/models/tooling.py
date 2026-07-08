# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ModelMessageRole = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class ModelMessage:
    role: ModelMessageRole
    content: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: Any | None = None
    arguments_error: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    result: Any
    is_error: bool = False


@dataclass(frozen=True)
class ModelTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    state: Any | None = None
