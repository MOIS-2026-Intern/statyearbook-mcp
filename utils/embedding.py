# -*- coding: utf-8 -*-
"""app과 admin이 공유하는 고정 BGE-M3 임베딩 profile과 provider."""
from __future__ import annotations

import hashlib
import json
import math

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol, Sequence


BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
MODEL_MANIFEST = ".statyearbook-model.json"
LOCAL_EMBEDDING_PROVIDER = "local"
STATISTICS_CONTENT_VERSION = "statistics-title-v3-level4-70-context-30"
TABLE_SEARCH_CONTENT_VERSION = "table-search-v1-headers-labels"


class EmbeddingConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    dimension: int
    batch_size: int = 16
    device: str = "cpu"
    max_length: int = 512
    revision: str | None = None

    # 로컬 BGE-M3 사용 여부와 양수여야 하는 실행 옵션을 생성 시점에 검증한다.
    def __post_init__(self) -> None:
        if self.provider != LOCAL_EMBEDDING_PROVIDER:
            raise EmbeddingConfigurationError(
                "only the local BGE-M3 embedding provider is supported"
            )
        for name in ("dimension", "batch_size", "max_length"):
            if getattr(self, name) <= 0:
                raise EmbeddingConfigurationError(f"{name} must be greater than zero")


@dataclass(frozen=True)
class EmbeddingProfile:
    profile_key: str
    provider: str
    model: str
    revision: str
    dimension: int
    max_length: int
    content_version: str
    normalized: bool

    # 프로필을 DB 저장에 사용할 평범한 dict로 직렬화한다.
    def as_record(self) -> dict:
        return {
            "profile_key": self.profile_key,
            "provider": self.provider,
            "model": self.model,
            "revision": self.revision,
            "dimension": self.dimension,
            "max_length": self.max_length,
            "content_version": self.content_version,
            "normalized": self.normalized,
        }


# 로컬 모델과 함께 배포된 고정 revision manifest를 읽고 검증한다.
def _read_model_manifest(model_path: Path) -> dict:
    manifest_path = model_path / MODEL_MANIFEST
    if not manifest_path.is_file():
        raise EmbeddingConfigurationError(
            f"local embedding model manifest not found: {manifest_path}; "
            "provision the pinned model artifact before starting the service"
        )
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmbeddingConfigurationError(
            f"invalid local embedding model manifest: {manifest_path}"
        ) from exc


# 모델 설정과 콘텐츠 버전으로 재현 가능한 임베딩 프로필 키를 만든다.
def create_embedding_profile(
    settings: EmbeddingSettings,
    content_version: str,
) -> EmbeddingProfile:
    model_path = Path(settings.model).expanduser().resolve()
    manifest = _read_model_manifest(model_path)
    model = str(manifest.get("source_model") or model_path.name)
    revision = str(manifest.get("revision") or "")

    identity = {
        "provider": LOCAL_EMBEDDING_PROVIDER,
        "model": model,
        "revision": revision,
        "dimension": settings.dimension,
        "max_length": settings.max_length,
        "content_version": content_version,
        "normalized": True,
    }
    serialized = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    profile_key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return EmbeddingProfile(profile_key=profile_key, **identity)


class EmbeddingProvider(Protocol):
    settings: EmbeddingSettings

    # 입력 순서를 보존해 설정된 차원의 벡터를 하나씩 반환한다.
    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        ...


# provider 결과를 float로 변환하고 개수·차원·유한성을 검증한다.
def _validated_vectors(
    vectors: Sequence[Sequence[float]],
    expected_count: int,
    expected_dimension: int,
) -> list[list[float]]:
    result = [[float(value) for value in vector] for vector in vectors]
    if len(result) != expected_count:
        raise RuntimeError(
            f"embedding provider returned {len(result)} vectors for {expected_count} inputs"
        )
    for vector in result:
        if len(vector) != expected_dimension:
            raise RuntimeError(
                f"embedding dimension {len(vector)} != configured {expected_dimension}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise RuntimeError("embedding contains a non-finite value")
    return result


class LocalSentenceTransformerProvider:
    # 로컬 artifact를 검증하되 무거운 모델 로딩은 첫 요청까지 미룬다.
    def __init__(self, settings: EmbeddingSettings):
        self.settings = settings
        self._model_path = Path(settings.model).expanduser().resolve()
        self._model = None
        self._load_lock = Lock()
        self._validate_artifact()

    # 로컬 모델 경로와 manifest의 차원·revision 일치를 확인한다.
    def _validate_artifact(self) -> None:
        if not self._model_path.is_dir():
            raise EmbeddingConfigurationError(
                f"local embedding model directory not found: {self._model_path}"
            )
        manifest = _read_model_manifest(self._model_path)

        if manifest.get("dimension") != self.settings.dimension:
            raise EmbeddingConfigurationError(
                "local model manifest dimension does not match the configured dimension"
            )
        if self.settings.revision and manifest.get("revision") != self.settings.revision:
            raise EmbeddingConfigurationError(
                "local model manifest revision does not match the configured revision"
            )

    # 동시 첫 요청에서도 모델 인스턴스를 한 번만 지연 로딩한다.
    def _load_model(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise EmbeddingConfigurationError(
                        "sentence-transformers is required for local embeddings"
                    ) from exc
                self._model = SentenceTransformer(
                    str(self._model_path),
                    device=self.settings.device,
                    local_files_only=True,
                )
                self._model.max_seq_length = self.settings.max_length
        return self._model

    # 로컬 모델로 정규화 임베딩을 만들고 반환 shape를 검증한다.
    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        inputs = list(texts)
        if not inputs:
            return []
        encoded = self._load_model().encode(
            inputs,
            batch_size=self.settings.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vectors = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        return _validated_vectors(vectors, len(inputs), self.settings.dimension)


# 검증된 로컬 BGE-M3 설정으로 임베딩 구현체를 생성한다.
def create_embedding_provider(settings: EmbeddingSettings) -> EmbeddingProvider:
    return LocalSentenceTransformerProvider(settings)
