# 이 파일은 관리자 적재와 운영 승격에 공통으로 사용할 최종 schema를 읽는다.
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT_DIR / "db" / "schema.sql"


def build_schema_ddl() -> str:
    if not SCHEMA_PATH.is_file():
        raise RuntimeError(f"schema file not found: {SCHEMA_PATH}")
    return SCHEMA_PATH.read_text(encoding="utf-8").rstrip() + "\n"
