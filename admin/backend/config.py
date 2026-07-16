# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.embedding import BGE_M3_REVISION


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parent
ADMIN_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ADMIN_DIR / ".env.admin", override=True)


@dataclass(frozen=True)
class EmbeddingModelOption:
    id: str
    label: str
    provider: str | None
    model: str | None
    dimension: int | None
    revision: str | None = None
    device: str = "cpu"
    enabled: bool = True
    description: str = ""


@dataclass(frozen=True)
class AdminSettings:
    host: str = os.environ.get("STATYEARBOOK_ADMIN_HOST", "127.0.0.1")
    port: int = int(os.environ.get("STATYEARBOOK_ADMIN_PORT", "8100"))
    api_token: str | None = os.environ.get("STATYEARBOOK_ADMIN_API_TOKEN")
    max_upload_mb: int = int(os.environ.get("STATYEARBOOK_ADMIN_MAX_UPLOAD_MB", "300"))
    state_dir: Path = Path(
        os.environ.get("STATYEARBOOK_ADMIN_STATE_DIR", str(ADMIN_DIR / "state"))
    )
    workspace_dir: Path = Path(
        os.environ.get("STATYEARBOOK_ADMIN_WORKSPACE_DIR", str(ADMIN_DIR / "workspaces"))
    )
    local_dsn: str | None = os.environ.get("STATYEARBOOK_ADMIN_LOCAL_DSN") or os.environ.get(
        "STATYEARBOOK_DSN"
    )
    production_dsn: str | None = os.environ.get("STATYEARBOOK_ADMIN_PRODUCTION_DSN")
    enable_production_target: bool = (
        os.environ.get("STATYEARBOOK_ADMIN_ENABLE_PRODUCTION_TARGET", "false").lower()
        == "true"
    )
    bge_model_path: str = os.environ.get(
        "STATYEARBOOK_ADMIN_BGE_MODEL_PATH", str(ROOT_DIR / "models" / "bge-m3")
    )

    def __post_init__(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        if self.host not in {"127.0.0.1", "localhost", "::1"} and not self.api_token:
            raise RuntimeError("STATYEARBOOK_ADMIN_API_TOKEN is required for a non-loopback host")

    @property
    def db_path(self) -> Path:
        return self.state_dir / "admin_jobs.sqlite3"

    def target_dsn(self, target: str) -> str:
        if target == "local" and self.local_dsn:
            return self.local_dsn
        if target == "production" and self.enable_production_target and self.production_dsn:
            return self.production_dsn
        raise RuntimeError(f"database target is not enabled: {target}")

    def targets(self) -> list[dict]:
        return [
            {
                "id": "local",
                "label": "로컬 검증 DB",
                "enabled": bool(self.local_dsn),
                "description": "관리자 로컬 환경에서 파싱·적재·검색을 먼저 검증합니다.",
            },
            {
                "id": "production",
                "label": "운영 DB",
                "enabled": bool(self.enable_production_target and self.production_dsn),
                "description": "환경변수로 명시적으로 허용한 경우에만 선택할 수 있습니다.",
            },
        ]

    def embedding_models(self) -> list[EmbeddingModelOption]:
        return [
            EmbeddingModelOption(
                id="bge-m3",
                label="BGE-M3 (로컬·권장)",
                provider="local",
                model=self.bge_model_path,
                dimension=1024,
                revision=BGE_M3_REVISION,
                description="인터넷 없이 로컬 모델로 1024차원 제목 임베딩을 생성합니다.",
            ),
            EmbeddingModelOption(
                id="skip",
                label="임베딩 건너뛰기",
                provider=None,
                model=None,
                dimension=None,
                description="파싱과 DB 적재까지만 실행하고 이후 별도 작업에서 임베딩합니다.",
            ),
            EmbeddingModelOption(
                id="openai-small",
                label="OpenAI text-embedding-3-small",
                provider="openai",
                model="text-embedding-3-small",
                dimension=1536,
                enabled=False,
                description="현재 DB가 vector(1024)이므로 별도 차원 migration 전에는 선택할 수 없습니다.",
            ),
        ]

    def embedding_model(self, model_id: str) -> EmbeddingModelOption:
        option = next((item for item in self.embedding_models() if item.id == model_id), None)
        if option is None or not option.enabled:
            raise RuntimeError(f"embedding model is not enabled: {model_id}")
        return option


settings = AdminSettings()
