# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from backend.config import Settings


class OpenAIConfigurationError(RuntimeError):
    pass


class OpenAIResponsesClient:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise OpenAIConfigurationError("OPENAI_API_KEY is not configured")

        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
        )

    async def create(
        self,
        *,
        instructions: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
        model_profile: str,
    ) -> Any:
        reasoning = _reasoning_for_profile(model_profile)
        kwargs: dict[str, Any] = {
            "model": self._settings.openai_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "parallel_tool_calls": False,
        }
        if reasoning is not None:
            kwargs["reasoning"] = reasoning

        return await self._client.responses.create(**kwargs)


def _reasoning_for_profile(model_profile: str) -> dict[str, str] | None:
    if model_profile == "fast":
        return {"effort": "none"}
    if model_profile == "deep":
        return {"effort": "medium"}
    return {"effort": "low"}
