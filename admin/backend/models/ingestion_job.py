# 이 파일은 통합 적재 작업 옵션과 workspace 산출물 파일명 계약을 정의한다.
# CLI와 웹 API가 같은 모델과 파일명 규칙을 공유하도록 한다.
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class IngestionOptions:
    input_path: str
    original_filename: str
    year: int
    title: str
    pub_no: str | None = None
    target: str = "local"
    load_mode: str = "reject"
    embedding_model: str = "bge-m3"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceArtifactNames:
    source_yearbook: str = "yearbook_source.hwpx"
    parsed_json: str = "yearbook_parsed.json"
    review_markdown: str = "yearbook_review.md"
    schema_ddl: str = "yearbook_schema.sql"
    load_dml: str = "yearbook_load.sql"
    embedding_dml: str = "yearbook_title_embeddings.sql"
    table_embedding_dml: str = "yearbook_table_search_embeddings.sql"


ARTIFACT_NAMES = WorkspaceArtifactNames()
