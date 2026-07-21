# -*- coding: utf-8 -*-
from __future__ import annotations

from openai import AsyncOpenAI

from backend.config import Settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.gateways.openai_compatible_gateway import OpenAICompatibleGateway


class BizRouterConfigurationError(ModelGatewayConfigurationError):
    pass


class BizRouterGateway(OpenAICompatibleGateway):
    """BizRouter transport with the shared OpenAI Responses API behavior."""

    # BizRouter 인증과 기본 URL을 적용한 OpenAI 호환 클라이언트를 구성한다.
    def __init__(self, settings: Settings):
        if not settings.bizrouter_api_key:
            raise BizRouterConfigurationError(
                "STATYEARBOOK_BACKEND_BIZROUTER_API_KEY is not configured"
            )

        super().__init__(
            settings,
            AsyncOpenAI(
                api_key=settings.bizrouter_api_key,
                base_url=settings.bizrouter_base_url,
                timeout=settings.model_timeout_seconds,
            ),
        )
