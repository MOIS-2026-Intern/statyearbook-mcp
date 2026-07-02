# -*- coding: utf-8 -*-
import os

from openai import OpenAI

from app.config import EMBED_MODEL

# OpenAI 클라이언트는 첫 검색 때 만든다.
_openai_client: OpenAI | None = None


# 질의를 pgvector 리터럴로 임베딩한다.
def embed_query(text: str) -> str:
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
