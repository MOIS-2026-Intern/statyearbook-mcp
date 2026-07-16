# -*- coding: utf-8 -*-
from functools import lru_cache

from app.config import EMBEDDING_SETTINGS
from app.embedding import (
    STATISTICS_CONTENT_VERSION,
    EmbeddingProfile,
    EmbeddingProvider,
    create_embedding_profile,
    create_embedding_provider,
)
from app.vector import vector_literal


# provider와 로컬 모델은 프로세스마다 한 번만 만든다.
@lru_cache(maxsize=1)
def embedding_provider() -> EmbeddingProvider:
    return create_embedding_provider(EMBEDDING_SETTINGS)


@lru_cache(maxsize=1)
def embedding_profile() -> EmbeddingProfile:
    return create_embedding_profile(EMBEDDING_SETTINGS, STATISTICS_CONTENT_VERSION)


# 질의를 pgvector 리터럴로 임베딩한다.
def embed_query(text: str) -> str:
    vector = embedding_provider().encode([text])[0]
    return vector_literal(vector)
