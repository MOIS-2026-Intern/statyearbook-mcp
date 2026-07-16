# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from app.embedding import EmbeddingProfile, EmbeddingProvider


EMBEDDING_JOB_LOCK_ID = 7_824_601_024


def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


@dataclass(frozen=True)
class EmbeddingBatch:
    rows: list[dict]
    last_source_id: int


@dataclass(frozen=True)
class EmbeddingRunResult:
    job_id: int | None
    target_count: int
    processed_count: int
    profile_key: str
    dry_run: bool


class EmbeddingSource(Protocol):
    name: str

    def validate_dimension(self, conn, expected_dimension: int) -> None:
        ...

    def snapshot_max_id(self, conn) -> int:
        ...

    def count_candidates(
        self,
        conn,
        profile_key: str,
        force: bool,
        max_source_id: int,
    ) -> int:
        ...

    def fetch_batch(
        self,
        conn,
        profile_key: str,
        force: bool,
        after_source_id: int,
        max_source_id: int,
        batch_size: int,
    ) -> EmbeddingBatch:
        ...

    def texts(self, rows: list[dict]) -> list[str]:
        ...

    def save_batch(
        self,
        conn,
        rows: list[dict],
        vectors: list[list[float]],
        profile_key: str,
    ) -> None:
        ...


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
        record = profile.as_record()
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
                record,
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


class EmbeddingRunner:
    def __init__(
        self,
        provider: EmbeddingProvider,
        profile: EmbeddingProfile,
        source: EmbeddingSource,
        jobs: EmbeddingJobRepository | None = None,
    ):
        self.provider = provider
        self.profile = profile
        self.source = source
        self.jobs = jobs or EmbeddingJobRepository()

    def run(
        self,
        conn,
        batch_size: int,
        force: bool = False,
        dry_run: bool = False,
        progress: Callable[[int, int], None] | None = None,
    ) -> EmbeddingRunResult:
        self.source.validate_dimension(conn, self.profile.dimension)
        self.jobs.acquire_lock(conn)
        job_id = None
        processed = 0
        try:
            max_source_id = self.source.snapshot_max_id(conn)
            target_count = self.source.count_candidates(
                conn,
                self.profile.profile_key,
                force,
                max_source_id,
            )
            if dry_run:
                conn.rollback()
                return EmbeddingRunResult(
                    job_id=None,
                    target_count=target_count,
                    processed_count=0,
                    profile_key=self.profile.profile_key,
                    dry_run=True,
                )

            self.jobs.register_profile(conn, self.profile)
            job_id = self.jobs.create_job(
                conn,
                self.source.name,
                self.profile.profile_key,
                force,
                target_count,
                max_source_id,
            )
            conn.commit()

            after_source_id = 0
            while processed < target_count:
                batch = self.source.fetch_batch(
                    conn,
                    self.profile.profile_key,
                    force,
                    after_source_id,
                    max_source_id,
                    batch_size,
                )
                if not batch.rows:
                    break
                vectors = self.provider.encode(self.source.texts(batch.rows))
                self.source.save_batch(
                    conn,
                    batch.rows,
                    vectors,
                    self.profile.profile_key,
                )
                processed += len(batch.rows)
                after_source_id = batch.last_source_id
                self.jobs.update_progress(conn, job_id, processed)
                conn.commit()
                if progress:
                    progress(processed, target_count)

            if processed != target_count:
                raise RuntimeError(
                    f"embedding candidate count changed: expected {target_count}, processed {processed}"
                )
            self.jobs.complete_job(conn, job_id, processed)
            conn.commit()
            return EmbeddingRunResult(
                job_id=job_id,
                target_count=target_count,
                processed_count=processed,
                profile_key=self.profile.profile_key,
                dry_run=False,
            )
        except Exception as exc:
            conn.rollback()
            if job_id is not None:
                self.jobs.fail_job(conn, job_id, processed, exc)
                conn.commit()
            raise
        finally:
            self.jobs.release_lock(conn)
            conn.commit()
