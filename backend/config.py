# -*- coding: utf-8 -*-
"""채팅 backend가 소유하는 모델, HTTP, MCP 연결 설정."""
from __future__ import annotations

import os

from dataclasses import dataclass, field
from pathlib import Path

from utils.env import load_service_env


BACKEND_DIR = Path(__file__).resolve().parent
PROFILE = load_service_env(BACKEND_DIR)


# 쉼표로 구분된 환경 변수 값을 정리하고 비어 있으면 기본값을 사용한다.
def _csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "statyearbook-backend"
    profile: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    model_provider: str = "openai"
    chat_model: str = "gpt-5.5"
    model_timeout_seconds: float = 60.0
    openai_api_key: str | None = None
    bizrouter_api_key: str | None = None
    bizrouter_base_url: str = "https://api.bizrouter.ai/v1"
    max_tool_rounds: int = 5
    tool_output_max_chars: int = 60_000
    mcp_server_label: str = "statyearbook"
    mcp_url: str = "http://127.0.0.1:8001/mcp"
    mcp_call_timeout_seconds: float = 90.0

    # 모델 공급자를 제한하고 운영 프로필의 필수 인증·MCP 설정을 시작 시 검증한다.
    def __post_init__(self) -> None:
        supported_providers = {"openai", "bizrouter"}
        if self.model_provider not in supported_providers:
            allowed = ", ".join(sorted(supported_providers))
            raise RuntimeError(
                f"STATYEARBOOK_BACKEND_MODEL_PROVIDER must be one of: {allowed}"
            )

        if self.profile != "main":
            return

        if not self.mcp_url.strip():
            raise RuntimeError(
                "STATYEARBOOK_BACKEND_MCP_URL is required when APP_PROFILE=main"
            )
        if not self.cors_origins:
            raise RuntimeError(
                "STATYEARBOOK_BACKEND_CORS_ORIGINS is required when APP_PROFILE=main"
            )

        provider_keys = {
            "openai": (
                "STATYEARBOOK_BACKEND_OPENAI_API_KEY",
                self.openai_api_key,
            ),
            "bizrouter": (
                "STATYEARBOOK_BACKEND_BIZROUTER_API_KEY",
                self.bizrouter_api_key,
            ),
        }
        key_name, key_value = provider_keys[self.model_provider]
        if not key_value or not key_value.strip():
            raise RuntimeError(f"{key_name} is required when APP_PROFILE=main")

    # 현재 프로필에 로드된 환경 변수로 백엔드 설정을 구성한다.
    @classmethod
    def from_env(cls) -> "Settings":
        profile = PROFILE
        return cls(
            profile=profile,
            host=os.environ.get("STATYEARBOOK_BACKEND_HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT") or os.environ.get("STATYEARBOOK_BACKEND_PORT", "8000")),
            reload=profile == "local",
            cors_origins=_csv(
                os.environ.get("STATYEARBOOK_BACKEND_CORS_ORIGINS"),
                ["http://localhost:5173", "http://127.0.0.1:5173"],
            ),
            model_provider=os.environ.get(
                "STATYEARBOOK_BACKEND_MODEL_PROVIDER", "openai"
            ).strip().lower(),
            chat_model=os.environ.get("STATYEARBOOK_BACKEND_CHAT_MODEL", "gpt-5.5"),
            model_timeout_seconds=float(
                os.environ.get("STATYEARBOOK_BACKEND_MODEL_TIMEOUT_SECONDS", "60")
            ),
            openai_api_key=os.environ.get("STATYEARBOOK_BACKEND_OPENAI_API_KEY"),
            bizrouter_api_key=os.environ.get("STATYEARBOOK_BACKEND_BIZROUTER_API_KEY"),
            bizrouter_base_url=os.environ.get(
                "STATYEARBOOK_BACKEND_BIZROUTER_BASE_URL",
                "https://api.bizrouter.ai/v1",
            ).rstrip("/"),
            max_tool_rounds=int(
                os.environ.get("STATYEARBOOK_BACKEND_MAX_TOOL_ROUNDS", "5")
            ),
            tool_output_max_chars=int(
                os.environ.get("STATYEARBOOK_BACKEND_TOOL_OUTPUT_MAX_CHARS", "60000")
            ),
            mcp_server_label=os.environ.get(
                "STATYEARBOOK_BACKEND_MCP_SERVER_LABEL", "statyearbook"
            ),
            mcp_url=os.environ.get(
                "STATYEARBOOK_BACKEND_MCP_URL", "http://127.0.0.1:8001/mcp"
            ),
            mcp_call_timeout_seconds=float(
                os.environ.get("STATYEARBOOK_BACKEND_MCP_CALL_TIMEOUT_SECONDS", "90")
            ),
        )

    # 선택한 모델 공급자에 필요한 인증 정보가 준비됐는지 확인한다.
    @property
    def model_configured(self) -> bool:
        if self.model_provider == "openai":
            return bool(self.openai_api_key)
        if self.model_provider == "bizrouter":
            return bool(self.bizrouter_api_key)
        return False


settings = Settings.from_env()
