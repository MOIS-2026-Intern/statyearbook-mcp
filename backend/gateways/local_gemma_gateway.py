# -*- coding: utf-8 -*-
from __future__ import annotations

from backend.config import Settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.models.tooling import ModelMessage, ModelTurn, ToolResult, ToolSpec


class LocalGemmaConfigurationError(ModelGatewayConfigurationError):
    pass


class LocalGemmaGateway:
    def __init__(self, settings: Settings):
        self._settings = settings

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
        raise LocalGemmaConfigurationError(
            "STATYEARBOOK_MODEL_PROVIDER=local_gemma is recognized, but the local Gemma "
            "runtime adapter has not been wired yet. Implement this gateway for the chosen "
            "runtime protocol, such as Ollama, llama.cpp, or vLLM."
        )
