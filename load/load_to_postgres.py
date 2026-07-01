#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
load_to_postgres.py
parse_yearbook.py 가 만든 parsed_yearbook.json 을 schema.sql 스키마에 적재한다.

기본 동작(옵션 없이 실행):
  python load_to_postgres.py parsed_yearbook.json
  -> ① db/seeds/load_all.sql 로 DML 을 저장하고
     ② .env 의 STATYEARBOOK_DSN(없으면 DATABASE_URL)이 있으면 실 DB 에도 적재한다.

옵션:
  --emit-sql PATH  : DML 저장 경로 변경(기본 db/seeds/load_all.sql). ''(빈값)이면 미저장.
  --dsn DSN        : 적재 대상 DSN 직접 지정(미지정 시 .env 의 STATYEARBOOK_DSN 사용).
  --no-db          : 실 DB 적재를 건너뛰고 SQL 파일만 생성.

적재는 항상 기존 데이터를 전부 비우고(TRUNCATE ... RESTART IDENTITY CASCADE) 다시 넣는다.
PK(stat_id 등)는 파이썬에서 명시적으로 부여하여 FK 연결을 결정적으로 만든다.
끝에서 시퀀스를 setval 로 맞추고, search_doc(tsvector)를 채운다.
embedding(vector)은 임베딩 모델이 필요하므로 별도 스크립트로 처리(기본 NULL).
"""
import json, argparse, sys, os
from dotenv import load_dotenv

load_dotenv()  # .env 의 STATYEARBOOK_DSN 등을 환경변수로 로드


# ── parsed json -> 각 테이블의 행(tuple) 리스트로 평탄화 ──────────────
def build_rows(data):
    pub = data['publication']
    pub_id = 1
    publications = [(pub_id, pub['year'], pub.get('pub_no'),
                     pub['title'], pub.get('page_count'))]

    statistics, stat_tables, footnotes, contacts, images = [], [], [], [], []
    sid = tid = nid = cid = iid = 0

    for u in data['statistics']:
        sid += 1
        statistics.append((
            sid, pub_id, pub['year'], u.get('ref_id'),
            u.get('chapter_no'), u.get('section_no'),
            u.get('chapter'), u.get('section'),
            u['title_ko'], u.get('title_en'),
            u.get('unit'), u.get('base_date'), u.get('page_start'),
        ))
        for t in u['tables']:
            tid += 1
            stat_tables.append((
                tid, sid, t.get('seq'), t.get('caption'),
                t.get('n_rows'), t.get('n_cols'),
                json.dumps(t['body'], ensure_ascii=False),   # -> ::jsonb
                t.get('table_md'),
            ))
        for f in u['footnotes']:
            nid += 1
            footnotes.append((nid, sid, f.get('seq'),
                              f.get('note_no'), f.get('content')))
        for c in u['contacts']:
            cid += 1
            contacts.append((cid, sid, c.get('dept'), c.get('officer'),
                             c.get('phone'), c.get('source_system'),
                             c.get('source_url')))
        for im in u['images']:
            iid += 1
            images.append((iid, sid, im.get('filename'), im.get('page'),
                           im.get('uri'), im.get('caption')))

    return {'publications': publications, 'statistics': statistics,
            'stat_tables': stat_tables, 'footnotes': footnotes,
            'contacts': contacts, 'statistic_images': images}


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

TRUNCATE_SQL = 'TRUNCATE ' + ', '.join(ORDER) + ' RESTART IDENTITY CASCADE;'

SEARCH_DOC_SQL = (
    "UPDATE statistics SET search_doc = to_tsvector('simple', "
    "coalesce(title_ko,'')||' '||coalesce(title_en,'')||' '||"
    "coalesce(chapter,'')||' '||coalesce(ref_id,''));"
)


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
            ji = cols.index(JSONB_COL[tbl]) if tbl in JSONB_COL else None
            recs = []
            for r in data:
                r = list(r)
                if ji is not None and r[ji] is not None:
                    r[ji] = Jsonb(json.loads(r[ji]))
                recs.append(tuple(r))
            ph = ', '.join(['%s'] * len(cols))
            cur.executemany(
                f'INSERT INTO {tbl} ({", ".join(cols)}) VALUES ({ph})', recs)
            print(f'  {tbl:18} {len(recs):>5} rows')
        # 시퀀스 보정 + tsvector
        for tbl, pk in SEQ.items():
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{tbl}','{pk}'), "
                f"COALESCE((SELECT MAX({pk}) FROM {tbl}),1));")
        cur.execute(SEARCH_DOC_SQL)
        conn.commit()
    print('완료(commit).  embedding은 --embed 또는 별도 스크립트로 채우세요.')


# ── (2) SQL 파일 생성 ───────────────────────────────────────────
def sql_lit(v):
    if v is None:
        return 'NULL'
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def emit_sql(rows, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('BEGIN;\n')
        f.write('\n-- 기존 데이터 전부 삭제 후 재적재\n')
        f.write(TRUNCATE_SQL + '\n')
        for tbl in ORDER:
            data = rows[tbl]
            if not data:
                continue
            cols = COLS[tbl]
            ji = cols.index(JSONB_COL[tbl]) if tbl in JSONB_COL else None
            f.write(f'\n-- {tbl} ({len(data)} rows)\n')
            for r in data:
                vals = []
                for k, v in enumerate(r):
                    if k == ji and v is not None:
                        vals.append(sql_lit(v) + '::jsonb')
                    else:
                        vals.append(sql_lit(v))
                f.write(f'INSERT INTO {tbl} ({", ".join(cols)}) '
                        f'VALUES ({", ".join(vals)});\n')
        f.write('\n-- 시퀀스 보정\n')
        for tbl, pk in SEQ.items():
            f.write(f"SELECT setval(pg_get_serial_sequence('{tbl}','{pk}'), "
                    f"COALESCE((SELECT MAX({pk}) FROM {tbl}),1));\n")
        f.write('\n-- 전문검색 컬럼\n')
        f.write(SEARCH_DOC_SQL + '\n')
        f.write('COMMIT;\n')
    print(f'-> {path}')


DEFAULT_SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'db', 'seeds', 'load_all.sql')

if __name__ == '__main__':
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
    args = ap.parse_args()

    data = json.load(open(args.parsed_json, encoding='utf-8'))
    rows = build_rows(data)
    counts = {k: len(v) for k, v in rows.items()}
    print('적재 대상:', counts)

    if args.emit_sql:
        os.makedirs(os.path.dirname(os.path.abspath(args.emit_sql)), exist_ok=True)
        emit_sql(rows, args.emit_sql)

    if args.no_db:
        print('--no-db: 실 DB 적재를 건너뜁니다.')
    elif args.dsn:
        load_live(rows, args.dsn)
    else:
        print('\nDSN 미지정: 실 DB 적재를 건너뜁니다. '
              '.env 의 STATYEARBOOK_DSN 또는 --dsn 을 지정하세요.', file=sys.stderr)
