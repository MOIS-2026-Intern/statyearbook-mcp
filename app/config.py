# -*- coding: utf-8 -*-
import os

from dotenv import load_dotenv

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

# 통계 제목 임베딩과 같은 모델을 사용한다.
EMBED_MODEL = os.environ.get("STATYEARBOOK_EMBED_MODEL", "text-embedding-3-small")

# 렌더링한 PNG를 저장하고 HTTP로 서빙할 디렉터리.
VISUALIZATION_DIR = os.environ.get("STATYEARBOOK_VISUALIZATION_DIR", "outputs/visualizations")

# PNG 정적 서버 바인딩 정보.
ASSET_SERVER_HOST = os.environ.get("STATYEARBOOK_ASSET_HOST", "127.0.0.1")
ASSET_SERVER_PORT = int(os.environ.get("STATYEARBOOK_ASSET_PORT", "8899"))

# 공개 배포 시 이미지 링크의 기준 URL(예: https://stats.example.com/viz).
# 설정하면 로컬 정적 서버를 띄우지 않고 이 값으로 링크를 만든다.
PUBLIC_BASE_URL = os.environ.get("STATYEARBOOK_PUBLIC_BASE_URL")
