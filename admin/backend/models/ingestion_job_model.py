# -*- coding: utf-8 -*-
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
    extract_images: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceArtifactNames:
    source_yearbook: str = "yearbook_source.hwpx"
    parsed_json: str = "yearbook_parsed.json"
    review_markdown: str = "yearbook_review.md"
    load_dml: str = "yearbook_load.sql"
    embedding_dml: str = "yearbook_title_embeddings.sql"


ARTIFACT_NAMES = WorkspaceArtifactNames()
