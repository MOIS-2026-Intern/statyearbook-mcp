# -*- coding: utf-8 -*-
from __future__ import annotations

from openai import AsyncOpenAI

from backend.config import Settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.gateways.openai_gateway import OpenAICompatibleGateway


class BizRouterConfigurationError(ModelGatewayConfigurationError):
    pass


class BizRouterGateway(OpenAICompatibleGateway):
    """BizRouter transport with the shared OpenAI Responses API behavior."""

    def __init__(self, settings: Settings):
        if not settings.bizrouter_api_key:
            raise BizRouterConfigurationError("BIZROUTER_API_KEY is not configured")

        super().__init__(
            settings,
            AsyncOpenAI(
                api_key=settings.bizrouter_api_key,
                base_url=settings.bizrouter_base_url,
                timeout=settings.openai_timeout_seconds,
            ),
        )
