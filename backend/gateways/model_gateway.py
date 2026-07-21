# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Protocol

from backend.config import Settings
from backend.models.tooling import ModelMessage, ModelTurn, ToolResult, ToolSpec


class ModelGatewayConfigurationError(RuntimeError):
    pass


class ModelGateway(Protocol):
    # 현재 대화와 도구 결과로 다음 모델 턴을 생성한다.
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


# 설정에서 선택한 공급자에 맞는 모델 gateway를 생성한다.
def create_model_gateway(settings: Settings) -> ModelGateway:
    if settings.model_provider == "openai":
        from backend.gateways.openai_gateway import OpenAIGateway

        return OpenAIGateway(settings)

    if settings.model_provider == "bizrouter":
        from backend.gateways.bizrouter_gateway import BizRouterGateway

        return BizRouterGateway(settings)

    raise ModelGatewayConfigurationError(f"Unsupported model provider: {settings.model_provider}")
