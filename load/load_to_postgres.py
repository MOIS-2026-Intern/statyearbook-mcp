#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
from itertools import count

from dotenv import load_dotenv

load_dotenv()  # .env 의 STATYEARBOOK_DSN 등을 환경변수로 로드


# 빈 테이블별 행 목록을 만든다.
def empty_rows() -> dict:
    return {
        'publications': [],
        'statistics': [],
        'stat_tables': [],
        'footnotes': [],
        'contacts': [],
        'statistic_images': [],
    }


# 발간물 행을 만든다.
def publication_row(pub: dict, pub_id: int) -> tuple:
    return (
        pub_id,
        pub['year'],
        pub.get('pub_no'),
        pub['title'],
        pub.get('page_count'),
    )


# 통계 단위 행을 만든다.
def statistic_row(unit: dict, stat_id: int, pub_id: int, year: int) -> tuple:
    return (
        stat_id,
        pub_id,
        year,
        unit.get('ref_id'),
        unit.get('chapter_no'),
        unit.get('section_no'),
        unit.get('chapter'),
        unit.get('section'),
        unit['title_ko'],
        unit.get('title_en'),
        unit.get('unit'),
        unit.get('base_date'),
        unit.get('page_start'),
    )


# 통계표 행을 만든다.
def stat_table_row(table: dict, table_id: int, stat_id: int) -> tuple:
    body_json = json.dumps(table['body'], ensure_ascii=False)
    return (
        table_id,
        stat_id,
        table.get('seq'),
        table.get('caption'),
        table.get('n_rows'),
        table.get('n_cols'),
        body_json,
        table.get('table_md'),
    )


# 주석 행을 만든다.
def footnote_row(footnote: dict, note_id: int, stat_id: int) -> tuple:
    return (
        note_id,
        stat_id,
        footnote.get('seq'),
        footnote.get('note_no'),
        footnote.get('content'),
    )


# 담당자/출처 행을 만든다.
def contact_row(contact: dict, contact_id: int, stat_id: int) -> tuple:
    return (
        contact_id,
        stat_id,
        contact.get('dept'),
        contact.get('officer'),
        contact.get('phone'),
        contact.get('source_system'),
        contact.get('source_url'),
    )


# 이미지 행을 만든다.
def image_row(image: dict, image_id: int, stat_id: int) -> tuple:
    return (
        image_id,
        stat_id,
        image.get('filename'),
        image.get('page'),
        image.get('uri'),
        image.get('caption'),
    )


# 통계 단위 하나를 테이블별 행 목록에 추가한다.
def add_statistic_rows(rows: dict, unit: dict, ids: dict, pub_id: int, year: int) -> None:
    stat_id = next(ids['statistics'])
    rows['statistics'].append(statistic_row(unit, stat_id, pub_id, year))

    for table in unit['tables']:
        table_id = next(ids['stat_tables'])
        rows['stat_tables'].append(stat_table_row(table, table_id, stat_id))
    for footnote in unit['footnotes']:
        note_id = next(ids['footnotes'])
        rows['footnotes'].append(footnote_row(footnote, note_id, stat_id))
    for contact in unit['contacts']:
        contact_id = next(ids['contacts'])
        rows['contacts'].append(contact_row(contact, contact_id, stat_id))
    for image in unit['images']:
        image_id = next(ids['statistic_images'])
        rows['statistic_images'].append(image_row(image, image_id, stat_id))


# parsed json을 각 테이블의 행 튜플로 평탄화한다.
def build_rows(data):
    pub = data['publication']
    pub_id = 1
    rows = empty_rows()
    ids = {
        'statistics': count(1),
        'stat_tables': count(1),
        'footnotes': count(1),
        'contacts': count(1),
        'statistic_images': count(1),
    }

    rows['publications'].append(publication_row(pub, pub_id))
    for unit in data['statistics']:
        add_statistic_rows(rows, unit, ids, pub_id, pub['year'])

    return rows


