# -*- coding: utf-8 -*-
"""UI 모델 목록과 요청별 모델 gateway 선택을 검증한다."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.controllers import chat_controller
from backend.gateways.model_gateway import UnsupportedChatModelError
from backend.main import create_app
from backend.models.chat import ChatRequest
from backend.models.tooling import ModelTurn, ToolSpec
from backend.services.chat_service import ChatService


GPT_MODEL = "openai/gpt-5-mini"
CLAUDE_MODEL = "anthropic/claude-sonnet-5"


class StubModelGateway:
    def __init__(self, model: str):
        self.model = model
        self.closed = False

    async def create_turn(self, **_kwargs) -> ModelTurn:
        return ModelTurn(text=self.model, tool_calls=[], state=None)

    async def close(self) -> None:
        self.closed = True


class StubMcpGateway:
    def __init__(self, _settings: Settings):
        pass

    async def __aenter__(self) -> "StubMcpGateway":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None

    @property
    def tool_specs_cache_hit(self) -> bool:
        return False

    async def list_tool_specs(self) -> list[ToolSpec]:
        return []


class ChatModelSettingsTests(unittest.TestCase):
    def test_normalizes_and_deduplicates_the_model_catalog(self) -> None:
        configured = Settings(
            chat_model=GPT_MODEL,
            chat_models=(GPT_MODEL, f" {CLAUDE_MODEL} ", GPT_MODEL),
        )

        self.assertEqual(configured.chat_models, (GPT_MODEL, CLAUDE_MODEL))

    def test_requires_the_default_model_in_the_catalog(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "must be included"):
            Settings(chat_model=GPT_MODEL, chat_models=(CLAUDE_MODEL,))


class ChatModelGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.created_models: list[str] = []
        self.gateways: list[StubModelGateway] = []
        settings = Settings(
            chat_model=GPT_MODEL,
            chat_models=(GPT_MODEL, CLAUDE_MODEL),
        )

        def create_gateway(model_settings: Settings) -> StubModelGateway:
            self.created_models.append(model_settings.chat_model)
            gateway = StubModelGateway(model_settings.chat_model)
            self.gateways.append(gateway)
            return gateway

        self.service = ChatService(settings, model_gateway_factory=create_gateway)

    def tearDown(self) -> None:
        asyncio.run(self.service.close())

    def test_creates_and_reuses_one_gateway_per_selected_model(self) -> None:
        claude = self.service._model_for(CLAUDE_MODEL)
        same_claude = self.service._model_for(CLAUDE_MODEL)
        gpt = self.service._model_for(GPT_MODEL)

        self.assertIs(claude, same_claude)
        self.assertIsNot(claude, gpt)
        self.assertEqual(self.created_models, [CLAUDE_MODEL, GPT_MODEL])

    def test_rejects_a_model_outside_the_catalog(self) -> None:
        with self.assertRaisesRegex(UnsupportedChatModelError, "Unsupported chat model"):
            self.service._model_for("unknown/model")

    def test_chat_request_uses_its_selected_model_gateway(self) -> None:
        request = ChatRequest(
            conversationId="conversation-1",
            message="질문",
            model=CLAUDE_MODEL,
        )

        with patch("backend.services.chat_service.McpGateway", StubMcpGateway):
            response = asyncio.run(self.service.respond(request))

        self.assertEqual(response.message.content, CLAUDE_MODEL)
        self.assertEqual(self.created_models, [CLAUDE_MODEL])

    def test_closes_every_created_model_gateway(self) -> None:
        self.service._model_for(GPT_MODEL)
        self.service._model_for(CLAUDE_MODEL)

        asyncio.run(self.service.close())

        self.assertTrue(all(gateway.closed for gateway in self.gateways))


class ChatModelApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            chat_model=GPT_MODEL,
            chat_models=(GPT_MODEL, CLAUDE_MODEL),
        )

    def test_lists_the_backend_model_catalog(self) -> None:
        with patch.object(chat_controller, "settings", self.settings):
            with TestClient(create_app()) as client:
                response = client.get("/api/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["defaultModel"], [model["id"] for model in payload["models"]])
        self.assertIn(GPT_MODEL, [model["id"] for model in payload["models"]])
        self.assertIn(CLAUDE_MODEL, [model["id"] for model in payload["models"]])

    def test_rejects_an_unconfigured_model_before_opening_a_gateway(self) -> None:
        with patch.object(chat_controller, "settings", self.settings):
            with TestClient(create_app()) as client:
                response = client.post(
                    "/api/chat",
                    json={
                        "conversationId": "conversation-1",
                        "message": "질문",
                        "model": "unknown/model",
                    },
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported chat model", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
