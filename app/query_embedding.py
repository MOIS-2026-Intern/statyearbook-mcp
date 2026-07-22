# -*- coding: utf-8 -*-
import logging
from functools import lru_cache
from time import perf_counter

from app.config import settings
from utils.embedding import (
    STATISTICS_CONTENT_VERSION,
    TABLE_SEARCH_CONTENT_VERSION,
    EmbeddingProfile,
    EmbeddingProvider,
    create_embedding_profile,
    create_embedding_provider,
)
from utils.vector import vector_literal


logger = logging.getLogger(__name__)


# provider와 로컬 모델은 프로세스마다 한 번만 만든다.
@lru_cache(maxsize=1)
def embedding_provider() -> EmbeddingProvider:
    return create_embedding_provider(settings.embedding)


# 통계 제목 임베딩의 재현 가능한 프로필 식별자를 캐시한다.
@lru_cache(maxsize=1)
def embedding_profile() -> EmbeddingProfile:
    return create_embedding_profile(settings.embedding, STATISTICS_CONTENT_VERSION)


# 표 검색 청크 임베딩의 프로필 식별자를 캐시한다.
@lru_cache(maxsize=1)
def table_search_embedding_profile() -> EmbeddingProfile:
    return create_embedding_profile(settings.embedding, TABLE_SEARCH_CONTENT_VERSION)


# 질의를 pgvector 리터럴로 임베딩한다.
def embed_query(text: str) -> str:
    provider = embedding_provider()
    started = perf_counter()
    try:
        vector = provider.encode([text])[0]
    except Exception as exc:
        logger.exception(
            "event=embedding.error provider=%s duration_ms=%s error_type=%s",
            provider.settings.provider,
            _elapsed_ms(started),
            exc.__class__.__name__,
        )
        raise
    logger.debug(
        "event=embedding provider=%s duration_ms=%s",
        provider.settings.provider,
        _elapsed_ms(started),
    )
    return vector_literal(vector)


# Convert a monotonic start timestamp into rounded milliseconds.
def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
