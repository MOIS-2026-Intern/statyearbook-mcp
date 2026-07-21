# 이 파일은 날짜·시간 기반 workspace ID 생성과 과거 UUID 작업 이관을 담당한다.
# 기존 작업 파일명, SQLite ID와 저장 경로를 손실 없이 새 규칙으로 변경한다.
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

from admin.backend.models.ingestion_job import ARTIFACT_NAMES
from admin.backend.repositories.admin_jobs import AdminJobRepository


WORKSPACE_ID_FORMAT = "%Y%m%d-%H%M%S-%f"
LEGACY_WORKSPACE_ID = re.compile(r"^[0-9a-f]{32}$")
LEGACY_ARTIFACT_NAMES = {
    "source.hwpx": ARTIFACT_NAMES.source_yearbook,
    "parsed_yearbook.json": ARTIFACT_NAMES.parsed_json,
    "parsed_yearbook.md": ARTIFACT_NAMES.review_markdown,
    "load.sql": ARTIFACT_NAMES.load_dml,
    "embeddings.sql": ARTIFACT_NAMES.embedding_dml,
}


# 정렬 가능하면서 마이크로초까지 구분되는 로컬 시각 기반 작업 ID를 만든다.
def create_workspace_id(now: datetime | None = None) -> str:
    timestamp = now or datetime.now().astimezone()
    return timestamp.strftime(WORKSPACE_ID_FORMAT)


# 중복 생성을 허용하지 않는 새 작업 디렉터리를 만들고 ID와 경로를 반환한다.
def create_workspace(root: Path, now: datetime | None = None) -> tuple[str, Path]:
    workspace_id = create_workspace_id(now)
    workspace = root / workspace_id
    workspace.mkdir(parents=True, exist_ok=False)
    return workspace_id, workspace


# UUID 기반 과거 작업과 산출물 이름을 현재 규칙으로 손실 없이 이관한다.
def migrate_legacy_workspaces(
    root: Path,
    repository: AdminJobRepository,
) -> list[tuple[str, str]]:
    migrated = []
    for job in repository.select_jobs(limit=10_000):
        old_id = job["job_id"]
        if not LEGACY_WORKSPACE_ID.fullmatch(old_id):
            continue
        created_at = datetime.fromisoformat(job["created_at"]).astimezone()
        new_id = create_workspace_id(created_at)
        old_workspace = root / old_id
        new_workspace = root / new_id
        if old_workspace.exists():
            old_workspace.rename(new_workspace)
        options = dict(job["options"])
        old_input = Path(options.get("input_path") or "")
        new_source = new_workspace / ARTIFACT_NAMES.source_yearbook
        if old_input.name in LEGACY_ARTIFACT_NAMES:
            options["input_path"] = str(new_source)

        artifacts = dict(job["artifacts"])
        for key, old_name in list(artifacts.items()):
            new_name = LEGACY_ARTIFACT_NAMES.get(old_name, old_name)
            old_path = new_workspace / old_name
            new_path = new_workspace / new_name
            if old_path.exists() and old_path != new_path:
                old_path.rename(new_path)
            artifacts[key] = new_name
        legacy_source = new_workspace / old_input.name
        if legacy_source.exists() and legacy_source != new_source:
            legacy_source.rename(new_source)

        parsed_path = new_workspace / ARTIFACT_NAMES.parsed_json
        if parsed_path.is_file():
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            if isinstance(parsed.get("metadata"), dict):
                parsed["metadata"]["source"] = str(new_source)
                parsed_path.write_text(
                    json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        repository.update_job_identity(old_id, new_id, options, artifacts)
        migrated.append((old_id, new_id))
    return migrated
