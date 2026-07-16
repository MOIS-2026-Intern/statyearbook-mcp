# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Protocol

from backend.config import Settings
from backend.models.tooling import ModelMessage, ModelTurn, ToolResult, ToolSpec


class ModelGatewayConfigurationError(RuntimeError):
    pass


class ModelGateway(Protocol):
    async def create_turn(
        self,
        *,
        instructions: str,
        messages: list[ModelMessage],
        tools: list[ToolSpec],
        model_profile: str,
        tool_results: list[ToolResult] | None = None,
        state: object | None = None,
    ) -> ModelTurn:
        ...


def create_model_gateway(settings: Settings) -> ModelGateway:
    if settings.model_provider == "openai":
        from backend.gateways.openai_gateway import OpenAIGateway

        return OpenAIGateway(settings)

    if settings.model_provider == "bizrouter":
        from backend.gateways.bizrouter_gateway import BizRouterGateway

        return BizRouterGateway(settings)

    if settings.model_provider == "local_gemma":
        from backend.gateways.local_gemma_gateway import LocalGemmaGateway

        return LocalGemmaGateway(settings)

    raise ModelGatewayConfigurationError(f"Unsupported model provider: {settings.model_provider}")
