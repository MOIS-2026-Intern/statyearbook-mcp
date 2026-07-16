# 이 파일은 로컬에서 검수한 적재·임베딩 DML을 운영 DB에 승격한다.
# 확인 연도와 최종 적재 건수를 검증한 뒤 작업 이벤트를 기록한다.
import psycopg

from admin.backend.config import AdminSettings
from admin.backend.repositories.admin_job_repository import AdminJobRepository
from admin.backend.repositories.postgres_dml_repository import PostgresDmlRepository


class ProductionPromotionService:
    def __init__(
        self,
        settings: AdminSettings,
        repository: AdminJobRepository,
        dml_repository: PostgresDmlRepository | None = None,
    ):
        self.settings = settings
        self.repository = repository
        self.dml_repository = dml_repository or PostgresDmlRepository()

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
        self.dml_repository.execute_file(dsn, load_dml_path)
        if embedding_dml_name:
            self.dml_repository.execute_file(dsn, workspace / embedding_dml_name)

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
