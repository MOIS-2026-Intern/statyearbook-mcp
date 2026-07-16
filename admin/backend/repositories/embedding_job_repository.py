# 이 파일은 PostgreSQL의 임베딩 profile과 batch job 이력을 관리한다.
# advisory lock으로 동시에 두 임베딩 작업이 실행되지 않도록 한다.
from app.embedding import EmbeddingProfile


EMBEDDING_JOB_LOCK_ID = 7_824_601_024


def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class EmbeddingJobRepository:
    def acquire_lock(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (EMBEDDING_JOB_LOCK_ID,))
            acquired = _first_value(cur.fetchone())
        if not acquired:
            raise RuntimeError("another embedding job is already running")

    def release_lock(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (EMBEDDING_JOB_LOCK_ID,))

    def register_profile(self, conn, profile: EmbeddingProfile) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO embedding_profiles (
                    profile_key, provider, model, revision, dimension,
                    max_length, content_version, normalized
                )
                VALUES (
                    %(profile_key)s, %(provider)s, %(model)s, %(revision)s,
                    %(dimension)s, %(max_length)s, %(content_version)s, %(normalized)s
                )
                ON CONFLICT (profile_key) DO NOTHING
                """,
                profile.as_record(),
            )

    def create_job(
        self,
        conn,
        source_name: str,
        profile_key: str,
        force: bool,
        target_count: int,
        max_source_id: int,
    ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO embedding_jobs (
                    source_name, profile_key, status, force_reembed,
                    target_count, max_source_id
                )
                VALUES (%s, %s, 'running', %s, %s, %s)
                RETURNING job_id
                """,
                (source_name, profile_key, force, target_count, max_source_id),
            )
            return int(_first_value(cur.fetchone()))

    def update_progress(self, conn, job_id: int, processed_count: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE embedding_jobs SET processed_count = %s WHERE job_id = %s",
                (processed_count, job_id),
            )

    def complete_job(self, conn, job_id: int, processed_count: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE embedding_jobs
                SET status = 'completed', processed_count = %s, finished_at = now()
                WHERE job_id = %s
                """,
                (processed_count, job_id),
            )

    def fail_job(self, conn, job_id: int, processed_count: int, error: Exception) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE embedding_jobs
                SET status = 'failed', processed_count = %s,
                    error_message = %s, finished_at = now()
                WHERE job_id = %s
                """,
                (processed_count, str(error)[:4000], job_id),
            )

    def latest_jobs(self, conn, source_name: str, limit: int = 5) -> list[dict]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_id, status, target_count, processed_count,
                       started_at, finished_at, error_message
                FROM embedding_jobs
                WHERE source_name = %s
                ORDER BY job_id DESC
                LIMIT %s
                """,
                (source_name, limit),
            )
            return cur.fetchall()
