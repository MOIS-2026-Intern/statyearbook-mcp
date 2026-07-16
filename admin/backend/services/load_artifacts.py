# 이 파일은 작업별 파싱 결과, 검수 문서와 두 종류 DML 산출물을 저장한다.
# workspace 파일명 규칙을 통합 적재 service에서 분리한다.
from pathlib import Path

from admin.backend.models.ingestion_job import ARTIFACT_NAMES
from admin.backend.services.load_dml import build_load_dml
from admin.backend.services.load_embedding_dml import TitleEmbeddingDmlWriter
from admin.backend.services.load_parser import parsed_to_markdown, write_json, write_text
from app.embedding import EmbeddingProfile


class YearbookArtifactService:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    def save_parsed_outputs(self, parsed: dict) -> dict[str, str]:
        json_path = self.workspace / ARTIFACT_NAMES.parsed_json
        review_path = self.workspace / ARTIFACT_NAMES.review_markdown
        write_json(str(json_path), parsed)
        write_text(str(review_path), parsed_to_markdown(parsed))
        return {
            "parsed_json": json_path.name,
            "review_markdown": review_path.name,
        }

    def save_load_dml(self, parsed: dict, load_mode: str) -> Path:
        dml = build_load_dml(parsed, load_mode)
        path = self.workspace / ARTIFACT_NAMES.load_dml
        path.write_text(dml, encoding="utf-8")
        return path

    def embedding_dml_writer(self, profile: EmbeddingProfile) -> TitleEmbeddingDmlWriter:
        return TitleEmbeddingDmlWriter(
            self.workspace / ARTIFACT_NAMES.embedding_dml,
            profile,
        )
