# 이 파일은 관리자 서비스가 소유하는 프로필, DB와 임베딩 선택지를 구성한다.
from __future__ import annotations

import os

from dataclasses import dataclass
from pathlib import Path

from utils.embedding import BGE_M3_REVISION
from utils.env import load_service_env


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parent
ADMIN_DIR = BACKEND_DIR.parent
ADMIN_API_PREFIX = "/api/admin"
PROFILE = load_service_env(ADMIN_DIR)


# 필수 환경변수를 읽고 누락 시 현재 프로필을 포함한 오류로 즉시 중단한다.
def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required for APP_PROFILE={PROFILE}")
    return value


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
    profile: str = "local"
    host: str = "127.0.0.1"
    port: int = 8100
    api_token: str | None = None
    max_upload_mb: int = 300
    state_dir: Path = ADMIN_DIR / "state"
    workspace_dir: Path = ADMIN_DIR / "workspaces"
    dsn: str = "postgresql:///statyearbook_mcp"
    bge_model_path: str = str(ROOT_DIR / "models" / "bge-m3")

    # 서비스 전용 환경변수를 타입이 지정된 관리자 설정으로 변환한다.
    @classmethod
    def from_env(cls) -> "AdminSettings":
        return cls(
            profile=PROFILE,
            host=os.environ.get("STATYEARBOOK_ADMIN_HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT") or os.environ.get("STATYEARBOOK_ADMIN_PORT", "8100")),
            api_token=os.environ.get("STATYEARBOOK_ADMIN_API_TOKEN"),
            max_upload_mb=int(os.environ.get("STATYEARBOOK_ADMIN_MAX_UPLOAD_MB", "300")),
            state_dir=Path(
                os.environ.get("STATYEARBOOK_ADMIN_STATE_DIR", str(ADMIN_DIR / "state"))
            ),
            workspace_dir=Path(
                os.environ.get(
                    "STATYEARBOOK_ADMIN_WORKSPACE_DIR",
                    str(ADMIN_DIR / "workspaces"),
                )
            ),
            dsn=_required("STATYEARBOOK_ADMIN_DSN"),
            bge_model_path=os.environ.get(
                "STATYEARBOOK_ADMIN_BGE_MODEL_PATH",
                str(ROOT_DIR / "models" / "bge-m3"),
            ),
        )

    # 외부 노출 가능성이 있는 환경에서는 관리자 토큰이 반드시 존재하게 한다.
    def __post_init__(self) -> None:
        if self.profile == "main" and not self.api_token:
            raise RuntimeError("STATYEARBOOK_ADMIN_API_TOKEN is required for APP_PROFILE=main")
        if self.host not in {"127.0.0.1", "localhost", "::1"} and not self.api_token:
            raise RuntimeError("STATYEARBOOK_ADMIN_API_TOKEN is required for a non-loopback host")

    # 관리자 작업 상태를 보관할 SQLite 파일 경로를 반환한다.
    @property
    def db_path(self) -> Path:
        return self.state_dir / "admin_jobs.sqlite3"

    # 프로필별로 허용되는 유일한 데이터베이스 대상을 선택한다.
    @property
    def default_target(self) -> str:
        return "production" if self.profile == "main" else "local"

    # 요청 대상이 현재 프로필과 일치할 때만 연결 문자열을 공개한다.
    def target_dsn(self, target: str) -> str:
        if target != self.default_target:
            raise RuntimeError(
                f"database target {target!r} is disabled for APP_PROFILE={self.profile}"
            )
        return self.dsn

    # 관리자 화면이 표시할 DB 대상과 활성 상태를 직렬화한다.
    def targets(self) -> list[dict]:
        return [
            {
                "id": "local",
                "label": "로컬 검증 DB",
                "enabled": self.default_target == "local",
                "description": "local/test 프로필에서 사용하는 검증 DB입니다.",
            },
            {
                "id": "production",
                "label": "운영 DB",
                "enabled": self.default_target == "production",
                "description": "main 프로필에서만 사용하는 운영 DB입니다.",
            },
        ]

    # 현재 배포에 제공되는 임베딩 처리 선택지를 정의한다.
    def embedding_models(self) -> list[EmbeddingModelOption]:
        return [
            EmbeddingModelOption(
                id="bge-m3",
                label="BGE-M3 (권장)",
                provider="local",
                model=self.bge_model_path,
                dimension=1024,
                revision=BGE_M3_REVISION,
                description="고정된 로컬 모델로 1024차원 검색 임베딩을 생성합니다.",
            ),
            EmbeddingModelOption(
                id="skip",
                label="임베딩 건너뛰기",
                provider=None,
                model=None,
                dimension=None,
                description="파싱과 DB 적재까지만 실행합니다.",
            ),
        ]

    # 활성화된 모델 ID만 설정 객체로 해석해 잘못된 작업 생성을 막는다.
    def embedding_model(self, model_id: str) -> EmbeddingModelOption:
        option = next((item for item in self.embedding_models() if item.id == model_id), None)
        if option is None or not option.enabled:
            raise RuntimeError(f"embedding model is not enabled: {model_id}")
        return option


settings = AdminSettings.from_env()
