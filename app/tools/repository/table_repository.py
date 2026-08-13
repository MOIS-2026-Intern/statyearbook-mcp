# -*- coding: utf-8 -*-
"""통계표 원문과 부속 메타데이터의 PostgreSQL 조회를 담당한다."""
from collections.abc import Callable
from typing import Any

from app.db import connect
from app.tools.repository.contact_repository import ContactRepository


STAT_SQL = """
    SELECT s.stat_id, p.publication_kind, s.year AS publication_year, s.ref_id,
           chapter_no, section_no, level3_no, level4_no,
           chapter, section, level3_title, level4_title,
           title_ko, title_en, unit, base_date, page_start
    FROM statistics s
    JOIN publications p ON p.pub_id = s.pub_id
    WHERE s.stat_id = %s
"""
TABLES_SQL = """
    SELECT seq, caption, n_rows, n_cols, body, table_md
    FROM stat_tables
    WHERE stat_id = %s
    ORDER BY seq
"""
FOOTNOTES_SQL = """
    SELECT seq, note_no, content
    FROM footnotes
    WHERE stat_id = %s
    ORDER BY seq
"""


class TableRepository:
    def __init__(
        self,
        contact_repository: ContactRepository | None = None,
        connection_factory: Callable[[], Any] = connect,
    ):
        self._contact_repository = contact_repository or ContactRepository()
        self._connection_factory = connection_factory

    # 한 통계표의 본문·주석·담당 정보 원천 행을 같은 트랜잭션에서 조회한다.
    def select_table_data(self, stat_id: int) -> tuple[dict | None, list, list, list]:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(STAT_SQL, (stat_id,))
            stat = cur.fetchone()
            if stat is None:
                return None, [], [], []

            cur.execute(TABLES_SQL, (stat_id,))
            tables = cur.fetchall()
            cur.execute(FOOTNOTES_SQL, (stat_id,))
            footnotes = cur.fetchall()
            contacts = self._contact_repository.select_contacts(cur, stat_id)
        return stat, tables, footnotes, contacts
