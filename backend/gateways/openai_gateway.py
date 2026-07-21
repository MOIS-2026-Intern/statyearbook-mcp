# -*- coding: utf-8 -*-
"""OpenAI provider의 인증과 client 구성을 담당하는 gateway."""

from openai import AsyncOpenAI

from backend.config import Settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.gateways.openai_compatible_gateway import OpenAICompatibleGateway


class OpenAIConfigurationError(ModelGatewayConfigurationError):
    pass


class OpenAIGateway(OpenAICompatibleGateway):
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise OpenAIConfigurationError("OPENAI_API_KEY is not configured")

        super().__init__(
            settings,
            AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            ),
        )
