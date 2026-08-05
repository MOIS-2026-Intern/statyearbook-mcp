# -*- coding: utf-8 -*-
"""시각화 도구에 필요한 통계표 원천 행의 PostgreSQL 조회를 담당한다."""
from collections.abc import Callable
from typing import Any

from app.db import connect


TABLE_SQL = """
    SELECT s.stat_id, s.ref_id,
           s.chapter_no, s.section_no, s.level3_no, s.level4_no,
           s.chapter, s.section, s.level3_title, s.level4_title,
           s.title_ko, s.title_en, s.unit, s.base_date, s.page_start,
           s.year AS publication_year,
           t.seq AS table_seq, t.caption, t.n_rows, t.n_cols,
           t.body, t.table_md
    FROM statistics s
    JOIN stat_tables t ON t.stat_id = s.stat_id
    WHERE s.stat_id = %s
    ORDER BY t.seq
"""


class VisualizationRepository:
    def __init__(self, connection_factory: Callable[[], Any] = connect):
        self._connection_factory = connection_factory

    # 같은 stat_id에 속한 모든 표 조각을 순서대로 조회한다.
    def select_table_rows(self, stat_id: int) -> list[dict]:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(TABLE_SQL, (stat_id,))
            return list(cur.fetchall())
