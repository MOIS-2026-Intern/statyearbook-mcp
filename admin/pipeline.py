# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import traceback
import zipfile

from dataclasses import asdict, dataclass
from pathlib import Path

from app.embedding import (
    STATISTICS_CONTENT_VERSION,
    EmbeddingSettings,
    create_embedding_profile,
    create_embedding_provider,
)
from admin.config import AdminSettings
from admin.job_store import AdminJobStore
from load.embedding_dml import EmbeddingDmlWriter
from load.embedding_pipeline import EmbeddingRunner
from load.parse_hwpx_yearbook import parse, parsed_to_markdown, write_json, write_text
from load.statistics_embedding_source import StatisticsEmbeddingSource
from load.yearbook_dml import build_load_dml, execute_dml


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


class AdminIngestionService:
    def __init__(self, settings: AdminSettings, store: AdminJobStore):
        self.settings = settings
        self.store = store

    def _step(self, job_id: str, stage: str, progress: int, message: str) -> None:
        self.store.update(
            job_id,
            status="running",
            stage=stage,
            progress=progress,
            message=message,
        )
        self.store.add_event(job_id, stage, message)

    def run(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        options = IngestionOptions(**job["options"])
        workspace = self.settings.workspace_dir / job_id
        workspace.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, str] = {}
        try:
            input_path = Path(options.input_path)
            self._step(job_id, "validate", 3, "업로드 파일과 대상 환경을 확인하고 있습니다.")
            if input_path.suffix.lower() != ".hwpx" or not zipfile.is_zipfile(input_path):
                raise ValueError("유효한 HWPX 파일이 아닙니다.")
            dsn = self.settings.target_dsn(options.target)

            self._step(job_id, "parse", 10, "HWPX 구조와 통계표를 파싱하고 있습니다.")
            image_dir = str(workspace / "images") if options.extract_images else None
            parsed = parse(
                str(input_path),
                image_dir=image_dir,
                publication_year=options.year,
                publication_title=options.title,
                publication_no=options.pub_no,
            )
            parsed_json = workspace / "parsed_yearbook.json"
            review_md = workspace / "parsed_yearbook.md"
            write_json(str(parsed_json), parsed)
            write_text(str(review_md), parsed_to_markdown(parsed))
            artifacts.update(parsed_json=parsed_json.name, review_markdown=review_md.name)
            self.store.update(job_id, artifacts=artifacts)

            self._step(job_id, "load_dml", 38, "누적 적재용 SQL을 생성하고 있습니다.")
            load_sql = workspace / "load.sql"
            load_dml = build_load_dml(parsed, options.load_mode)
            load_sql.write_text(load_dml, encoding="utf-8")
            artifacts["load_dml"] = load_sql.name
            self.store.update(job_id, artifacts=artifacts)

            self._step(job_id, "load_db", 48, f"{options.target} DB에 {options.year}년 연보를 적재하고 있습니다.")
            execute_dml(dsn, load_dml)

            embedding_profile_key = None
            embedding_count = 0
            if options.embedding_model != "skip":
                model = self.settings.embedding_model(options.embedding_model)
                embed_settings = EmbeddingSettings(
                    provider=str(model.provider),
                    model=str(model.model),
                    dimension=int(model.dimension),
                    batch_size=16,
                    device=model.device,
                    max_length=512,
                    revision=model.revision,
                )
                profile = create_embedding_profile(embed_settings, STATISTICS_CONTENT_VERSION)
                provider = create_embedding_provider(embed_settings)
                source = StatisticsEmbeddingSource(options.year)
                runner = EmbeddingRunner(provider, profile, source)
                embedding_sql = workspace / "embeddings.sql"
                writer = EmbeddingDmlWriter(embedding_sql, profile)
                artifacts["embedding_dml"] = embedding_sql.name
                self.store.update(job_id, artifacts=artifacts)
                self._step(job_id, "embedding", 60, "제목 임베딩을 생성하고 DB에 저장하고 있습니다.")
                try:
                    import psycopg
                    from psycopg.rows import dict_row

                    with psycopg.connect(dsn, row_factory=dict_row) as conn:
                        result = runner.run(
                            conn,
                            batch_size=embed_settings.batch_size,
                            progress=lambda done, total: self.store.update(
                                job_id,
                                progress=60 + int(32 * done / max(total, 1)),
                                message=f"제목 임베딩 {done}/{total}",
                            ),
                            on_batch=writer.write_batch,
                        )
                    writer.complete()
                except Exception as exc:
                    writer.abort(exc)
                    raise
                embedding_profile_key = result.profile_key
                embedding_count = result.processed_count
                self.store.update(
                    job_id,
                    progress=93,
                    message="생성된 임베딩 SQL을 DB에 적용하고 있습니다.",
                )
                execute_dml(dsn, embedding_sql.read_text(encoding="utf-8"))

            self._step(job_id, "verify", 95, "적재 건수와 임베딩 profile을 검증하고 있습니다.")
            verification = self._verify(dsn, options.year, embedding_profile_key)
            result_payload = {
                "publication_year": options.year,
                "publication_title": options.title,
                "embedding_count": embedding_count,
                "embedding_profile_key": embedding_profile_key,
                **verification,
            }
            self.store.update(
                job_id,
                status="completed",
                stage="completed",
                progress=100,
                message="파싱, 적재, 임베딩과 검증이 모두 완료되었습니다.",
                artifacts=artifacts,
                result=result_payload,
            )
            self.store.add_event(job_id, "completed", "모든 단계가 완료되었습니다.")
            return self.store.get(job_id)
        except Exception as exc:
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self.store.update(
                job_id,
                status="failed",
                stage=self.store.get(job_id)["stage"],
                message="작업이 중단되었습니다.",
                error=detail[-12000:],
                artifacts=artifacts,
            )
            self.store.add_event(job_id, self.store.get(job_id)["stage"], str(exc), "error")
            return self.store.get(job_id)

    def _verify(self, dsn: str, year: int, profile_key: str | None) -> dict:
        import psycopg

        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS statistics_count,
                       COALESCE(SUM((SELECT COUNT(*) FROM stat_tables t WHERE t.stat_id = s.stat_id)), 0)
                FROM statistics s WHERE s.year = %s
                """,
                (year,),
            )
            statistics_count, table_count = cur.fetchone()
            current_count = 0
            if profile_key:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM statistics
                    WHERE year = %s AND embedding IS NOT NULL AND embedding_profile_key = %s
                    """,
                    (year, profile_key),
                )
                current_count = cur.fetchone()[0]
        if profile_key and current_count != statistics_count:
            raise RuntimeError(
                f"embedding verification failed: {current_count}/{statistics_count}"
            )
        return {
            "statistics_count": int(statistics_count),
            "table_count": int(table_count),
            "verified_embedding_count": int(current_count),
        }
