# -*- coding: utf-8 -*-
"""검색 질의 임베딩.

질의를 임베딩 적재 때와 동일한 OpenAI 모델로 임베딩한 뒤, statistics.embedding 과
코사인 거리(<=>)로 비교해 가까운 순으로 정렬하는 데 쓴다.
"""
import os

from openai import OpenAI

from app.config import EMBED_MODEL

# OpenAI 클라이언트는 처음 검색할 때 한 번만 만든다(모듈 로드 시 키가 없어도 서버는 뜨게).
_openai_client: OpenAI | None = None


def embed_query(text: str) -> str:
    """질의를 임베딩해 pgvector 리터럴 '[0.1,0.2,...]' 로 돌려준다."""
    global _openai_client
    if _openai_client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY 미설정: 의미 검색을 하려면 .env 에 키를 넣어 주세요."
            )
        _openai_client = OpenAI()
    resp = _openai_client.embeddings.create(model=EMBED_MODEL, input=text)
    vec = resp.data[0].embedding
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
