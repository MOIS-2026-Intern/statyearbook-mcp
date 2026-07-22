# 이 파일은 임베딩 provider와 데이터 repository를 batch 단위로 연결해 실행한다.
# DB 직접 저장과 DML 전용 생성 모드를 분리해 호출자가 적재 방식을 선택하게 한다.
from __future__ import annotations

import math

from typing import Callable, Literal, Protocol

from admin.backend.models.embedding import (
    EmbeddingBatch,
    EmbeddingRunResult,
    WeightedEmbeddingTexts,
)
from admin.backend.repositories.embedding_jobs import EmbeddingJobRepository
from utils.embedding import EmbeddingProfile, EmbeddingProvider


class EmbeddingSource(Protocol):
    name: str

    # 저장 대상 vector 열이 모델 차원을 수용하는지 검증한다.
    def select_and_validate_dimension(self, conn, expected_dimension: int) -> None:
        ...

    # 실행 범위를 고정할 현재 최대 source ID를 반환한다.
    def select_max_source_id(self, conn) -> int:
        ...

    # profile과 강제 실행 여부에 맞는 전체 후보 수를 반환한다.
    def select_candidate_count(
        self,
        conn,
        profile_key: str,
        force: bool,
        max_source_id: int,
    ) -> int:
        ...

    # source ID 커서 뒤의 다음 후보 배치를 읽는다.
    def select_candidate_batch(
        self,
        conn,
        profile_key: str,
        force: bool,
        after_source_id: int,
        max_source_id: int,
        batch_size: int,
    ) -> EmbeddingBatch:
        ...

    # 후보 행을 단일 또는 가중치 기반 모델 입력으로 변환한다.
    def select_embedding_texts(
        self,
        rows: list[dict],
    ) -> list[str] | WeightedEmbeddingTexts:
        ...

    # 행과 같은 순서의 벡터를 저장 대상에 반영한다.
    def update_embedding_batch(
        self,
        conn,
        rows: list[dict],
        vectors: list[list[float]],
        profile_key: str,
    ) -> None:
        ...


class EmbeddingRunner:
    # provider, profile과 저장소를 하나의 배치 실행 단위로 묶는다.
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

    # 일반 입력은 그대로 인코딩하고 가중 입력은 합성 후 단위 벡터로 정규화한다.
    def _encode_texts(
        self,
        inputs: list[str] | WeightedEmbeddingTexts,
    ) -> list[list[float]]:
        if isinstance(inputs, list):
            return self.provider.encode(inputs)
        if not inputs.groups:
            return []

        expected_count = len(inputs.groups[0][1])
        total_weight = sum(weight for weight, _texts in inputs.groups)
        if total_weight <= 0:
            raise ValueError("embedding weights must sum to a positive value")

        encoded_groups: list[tuple[float, list[list[float]]]] = []
        for weight, texts in inputs.groups:
            if weight < 0:
                raise ValueError("embedding weights must not be negative")
            if len(texts) != expected_count:
                raise ValueError("weighted embedding groups must have the same row count")
            if weight:
                encoded_groups.append((weight / total_weight, self.provider.encode(texts)))

        combined: list[list[float]] = []
        for row_index in range(expected_count):
            dimensions = {len(vectors[row_index]) for _weight, vectors in encoded_groups}
            if len(dimensions) != 1:
                raise RuntimeError("weighted embedding vectors have different dimensions")
            dimension = dimensions.pop()
            vector = [
                sum(weight * vectors[row_index][index] for weight, vectors in encoded_groups)
                for index in range(dimension)
            ]
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                raise RuntimeError("weighted embedding produced a zero vector")
            combined.append([value / norm for value in vector])
        return combined

    # 고정된 후보 범위를 배치 처리하며 DB 저장 또는 이관용 callback 출력을 수행한다.
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
        self.source.select_and_validate_dimension(conn, self.profile.dimension)
        if writes_database:
            self.jobs.acquire_lock(conn)
        job_id = None
        processed = 0
        try:
            max_source_id = self.source.select_max_source_id(conn)
            target_count = self.source.select_candidate_count(
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
                self.jobs.insert_embedding_profile(conn, self.profile)
                job_id = self.jobs.insert_embedding_job(
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
                batch = self.source.select_candidate_batch(
                    conn,
                    self.profile.profile_key,
                    force,
                    after_source_id,
                    max_source_id,
                    batch_size,
                )
                if not batch.rows:
                    break
                vectors = self._encode_texts(self.source.select_embedding_texts(batch.rows))
                if on_batch:
                    on_batch(batch.rows, vectors, self.profile)
                if writes_database:
                    self.source.update_embedding_batch(
                        conn,
                        batch.rows,
                        vectors,
                        self.profile.profile_key,
                    )
                processed += len(batch.rows)
                after_source_id = batch.last_source_id
                if writes_database:
                    self.jobs.update_embedding_job_progress(conn, job_id, processed)
                    conn.commit()
                if progress:
                    progress(processed, target_count)

            if processed != target_count:
                raise RuntimeError(
                    f"embedding candidate count changed: expected {target_count}, processed {processed}"
                )
            if writes_database:
                self.jobs.update_embedding_job_completed(conn, job_id, processed)
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
                self.jobs.update_embedding_job_failed(conn, job_id, processed, exc)
                conn.commit()
            raise
        finally:
            if writes_database:
                self.jobs.release_lock(conn)
                conn.commit()
