# 이 파일은 PostgreSQL의 임베딩 profile과 batch job 이력을 관리한다.
# advisory lock으로 동시에 두 임베딩 작업이 실행되지 않도록 한다.
from utils.embedding import EmbeddingProfile


EMBEDDING_JOB_LOCK_ID = 7_824_601_024


# tuple과 dict 형식의 psycopg 행에서 첫 스칼라 값을 동일하게 꺼낸다.
def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class EmbeddingJobRepository:
    # 데이터베이스 전역 advisory lock을 획득해 임베딩 작업 중복 실행을 막는다.
    def acquire_lock(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (EMBEDDING_JOB_LOCK_ID,))
            acquired = _first_value(cur.fetchone())
        if not acquired:
            raise RuntimeError("another embedding job is already running")

    # 작업 종료 후 세션 advisory lock을 명시적으로 해제한다.
    def release_lock(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (EMBEDDING_JOB_LOCK_ID,))

    # 동일 profile key의 모델 메타데이터를 최초 한 번만 등록한다.
    def insert_embedding_profile(self, conn, profile: EmbeddingProfile) -> None:
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

    # 처리 범위가 고정된 실행 이력을 생성하고 새 작업 ID를 반환한다.
    def insert_embedding_job(
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

    # 완료된 배치 수를 실행 이력에 반영한다.
    def update_embedding_job_progress(self, conn, job_id: int, processed_count: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE embedding_jobs SET processed_count = %s WHERE job_id = %s",
                (processed_count, job_id),
            )

    # 정상 종료 상태, 최종 처리 수와 완료 시각을 함께 기록한다.
    def update_embedding_job_completed(self, conn, job_id: int, processed_count: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE embedding_jobs
                SET status = 'completed', processed_count = %s, finished_at = now()
                WHERE job_id = %s
                """,
                (processed_count, job_id),
            )

    # 실패 시 진행량과 길이가 제한된 오류 메시지를 실행 이력에 남긴다.
    def update_embedding_job_failed(
        self,
        conn,
        job_id: int,
        processed_count: int,
        error: Exception,
    ) -> None:
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
