#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # .env 의 STATYEARBOOK_DSN, OPENAI_API_KEY 로드

DSN = os.environ.get("STATYEARBOOK_DSN") or os.environ.get("DATABASE_URL")
EXPECTED_DIM = 1536  # 스키마 vector(1536) 과 일치해야 함


# CLI 인자를 정의한다.
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="embedding 이 이미 있어도 전부 다시 생성")
    ap.add_argument("--model", default="text-embedding-3-small",
                    help="OpenAI 임베딩 모델(기본 text-embedding-3-small, 1536차원)")
    ap.add_argument("--batch", type=int, default=100,
                    help="한 번의 API 호출에 넣을 제목 수(기본 100)")
    ap.add_argument("--dsn", default=DSN, help="DB 접속 문자열(기본 .env 의 STATYEARBOOK_DSN)")
    return ap


# 실행에 필요한 설정을 확인한다.
def validate_settings(args) -> None:
    if not args.dsn:
        sys.exit("DSN 미지정: .env 의 STATYEARBOOK_DSN 또는 --dsn 을 설정하세요.")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY 미설정: .env 에 키를 넣으세요.")
    if args.batch <= 0:
        sys.exit("--batch 는 1 이상이어야 합니다.")


# 임베딩할 제목 조회 SQL을 만든다.
def select_sql(all_rows: bool) -> str:
    where = "" if all_rows else "WHERE embedding IS NULL"
    return (
        "SELECT stat_id, title_ko, title_en, chapter, section "
        f"FROM statistics {where} ORDER BY stat_id"
    )


# DB에서 임베딩 대상 행을 조회한다.
def fetch_rows(conn, all_rows: bool) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(select_sql(all_rows))
        return cur.fetchall()


# 리스트를 배치 단위로 나눈다.
def iter_batches(rows: list, batch_size: int):
    for start in range(0, len(rows), batch_size):
        yield rows[start:start + batch_size]


# 임베딩할 텍스트를 만든다.
def build_text(row: dict) -> str:
    parts = [row.get("title_ko"), row.get("title_en"),
             row.get("chapter"), row.get("section")]
    text = " ".join(filter(None, parts)).strip()
    # OpenAI 는 빈 문자열 입력을 거부하므로 최소 한 글자는 보장
    return text or "(제목 없음)"


# 파이썬 리스트를 pgvector 리터럴로 바꾼다.
def vector_literal(vec) -> str:
    items = ",".join(str(float(value)) for value in vec)
    return f"[{items}]"


# OpenAI 응답에서 임베딩 벡터만 꺼낸다.
def create_embeddings(client, model: str, rows: list[dict]) -> list:
    inputs = [build_text(row) for row in rows]
    resp = client.embeddings.create(model=model, input=inputs)
    return [item.embedding for item in resp.data]


# 임베딩 차원이 DB 스키마와 맞는지 확인한다.
def validate_dimension(vecs: list) -> None:
    dim = len(vecs[0])
    if dim != EXPECTED_DIM:
        sys.exit(f"임베딩 차원 {dim} != 스키마 {EXPECTED_DIM}. "
                 f"모델을 바꾸거나 컬럼을 vector({dim}) 로 변경하세요.")


# DB 업데이트용 파라미터를 만든다.
def update_params(vecs: list, rows: list[dict]) -> list[tuple]:
    return [(vector_literal(vec), row["stat_id"]) for vec, row in zip(vecs, rows)]


# 임베딩 값을 DB에 저장한다.
def update_embeddings(conn, params: list[tuple]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE statistics SET embedding = %s::vector WHERE stat_id = %s",
            params)
    conn.commit()


# 한 배치를 임베딩하고 저장한다.
def process_batch(conn, client, model: str, rows: list[dict]) -> None:
    vecs = create_embeddings(client, model, rows)
    validate_dimension(vecs)
    update_embeddings(conn, update_params(vecs, rows))


def run(args) -> None:
    validate_settings(args)

    import psycopg
    from psycopg.rows import dict_row
    from openai import OpenAI

    client = OpenAI()  # OPENAI_API_KEY 를 환경변수에서 읽음

    with psycopg.connect(args.dsn, row_factory=dict_row) as conn:
        rows = fetch_rows(conn, args.all)

        if not rows:
            print("임베딩할 대상이 없습니다. (--all 로 전체 재생성 가능)")
            return

        print(f"대상 {len(rows)}건 · 모델 {args.model} · 배치 {args.batch}")
        done = 0
        for chunk in iter_batches(rows, args.batch):
            process_batch(conn, client, args.model, chunk)
            done += len(chunk)
            print(f"  {done}/{len(rows)}")

    print("완료. 이제 검색에서 embedding <=> query 로 의미 검색을 쓸 수 있습니다.")


def main() -> None:
    args = build_parser().parse_args()
    run(args)


if __name__ == "__main__":
    main()
