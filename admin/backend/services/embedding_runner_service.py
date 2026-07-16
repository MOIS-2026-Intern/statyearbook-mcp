# 이 파일은 임베딩 provider와 데이터 repository를 batch 단위로 연결해 실행한다.
# DB 직접 저장과 DML 전용 생성 모드를 분리해 호출자가 적재 방식을 선택하게 한다.
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from admin.backend.repositories.embedding_job_repository import EmbeddingJobRepository
from app.embedding import EmbeddingProfile, EmbeddingProvider



@dataclass(frozen=True)
class EmbeddingBatch:
    rows: list[dict]
    last_source_id: int


@dataclass(frozen=True)
class EmbeddingRunResult:
    job_id: int | None
    target_count: int
    processed_count: int
    max_source_id: int
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
        mode: Literal["database", "dml"] = "database",
        progress: Callable[[int, int], None] | None = None,
        on_batch: Callable[[list[dict], list[list[float]], EmbeddingProfile], None] | None = None,
    ) -> EmbeddingRunResult:
        if mode not in {"database", "dml"}:
            raise ValueError(f"unsupported embedding run mode: {mode}")
        if mode == "dml" and on_batch is None and not dry_run:
            raise ValueError("on_batch is required when embedding run mode is dml")

        writes_database = mode == "database"
        self.source.validate_dimension(conn, self.profile.dimension)
        if writes_database:
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
                    max_source_id=max_source_id,
                    profile_key=self.profile.profile_key,
                    dry_run=True,
                )

            if writes_database:
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
                if on_batch:
                    on_batch(batch.rows, vectors, self.profile)
                if writes_database:
                    self.source.save_batch(
                        conn,
                        batch.rows,
                        vectors,
                        self.profile.profile_key,
                    )
                processed += len(batch.rows)
                after_source_id = batch.last_source_id
                if writes_database:
                    self.jobs.update_progress(conn, job_id, processed)
                    conn.commit()
                if progress:
                    progress(processed, target_count)

            if processed != target_count:
                raise RuntimeError(
                    f"embedding candidate count changed: expected {target_count}, processed {processed}"
                )
            if writes_database:
                self.jobs.complete_job(conn, job_id, processed)
                conn.commit()
            return EmbeddingRunResult(
                job_id=job_id,
                target_count=target_count,
                processed_count=processed,
                max_source_id=max_source_id,
                profile_key=self.profile.profile_key,
                dry_run=False,
            )
        except Exception as exc:
            conn.rollback()
            if writes_database and job_id is not None:
                self.jobs.fail_job(conn, job_id, processed, exc)
                conn.commit()
            raise
        finally:
            if writes_database:
                self.jobs.release_lock(conn)
                conn.commit()
