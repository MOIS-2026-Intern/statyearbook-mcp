# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import math
import os

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol, Sequence


BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
MODEL_MANIFEST = ".statyearbook-model.json"
SUPPORTED_PROVIDERS = ("openai", "local")
STATISTICS_CONTENT_VERSION = "statistics-title-v3-level4-70-context-30"


class EmbeddingConfigurationError(RuntimeError):
    pass


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise EmbeddingConfigurationError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise EmbeddingConfigurationError(f"{name} must be greater than zero")
    return parsed


def _default_model(provider: str) -> str:
    if provider == "local":
        return "models/bge-m3"
    return "text-embedding-3-small"


def _default_dimension(provider: str, model: str) -> int:
    if provider == "local" and Path(model).name == "bge-m3":
        return 1024
    if provider == "openai" and model == "text-embedding-3-small":
        return 1536
    raise EmbeddingConfigurationError(
        "STATYEARBOOK_EMBED_DIMENSION is required for this embedding model"
    )


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    dimension: int
    batch_size: int = 16
    device: str = "cpu"
    max_length: int = 512
    revision: str | None = None

    @classmethod
    def from_env(cls) -> "EmbeddingSettings":
        provider = os.environ.get("STATYEARBOOK_EMBED_PROVIDER", "openai").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            supported = ", ".join(SUPPORTED_PROVIDERS)
            raise EmbeddingConfigurationError(
                f"unsupported STATYEARBOOK_EMBED_PROVIDER={provider!r}; use {supported}"
            )

        model = os.environ.get("STATYEARBOOK_EMBED_MODEL") or _default_model(provider)
        raw_dimension = os.environ.get("STATYEARBOOK_EMBED_DIMENSION")
        dimension = (
            _positive_int(raw_dimension, "STATYEARBOOK_EMBED_DIMENSION")
            if raw_dimension
            else _default_dimension(provider, model)
        )
        batch_size = _positive_int(
            os.environ.get("STATYEARBOOK_EMBED_BATCH_SIZE", "16"),
            "STATYEARBOOK_EMBED_BATCH_SIZE",
        )
        max_length = _positive_int(
            os.environ.get("STATYEARBOOK_EMBED_MAX_LENGTH", "512"),
            "STATYEARBOOK_EMBED_MAX_LENGTH",
        )
        revision = os.environ.get("STATYEARBOOK_EMBED_REVISION")
        if provider == "local" and not revision and Path(model).name == "bge-m3":
            revision = BGE_M3_REVISION

        return cls(
            provider=provider,
            model=model,
            dimension=dimension,
            batch_size=batch_size,
            device=os.environ.get("STATYEARBOOK_EMBED_DEVICE", "cpu"),
            max_length=max_length,
            revision=revision,
        )


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


def _read_model_manifest(model_path: Path) -> dict:
    manifest_path = model_path / MODEL_MANIFEST
    if not manifest_path.is_file():
        raise EmbeddingConfigurationError(
            f"local embedding model manifest not found: {manifest_path}; "
            "prepare the model with scripts/download_embedding_model.py"
        )
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmbeddingConfigurationError(
            f"invalid local embedding model manifest: {manifest_path}"
        ) from exc


def create_embedding_profile(
    settings: EmbeddingSettings,
    content_version: str,
) -> EmbeddingProfile:
    if settings.provider == "local":
        model_path = Path(settings.model).expanduser().resolve()
        manifest = _read_model_manifest(model_path)
        model = str(manifest.get("source_model") or model_path.name)
        revision = str(manifest.get("revision") or "")
        normalized = True
    else:
        model = settings.model
        revision = settings.revision or ""
        normalized = False

    identity = {
        "provider": settings.provider,
        "model": model,
        "revision": revision,
        "dimension": settings.dimension,
        "max_length": settings.max_length,
        "content_version": content_version,
        "normalized": normalized,
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

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        ...


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


class OpenAIEmbeddingProvider:
    def __init__(self, settings: EmbeddingSettings):
        if not os.environ.get("OPENAI_API_KEY"):
            raise EmbeddingConfigurationError(
                "OPENAI_API_KEY is required when STATYEARBOOK_EMBED_PROVIDER=openai"
            )
        from openai import OpenAI

        self.settings = settings
        self._client = OpenAI()

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        inputs = list(texts)
        if not inputs:
            return []
        response = self._client.embeddings.create(
            model=self.settings.model,
            input=inputs,
            dimensions=self.settings.dimension,
        )
        vectors = [item.embedding for item in response.data]
        return _validated_vectors(vectors, len(inputs), self.settings.dimension)


class LocalSentenceTransformerProvider:
    def __init__(self, settings: EmbeddingSettings):
        self.settings = settings
        self._model_path = Path(settings.model).expanduser().resolve()
        self._model = None
        self._load_lock = Lock()
        self._validate_artifact()

    def _validate_artifact(self) -> None:
        if not self._model_path.is_dir():
            raise EmbeddingConfigurationError(
                f"local embedding model directory not found: {self._model_path}"
            )
        manifest = _read_model_manifest(self._model_path)

        if manifest.get("dimension") != self.settings.dimension:
            raise EmbeddingConfigurationError(
                "local model manifest dimension does not match "
                "STATYEARBOOK_EMBED_DIMENSION"
            )
        if self.settings.revision and manifest.get("revision") != self.settings.revision:
            raise EmbeddingConfigurationError(
                "local model manifest revision does not match "
                "STATYEARBOOK_EMBED_REVISION"
            )

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


def create_embedding_provider(settings: EmbeddingSettings) -> EmbeddingProvider:
    if settings.provider == "openai":
        return OpenAIEmbeddingProvider(settings)
    if settings.provider == "local":
        return LocalSentenceTransformerProvider(settings)
    raise EmbeddingConfigurationError(f"unsupported embedding provider: {settings.provider}")
