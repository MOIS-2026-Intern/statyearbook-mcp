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


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "statyearbook-backend"
    host: str = os.environ.get("STATYEARBOOK_BACKEND_HOST", "127.0.0.1")
    port: int = int(os.environ.get("STATYEARBOOK_BACKEND_PORT", "8000"))
    cors_origins: list[str] = None  # type: ignore[assignment]

    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    openai_model: str = os.environ.get("STATYEARBOOK_CHAT_MODEL", "gpt-5.5")
    openai_timeout_seconds: float = float(os.environ.get("STATYEARBOOK_OPENAI_TIMEOUT_SECONDS", "60"))
    max_tool_rounds: int = int(os.environ.get("STATYEARBOOK_MAX_TOOL_ROUNDS", "4"))
    tool_output_max_chars: int = int(os.environ.get("STATYEARBOOK_TOOL_OUTPUT_MAX_CHARS", "60000"))

    mcp_server_label: str = os.environ.get("STATYEARBOOK_MCP_SERVER_LABEL", "statyearbook")
    mcp_command: str = os.environ.get("STATYEARBOOK_MCP_COMMAND", sys.executable)
    mcp_args: list[str] = None  # type: ignore[assignment]
    mcp_cwd: str = os.environ.get("STATYEARBOOK_MCP_CWD", str(ROOT_DIR))
    mcp_call_timeout_seconds: float = float(os.environ.get("STATYEARBOOK_MCP_CALL_TIMEOUT_SECONDS", "90"))
    force_visualize_without_inline_image: bool = _bool_env("STATYEARBOOK_FORCE_VISUALIZE_NO_INLINE_IMAGE", True)

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


settings = Settings()
