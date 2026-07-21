# -*- coding: utf-8 -*-
from functools import lru_cache

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
    vector = embedding_provider().encode([text])[0]
    return vector_literal(vector)
