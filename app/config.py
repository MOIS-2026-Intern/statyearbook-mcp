# -*- coding: utf-8 -*-
import os

from dotenv import load_dotenv

from app.embedding import EmbeddingSettings

# .env 값을 환경변수로 읽는다.
load_dotenv()


# 필수 환경변수를 읽고 없으면 바로 중단한다.
def required_env(name: str, message: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(message)
    return value


# PostgreSQL 접속 문자열.
DSN = required_env(
    "STATYEARBOOK_DSN",
    "STATYEARBOOK_DSN 이 설정되지 않았습니다. "
    ".env.example 를 .env 로 복사한 뒤 접속 정보를 채워 주세요.",
)

# 통계 제목 적재와 질의에 동일하게 적용되는 임베딩 설정.
EMBEDDING_SETTINGS = EmbeddingSettings.from_env()
