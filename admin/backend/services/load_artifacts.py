# 이 파일은 작업별 파싱 결과, 검수 문서와 두 종류 DML 산출물을 저장한다.
# workspace 파일명 규칙을 통합 적재 service에서 분리한다.
from pathlib import Path

from admin.backend.models.ingestion_job import ARTIFACT_NAMES
from admin.backend.services.load_dml import build_load_dml
from admin.backend.services.load_embedding_dml import (
    TableSearchEmbeddingDmlWriter,
    TitleEmbeddingDmlWriter,
)
from admin.backend.services.load_parser import parsed_to_markdown, write_json, write_text
from utils.embedding import EmbeddingProfile


class YearbookArtifactService:
    # 한 작업공간을 기준으로 모든 검수·적재 산출물 경로를 고정한다.
    def __init__(self, workspace: Path):
        self.workspace = workspace

    # 파싱 결과 JSON과 사람이 검토할 Markdown을 함께 저장한다.
    def save_parsed_outputs(self, parsed: dict) -> dict[str, str]:
        json_path = self.workspace / ARTIFACT_NAMES.parsed_json
        review_path = self.workspace / ARTIFACT_NAMES.review_markdown
        write_json(str(json_path), parsed)
        write_text(str(review_path), parsed_to_markdown(parsed))
        return {
            "parsed_json": json_path.name,
            "review_markdown": review_path.name,
        }

    # 선택한 중복 처리 모드의 적재 DML을 작업공간에 기록한다.
    def save_load_dml(self, parsed: dict, load_mode: str) -> Path:
        dml = build_load_dml(parsed, load_mode)
        path = self.workspace / ARTIFACT_NAMES.load_dml
        path.write_text(dml, encoding="utf-8")
        return path

    # 통계 제목 임베딩을 스트리밍 기록할 writer를 표준 파일명으로 만든다.
    def embedding_dml_writer(self, profile: EmbeddingProfile) -> TitleEmbeddingDmlWriter:
        return TitleEmbeddingDmlWriter(
            self.workspace / ARTIFACT_NAMES.embedding_dml,
            profile,
        )

    # 표 검색 청크 임베딩을 별도 DML 산출물에 기록할 writer를 만든다.
    def table_embedding_dml_writer(
        self,
        profile: EmbeddingProfile,
    ) -> TableSearchEmbeddingDmlWriter:
        return TableSearchEmbeddingDmlWriter(
            self.workspace / ARTIFACT_NAMES.table_embedding_dml,
            profile,
        )
