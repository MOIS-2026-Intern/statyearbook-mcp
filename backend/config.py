# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_args(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return shlex.split(value)


@dataclass(frozen=True)
class Settings:
    app_name: str = "statyearbook-backend"
    host: str = os.environ.get("STATYEARBOOK_BACKEND_HOST", "127.0.0.1")
    port: int = int(os.environ.get("STATYEARBOOK_BACKEND_PORT", "8000"))
    cors_origins: list[str] = None  # type: ignore[assignment]

    model_provider: str = os.environ.get("STATYEARBOOK_MODEL_PROVIDER", "openai").strip().lower()
    chat_model: str = os.environ.get("STATYEARBOOK_CHAT_MODEL", "gpt-5.5")
    model_timeout_seconds: float = float(
        os.environ.get(
            "STATYEARBOOK_MODEL_TIMEOUT_SECONDS",
            os.environ.get("STATYEARBOOK_OPENAI_TIMEOUT_SECONDS", "60"),
        )
    )

    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    bizrouter_api_key: str | None = os.environ.get("BIZROUTER_API_KEY")
    bizrouter_base_url: str = os.environ.get(
        "BIZROUTER_BASE_URL", "https://api.bizrouter.ai/v1"
    ).rstrip("/")
    max_tool_rounds: int = int(os.environ.get("STATYEARBOOK_MAX_TOOL_ROUNDS", "5"))
    tool_output_max_chars: int = int(os.environ.get("STATYEARBOOK_TOOL_OUTPUT_MAX_CHARS", "60000"))

    mcp_server_label: str = os.environ.get("STATYEARBOOK_MCP_SERVER_LABEL", "statyearbook")
    mcp_command: str = os.environ.get("STATYEARBOOK_MCP_COMMAND", sys.executable)
    mcp_args: list[str] = None  # type: ignore[assignment]
    mcp_cwd: str = os.environ.get("STATYEARBOOK_MCP_CWD", str(ROOT_DIR))
    mcp_call_timeout_seconds: float = float(os.environ.get("STATYEARBOOK_MCP_CALL_TIMEOUT_SECONDS", "90"))
    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cors_origins",
            _csv(
                os.environ.get("STATYEARBOOK_BACKEND_CORS_ORIGINS"),
                ["http://localhost:5173", "http://127.0.0.1:5173"],
            ),
        )
        object.__setattr__(
            self,
            "mcp_args",
            _split_args(os.environ.get("STATYEARBOOK_MCP_ARGS"), ["server.py"]),
        )

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_bizrouter_key(self) -> bool:
        return bool(self.bizrouter_api_key)

    @property
    def model_configured(self) -> bool:
        if self.model_provider == "openai":
            return self.has_openai_key
        if self.model_provider == "bizrouter":
            return self.has_bizrouter_key
        if self.model_provider == "local_gemma":
            return False
        return False

    @property
    def openai_model(self) -> str:
        return self.chat_model

    @property
    def openai_timeout_seconds(self) -> float:
        return self.model_timeout_seconds


settings = Settings()
