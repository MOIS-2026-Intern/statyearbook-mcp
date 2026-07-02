# -*- coding: utf-8 -*-
import os

from dotenv import load_dotenv

# .env 값을 환경변수로 읽는다.
load_dotenv()

# PostgreSQL 접속 문자열.
DSN = os.environ.get("STATYEARBOOK_DSN")
if not DSN:
    raise RuntimeError(
        "STATYEARBOOK_DSN 이 설정되지 않았습니다. "
        ".env.example 를 .env 로 복사한 뒤 접속 정보를 채워 주세요."
    )

# 통계 제목 임베딩과 같은 모델을 사용한다.
EMBED_MODEL = os.environ.get("STATYEARBOOK_EMBED_MODEL", "text-embedding-3-small")
