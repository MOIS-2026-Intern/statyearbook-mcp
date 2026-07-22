"""관리자 임베딩 작업에서 repository와 service가 공유하는 자료형."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingBatch:
    rows: list[dict]
    last_source_id: int


@dataclass(frozen=True)
class WeightedEmbeddingTexts:
    """같은 행을 여러 문맥으로 임베딩한 뒤 지정 비율로 합칠 입력."""

    groups: tuple[tuple[float, list[str]], ...]


@dataclass(frozen=True)
class EmbeddingRunResult:
    job_id: int | None
    target_count: int
    processed_count: int
    max_source_id: int
    profile_key: str
    dry_run: bool