COLS = {
    'publications': ['pub_id', 'year', 'pub_no', 'title', 'page_count'],
    'statistics':   ['stat_id', 'pub_id', 'year', 'ref_id', 'chapter_no',
                     'section_no', 'chapter', 'section', 'title_ko', 'title_en',
                     'unit', 'base_date', 'page_start'],
    'stat_tables':  ['table_id', 'stat_id', 'seq', 'caption', 'n_rows',
                     'n_cols', 'body', 'table_md'],
    'footnotes':    ['note_id', 'stat_id', 'seq', 'note_no', 'content'],
    'contacts':     ['contact_id', 'stat_id', 'dept', 'officer', 'phone',
                     'source_system', 'source_url'],
    'statistic_images': ['image_id', 'stat_id', 'filename', 'page', 'uri', 'caption'],
}
# body 컬럼은 jsonb 캐스팅 필요
JSONB_COL = {'stat_tables': 'body'}
SEQ = {  # 시퀀스 setval 대상 (테이블, PK컬럼)
    'publications': 'pub_id', 'statistics': 'stat_id', 'stat_tables': 'table_id',
    'footnotes': 'note_id', 'contacts': 'contact_id', 'statistic_images': 'image_id',
}
ORDER = ['publications', 'statistics', 'stat_tables', 'footnotes',
         'contacts', 'statistic_images']

TABLE_LIST_SQL = ", ".join(ORDER)
TRUNCATE_SQL = f'TRUNCATE {TABLE_LIST_SQL} RESTART IDENTITY CASCADE;'

SEARCH_DOC_SQL = """
UPDATE statistics SET search_doc = to_tsvector(
    'simple',
    coalesce(title_ko,'') || ' ' ||
    coalesce(title_en,'') || ' ' ||
    coalesce(chapter,'') || ' ' ||
    coalesce(ref_id,'')
);
""".strip()


def insert_sql(table: str, columns: list[str]) -> str:
    column_sql = ", ".join(columns)
    placeholders = ", ".join("%s" for _ in columns)
    return f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})"


def setval_sql(table: str, pk: str) -> str:
    max_id_sql = f"COALESCE((SELECT MAX({pk}) FROM {table}),1)"
    sequence_sql = f"pg_get_serial_sequence('{table}','{pk}')"
    return f"SELECT setval({sequence_sql}, {max_id_sql});"


# jsonb 캐스팅이 필요한 컬럼 위치를 찾는다.
def jsonb_index(table: str, columns: list[str]) -> int | None:
    if table not in JSONB_COL:
        return None
    return columns.index(JSONB_COL[table])


# 실 DB 적재용 레코드로 변환한다.
def live_record(row: tuple, jsonb_idx: int | None, jsonb_type) -> tuple:
    values = list(row)
    if jsonb_idx is not None and values[jsonb_idx] is not None:
        values[jsonb_idx] = jsonb_type(json.loads(values[jsonb_idx]))
    return tuple(values)


# 테이블 행 목록을 실 DB 적재용 레코드 목록으로 변환한다.
def live_records(table: str, data: list, jsonb_type) -> list[tuple]:
    columns = COLS[table]
    idx = jsonb_index(table, columns)
    return [live_record(row, idx, jsonb_type) for row in data]


# ── (1) 실서버 적재 ─────────────────────────────────────────────
def load_live(rows, dsn):
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(TRUNCATE_SQL)          # 기존 데이터 전부 삭제 후 재적재
        for tbl in ORDER:
            data = rows[tbl]
            if not data:
                continue
            cols = COLS[tbl]
            recs = live_records(tbl, data, Jsonb)
            cur.executemany(insert_sql(tbl, cols), recs)
            print(f'  {tbl:18} {len(recs):>5} rows')
        # 시퀀스 보정 + tsvector
        for tbl, pk in SEQ.items():
            cur.execute(setval_sql(tbl, pk))
        cur.execute(SEARCH_DOC_SQL)
        conn.commit()
    print('완료(commit).  embedding은 --embed 또는 별도 스크립트로 채우세요.')


