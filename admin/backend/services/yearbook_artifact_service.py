# -*- coding: utf-8 -*-
from pathlib import Path

from admin.backend.models.ingestion_job_model import ARTIFACT_NAMES
from admin.backend.services.title_embedding_dml_service import TitleEmbeddingDmlWriter
from admin.backend.services.yearbook_load_dml_service import build_load_dml
from admin.backend.services.yearbook_parser_service import parsed_to_markdown, write_json, write_text
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

    def save_load_dml(self, parsed: dict, load_mode: str) -> tuple[str, Path]:
        dml = build_load_dml(parsed, load_mode)
        path = self.workspace / ARTIFACT_NAMES.load_dml
        path.write_text(dml, encoding="utf-8")
        return dml, path

    def embedding_dml_writer(self, profile: EmbeddingProfile) -> TitleEmbeddingDmlWriter:
        return TitleEmbeddingDmlWriter(
            self.workspace / ARTIFACT_NAMES.embedding_dml,
            profile,
        )
