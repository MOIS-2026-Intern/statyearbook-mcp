# -*- coding: utf-8 -*-
"""MCP app이 소유하는 DB와 검색 임베딩 설정."""
from __future__ import annotations

import os

from dataclasses import dataclass
from pathlib import Path

from utils.embedding import (
    BGE_M3_REVISION,
    EmbeddingConfigurationError,
    EmbeddingSettings,
    create_embedding_provider,
)
from utils.env import load_service_env


APP_DIR = Path(__file__).resolve().parent
PROFILE = load_service_env(APP_DIR)


# 필수 앱 환경변수를 읽고 누락 시 현재 프로필을 포함한 오류를 낸다.
def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required for APP_PROFILE={PROFILE}")
    return value


# 환경변수의 정수 값을 읽어 양수인지 검증한다.
def _positive_int(name: str, default: str | None = None) -> int:
    raw_value = os.environ.get(name, default)
    if raw_value is None:
        raise EmbeddingConfigurationError(f"{name} is required")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise EmbeddingConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise EmbeddingConfigurationError(f"{name} must be greater than zero")
    return value


# 로컬 BGE-M3 기본값과 서비스 전용 override로 임베딩 설정을 구성한다.
def embedding_settings_from_env() -> EmbeddingSettings:
    model = os.environ.get("STATYEARBOOK_APP_EMBED_MODEL", "models/bge-m3")
    return EmbeddingSettings(
        provider="local",
        model=model,
        dimension=1024,
        batch_size=_positive_int("STATYEARBOOK_APP_EMBED_BATCH_SIZE", "16"),
        device=os.environ.get("STATYEARBOOK_APP_EMBED_DEVICE", "cpu"),
        max_length=512,
        revision=BGE_M3_REVISION,
    )


@dataclass(frozen=True)
class AppSettings:
    profile: str
    dsn: str
    embedding: EmbeddingSettings
    host: str
    port: int

    # 운영 app은 고정 BGE-M3 artifact의 경로·차원·revision을 시작 시 검증한다.
    def __post_init__(self) -> None:
        if self.profile != "main":
            return
        create_embedding_provider(self.embedding)

    # 현재 프로필의 환경변수를 불변 앱 설정 객체로 묶는다.
    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            profile=PROFILE,
            dsn=_required("STATYEARBOOK_APP_DSN"),
            embedding=embedding_settings_from_env(),
            host=os.environ.get("STATYEARBOOK_APP_HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT") or os.environ.get("STATYEARBOOK_APP_PORT", "8001")),
        )


settings = AppSettings.from_env()