# ── (2) SQL 파일 생성 ───────────────────────────────────────────
def sql_lit(v):
    if v is None:
        return 'NULL'
    if isinstance(v, (int, float)):
        return str(v)
    escaped = str(v).replace("'", "''")
    return f"'{escaped}'"


# SQL 파일용 값 목록을 만든다.
def sql_values(row: tuple, jsonb_idx: int | None) -> list[str]:
    values = []
    for index, value in enumerate(row):
        literal = sql_lit(value)
        if index == jsonb_idx and value is not None:
            literal = f'{literal}::jsonb'
        values.append(literal)
    return values


# INSERT 문 한 줄을 만든다.
def insert_row_sql(table: str, column_sql: str, values: list[str]) -> str:
    value_sql = ", ".join(values)
    return f'INSERT INTO {table} ({column_sql}) VALUES ({value_sql});'


# 한 테이블의 INSERT 문들을 파일에 쓴다.
def write_table_sql(file, table: str, data: list) -> None:
    columns = COLS[table]
    column_sql = ", ".join(columns)
    idx = jsonb_index(table, columns)

    file.write(f'\n-- {table} ({len(data)} rows)\n')
    for row in data:
        values = sql_values(row, idx)
        file.write(f'{insert_row_sql(table, column_sql, values)}\n')


# 시퀀스 보정 SQL을 파일에 쓴다.
def write_setval_sql(file) -> None:
    file.write('\n-- 시퀀스 보정\n')
    for table, pk in SEQ.items():
        file.write(f'{setval_sql(table, pk)}\n')


# 전문검색 컬럼 갱신 SQL을 파일에 쓴다.
def write_search_doc_sql(file) -> None:
    file.write('\n-- 전문검색 컬럼\n')
    file.write(f'{SEARCH_DOC_SQL}\n')


def emit_sql(rows, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('BEGIN;\n')
        f.write('\n-- 기존 데이터 전부 삭제 후 재적재\n')
        f.write(f'{TRUNCATE_SQL}\n')
        for tbl in ORDER:
            data = rows[tbl]
            if not data:
                continue
            write_table_sql(f, tbl, data)
        write_setval_sql(f)
        write_search_doc_sql(f)
        f.write('COMMIT;\n')
    print(f'-> {path}')


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SEED = os.path.join(ROOT_DIR, 'db', 'seeds', 'load_all.sql')


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument('parsed_json')
    ap.add_argument('--dsn',
                    default=os.environ.get('STATYEARBOOK_DSN')
                    or os.environ.get('DATABASE_URL'),
                    help='postgresql://user:pw@host:port/db '
                         '(미지정 시 .env 의 STATYEARBOOK_DSN, 없으면 DATABASE_URL 사용)')
    ap.add_argument('--emit-sql', default=DEFAULT_SEED,
                    help='INSERT문 .sql 저장 경로(기본 db/seeds/load_all.sql, 빈값이면 미저장)')
    ap.add_argument('--no-db', action='store_true',
                    help='실 DB 적재를 건너뛰고 SQL 파일만 생성')
    return ap


def load_json(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def row_counts(rows: dict) -> dict:
    return {table: len(data) for table, data in rows.items()}


def ensure_parent_dir(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)


def maybe_emit_sql(rows: dict, path: str) -> None:
    if not path:
        return
    ensure_parent_dir(path)
    emit_sql(rows, path)


def run(args) -> None:
    data = load_json(args.parsed_json)
    rows = build_rows(data)
    print('적재 대상:', row_counts(rows))

    maybe_emit_sql(rows, args.emit_sql)

    if args.no_db:
        print('--no-db: 실 DB 적재를 건너뜁니다.')
    elif args.dsn:
        load_live(rows, args.dsn)
    else:
        print('\nDSN 미지정: 실 DB 적재를 건너뜁니다. '
              '.env 의 STATYEARBOOK_DSN 또는 --dsn 을 지정하세요.', file=sys.stderr)


def main() -> None:
    args = build_parser().parse_args()
    run(args)


if __name__ == '__main__':
    main()
