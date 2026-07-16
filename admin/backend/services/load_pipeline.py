# 이 파일은 검증, 파싱, DML 적재, 제목 임베딩과 결과 확인 단계를 조율한다.
# CLI와 웹 API가 함께 사용하는 관리자 통합 적재 application service다.
from __future__ import annotations

import traceback
import zipfile

from pathlib import Path

from app.embedding import (
    STATISTICS_CONTENT_VERSION,
    EmbeddingSettings,
    create_embedding_profile,
    create_embedding_provider,
)
from admin.backend.config import AdminSettings
from admin.backend.models.ingestion_job import IngestionOptions
from admin.backend.repositories.admin_jobs import AdminJobRepository
from admin.backend.repositories.postgres_dml import PostgresDmlRepository
from admin.backend.repositories.statistics_embeddings import StatisticsEmbeddingRepository
from admin.backend.services.load_artifacts import YearbookArtifactService
from admin.backend.services.load_embedding import EmbeddingRunner
from admin.backend.services.load_parser import parse
from admin.backend.services.load_verification import YearbookVerificationService


class YearbookIngestionService:
    def __init__(
        self,
        settings: AdminSettings,
        store: AdminJobRepository,
        verification: YearbookVerificationService | None = None,
        dml_repository: PostgresDmlRepository | None = None,
    ):
        self.settings = settings
        self.store = store
        self.verification = verification or YearbookVerificationService()
        self.dml_repository = dml_repository or PostgresDmlRepository()

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
        artifact_service = YearbookArtifactService(workspace)
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
            artifacts.update(artifact_service.save_parsed_outputs(parsed))
            self.store.update(job_id, artifacts=artifacts)

            self._step(job_id, "load_dml", 38, "누적 적재용 SQL을 생성하고 있습니다.")
            load_sql = artifact_service.save_load_dml(parsed, options.load_mode)
            artifacts["load_dml"] = load_sql.name
            self.store.update(job_id, artifacts=artifacts)

            self._step(job_id, "load_db", 48, f"{options.target} DB에 {options.year}년 연보를 적재하고 있습니다.")
            self.dml_repository.execute_file(dsn, load_sql)

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
                source = StatisticsEmbeddingRepository(options.year)
                runner = EmbeddingRunner(provider, profile, source)
                writer = artifact_service.embedding_dml_writer(profile)
                embedding_sql = writer.path
                artifacts["embedding_dml"] = embedding_sql.name
                self.store.update(job_id, artifacts=artifacts)
                self._step(
                    job_id,
                    "embedding_dml",
                    60,
                    "제목 벡터와 임베딩 적재 SQL을 생성하고 있습니다.",
                )
                try:
                    import psycopg
                    from psycopg.rows import dict_row

                    with psycopg.connect(dsn, row_factory=dict_row) as conn:
                        result = runner.run(
                            conn,
                            batch_size=embed_settings.batch_size,
                            mode="dml",
                            progress=lambda done, total: self.store.update(
                                job_id,
                                progress=60 + int(28 * done / max(total, 1)),
                                message=f"임베딩 적재 SQL 생성 {done}/{total}",
                            ),
                            on_batch=writer.write_batch,
                        )
                    writer.complete(
                        source_name=source.name,
                        target_count=result.target_count,
                        processed_count=result.processed_count,
                        max_source_id=result.max_source_id,
                    )
                except Exception as exc:
                    writer.abort(exc)
                    raise
                embedding_profile_key = result.profile_key
                embedding_count = result.processed_count
                self._step(
                    job_id,
                    "embedding_db",
                    90,
                    f"생성된 임베딩 SQL을 {options.target} DB에 실행하고 있습니다.",
                )
                self.dml_repository.execute_file(dsn, embedding_sql)

            self._step(job_id, "verify", 95, "적재 건수와 임베딩 profile을 검증하고 있습니다.")
            verification = self.verification.verify(
                dsn,
                options.year,
                embedding_profile_key,
            )
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
