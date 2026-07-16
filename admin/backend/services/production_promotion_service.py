# -*- coding: utf-8 -*-
import psycopg

from admin.backend.config import AdminSettings
from admin.backend.repositories.admin_job_repository import AdminJobRepository
from admin.backend.services.yearbook_load_dml_service import execute_dml


class ProductionPromotionService:
    def __init__(self, settings: AdminSettings, repository: AdminJobRepository):
        self.settings = settings
        self.repository = repository

    def promote(self, job_id: str, confirmed_year: int) -> dict:
        try:
            job = self.repository.get(job_id)
        except KeyError as exc:
            raise RuntimeError(f"job not found: {job_id}") from exc
        if job["status"] != "completed":
            raise RuntimeError("only a completed job can be promoted")
        year = int(job["options"]["year"])
        if confirmed_year != year:
            raise RuntimeError(f"confirmed year must be {year}")

        dsn = self.settings.target_dsn("production")
        workspace = self.settings.workspace_dir / job_id
        load_dml_path = workspace / job["artifacts"]["load_dml"]
        embedding_dml_name = job["artifacts"].get("embedding_dml")
        execute_dml(dsn, load_dml_path.read_text(encoding="utf-8"))
        if embedding_dml_name:
            execute_dml(
                dsn,
                (workspace / embedding_dml_name).read_text(encoding="utf-8"),
            )

        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COUNT(embedding) FROM statistics WHERE year = %s",
                (year,),
            )
            statistics_count, embedding_count = cur.fetchone()
        expected_statistics = int(
            job["result"].get("statistics_count", statistics_count)
        )
        expected_embeddings = int(
            job["result"].get("verified_embedding_count", embedding_count)
        )
        if statistics_count != expected_statistics or embedding_count != expected_embeddings:
            raise RuntimeError(
                "production verification failed: "
                f"statistics={statistics_count}/{expected_statistics}, "
                f"embeddings={embedding_count}/{expected_embeddings}"
            )
        result = {
            "job_id": job_id,
            "year": year,
            "statistics_count": int(statistics_count),
            "embedding_count": int(embedding_count),
        }
        self.repository.add_event(
            job_id,
            "production",
            "운영 DB 적용 완료: "
            f"statistics={statistics_count}, embeddings={embedding_count}",
        )
        return result
