# -*- coding: utf-8 -*-
import os

from openai import OpenAI

from app.config import EMBED_MODEL
from app.vector import vector_literal

# OpenAI 클라이언트는 첫 검색 때 만든다.
_openai_client: OpenAI | None = None


# OpenAI API 키가 있는지 확인한다.
def require_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY 미설정: 의미 검색을 하려면 .env 에 키를 넣어 주세요."
        )


# OpenAI 클라이언트를 지연 생성한다.
def openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        require_api_key()
        _openai_client = OpenAI()
    return _openai_client


# 질의를 pgvector 리터럴로 임베딩한다.
def embed_query(text: str) -> str:
    client = openai_client()
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return vector_literal(resp.data[0].embedding)
