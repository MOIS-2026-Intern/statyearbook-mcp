# -*- coding: utf-8 -*-
"""통계표 담당 정보 도구의 PostgreSQL 조회를 담당한다."""
from collections.abc import Callable
from typing import Any

from app.db import connect

STAT_SQL = """
    SELECT stat_id, year AS publication_year, ref_id,
           level3_title, level4_title, title_ko
    FROM statistics
    WHERE stat_id = %s
"""
CONTACTS_SQL = """
    SELECT dept, officer, phone, source_system, source_url
    FROM contacts
    WHERE stat_id = %s
    ORDER BY contact_id
"""


class ContactRepository:
    def __init__(self, connection_factory: Callable[[], Any] = connect):
        self._connection_factory = connection_factory

    # 담당 정보 응답에 필요한 통계표 문맥을 조회한다.
    def select_statistic(self, cur, stat_id: int) -> dict | None:
        cur.execute(STAT_SQL, (stat_id,))
        return cur.fetchone()

    # 한 통계표에 연결된 담당 정보 행을 순서대로 조회한다.
    def select_contacts(self, cur, stat_id: int) -> list[dict]:
        cur.execute(CONTACTS_SQL, (stat_id,))
        return cur.fetchall()

    # 한 통계표의 문맥과 담당 정보를 같은 트랜잭션에서 조회한다.
    def select_contact_data(self, stat_id: int) -> tuple[dict | None, list[dict]]:
        with self._connection_factory() as conn, conn.cursor() as cur:
            stat = self.select_statistic(cur, stat_id)
            if stat is None:
                return None, []
            return stat, self.select_contacts(cur, stat_id)
