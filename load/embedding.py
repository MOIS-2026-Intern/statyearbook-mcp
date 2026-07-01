#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
embedding.py
statistics 테이블의 제목을 OpenAI 임베딩으로 변환해 embedding(vector) 컬럼을 채운다.

임베딩은 "한 번만" 만들어 저장하면 된다. 이후 검색 시에는 사용자 질의만 그때그때
임베딩해서 저장된 벡터들과 코사인 거리(<=>)를 비교한다.
제목이 바뀌거나 새 표가 추가됐을 때만 다시 실행하면 된다.

전제:
  - db/migrations/0001_init.sql 로 스키마가 만들어져 있고
  - load/load_to_postgres.py 로 데이터가 적재된 상태(embedding 은 NULL)
  - .env 에 STATYEARBOOK_DSN, OPENAI_API_KEY 가 설정돼 있음

사용법:
  python load/embedding.py            # embedding 이 비어있는 행만 채움
  python load/embedding.py --all      # 전부 다시 임베딩(제목이 바뀐 경우)
  python load/embedding.py --model text-embedding-3-small --batch 100

주의:
  스키마는 vector(1536) 이므로 임베딩 차원이 1536 인 모델을 써야 한다.
  text-embedding-3-small(기본 1536)이 맞다. 3-large(3072)를 쓰려면 컬럼을 바꿔야 함.
"""
import os, sys, argparse
from dotenv import load_dotenv

load_dotenv()  # .env 의 STATYEARBOOK_DSN, OPENAI_API_KEY 로드

DSN = os.environ.get("STATYEARBOOK_DSN") or os.environ.get("DATABASE_URL")
EXPECTED_DIM = 1536  # 스키마 vector(1536) 과 일치해야 함


def build_text(row: dict) -> str:
    """임베딩할 텍스트. search_doc(tsvector)와 동일한 소스를 사용해 일관성 유지."""
    parts = [row.get("title_ko"), row.get("title_en"),
             row.get("chapter"), row.get("section")]
    text = " ".join(p for p in parts if p).strip()
    # OpenAI 는 빈 문자열 입력을 거부하므로 최소 한 글자는 보장
    return text or "(제목 없음)"


def to_vector_literal(vec) -> str:
    """파이썬 리스트 -> pgvector 리터럴 '[0.1,0.2,...]' (::vector 로 캐스팅해 저장)."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="embedding 이 이미 있어도 전부 다시 생성")
    ap.add_argument("--model", default="text-embedding-3-small",
                    help="OpenAI 임베딩 모델(기본 text-embedding-3-small, 1536차원)")
    ap.add_argument("--batch", type=int, default=100,
                    help="한 번의 API 호출에 넣을 제목 수(기본 100)")
    ap.add_argument("--dsn", default=DSN, help="DB 접속 문자열(기본 .env 의 STATYEARBOOK_DSN)")
    args = ap.parse_args()

    if not args.dsn:
        sys.exit("DSN 미지정: .env 의 STATYEARBOOK_DSN 또는 --dsn 을 설정하세요.")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY 미설정: .env 에 키를 넣으세요.")

    import psycopg
    from psycopg.rows import dict_row
    from openai import OpenAI

    client = OpenAI()  # OPENAI_API_KEY 를 환경변수에서 읽음

    where = "" if args.all else "WHERE embedding IS NULL"
    select_sql = (f"SELECT stat_id, title_ko, title_en, chapter, section "
                  f"FROM statistics {where} ORDER BY stat_id")

    with psycopg.connect(args.dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(select_sql)
            rows = cur.fetchall()

        if not rows:
            print("임베딩할 대상이 없습니다. (--all 로 전체 재생성 가능)")
            return

        print(f"대상 {len(rows)}건 · 모델 {args.model} · 배치 {args.batch}")
        done = 0
        for i in range(0, len(rows), args.batch):
            chunk = rows[i:i + args.batch]
            inputs = [build_text(r) for r in chunk]

            resp = client.embeddings.create(model=args.model, input=inputs)
            # resp.data 는 입력 순서와 동일하게 반환됨
            vecs = [d.embedding for d in resp.data]

            dim = len(vecs[0])
            if dim != EXPECTED_DIM:
                sys.exit(f"임베딩 차원 {dim} != 스키마 {EXPECTED_DIM}. "
                         f"모델을 바꾸거나 컬럼을 vector({dim}) 로 변경하세요.")

            params = [(to_vector_literal(v), r["stat_id"])
                      for v, r in zip(vecs, chunk)]
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE statistics SET embedding = %s::vector WHERE stat_id = %s",
                    params)
            conn.commit()  # 배치마다 커밋 → 중간에 끊겨도 이어서 재실행 가능

            done += len(chunk)
            print(f"  {done}/{len(rows)}")

    print("완료. 이제 검색에서 embedding <=> query 로 의미 검색을 쓸 수 있습니다.")


if __name__ == "__main__":
    main()
