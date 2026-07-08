# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app: str
    modelProvider: str
    chatModel: str
    modelConfigured: bool
    openaiModel: str
    openaiConfigured: bool
    mcp: dict[str, Any]
