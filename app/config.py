# -*- coding: utf-8 -*-
"""환경 설정 로딩.

접속 정보(비밀번호 등)는 코드가 아니라 .env 에 두고, .env 는 커밋하지 않는다.
예)  cp .env.example .env  후 .env 안의 값을 채운다.
"""
import os

from dotenv import load_dotenv

# 같은 폴더의 .env 파일에서 환경변수를 읽어들인다(있으면).
load_dotenv()

DSN = os.environ.get("STATYEARBOOK_DSN")
if not DSN:
    raise RuntimeError(
        "STATYEARBOOK_DSN 이 설정되지 않았습니다. "
        ".env.example 를 .env 로 복사한 뒤 접속 정보를 채워 주세요."
    )

# 의미 검색용 임베딩 모델. load/embed_statistics.py 로 저장한 것과 반드시 동일해야
# 벡터 공간이 일치한다(text-embedding-3-small = 1536차원, 스키마 vector(1536)).
EMBED_MODEL = os.environ.get("STATYEARBOOK_EMBED_MODEL", "text-embedding-3-small")
