# 이 파일은 PostgreSQL의 발간물 목록 조회와 관련 데이터 전체 삭제를 담당한다.
# statistics 하위 cascade와 임베딩 작업·profile 정리를 하나의 트랜잭션으로 묶는다.
from __future__ import annotations

import psycopg

from psycopg.rows import dict_row

from admin.backend.errors import PublicationsNotFoundError


PUBLICATION_WRITE_LOCK_ID = 7_824_601_025


class PublicationRepository:
    def select_publications(self, dsn: str) -> list[dict]:
        with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT pub_id, year, pub_no, title
                FROM publications
                ORDER BY year DESC, pub_id DESC
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def delete_publications(self, dsn: str, pub_ids: list[int]) -> dict:
        selected_ids = sorted(set(pub_ids))
        with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (PUBLICATION_WRITE_LOCK_ID,))
            cur.execute(
                """
                SELECT pub_id, year, pub_no, title
                FROM publications
                WHERE pub_id = ANY(%s)
                ORDER BY year DESC, pub_id DESC
                FOR UPDATE
                """,
                (selected_ids,),
            )
            publications = [dict(row) for row in cur.fetchall()]
            found_ids = {int(row["pub_id"]) for row in publications}
            missing_ids = sorted(set(selected_ids) - found_ids)
            if missing_ids:
                raise PublicationsNotFoundError(missing_ids)

            cur.execute(
                """
                WITH selected_statistics AS (
                    SELECT stat_id FROM statistics WHERE pub_id = ANY(%s)
                )
                SELECT
                    (SELECT COUNT(*) FROM selected_statistics) AS statistics,
                    (SELECT COUNT(*) FROM stat_tables t
                     JOIN selected_statistics s ON s.stat_id = t.stat_id) AS stat_tables,
                    (SELECT COUNT(*) FROM footnotes f
                     JOIN selected_statistics s ON s.stat_id = f.stat_id) AS footnotes,
                    (SELECT COUNT(*) FROM contacts c
                     JOIN selected_statistics s ON s.stat_id = c.stat_id) AS contacts
                """,
                (selected_ids,),
            )
            related_counts = dict(cur.fetchone())
            source_names = [f"statistics:{row['year']}" for row in publications]
            cur.execute(
                """
                SELECT DISTINCT profile_key
                FROM embedding_jobs
                WHERE source_name = ANY(%s)
                UNION
                SELECT DISTINCT embedding_profile_key
                FROM statistics
                WHERE pub_id = ANY(%s) AND embedding_profile_key IS NOT NULL
                """,
                (source_names, selected_ids),
            )
            profile_keys = [row["profile_key"] for row in cur.fetchall()]

            cur.execute(
                "DELETE FROM embedding_jobs WHERE source_name = ANY(%s)",
                (source_names,),
            )
            related_counts["embedding_jobs"] = cur.rowcount
            cur.execute("DELETE FROM statistics WHERE pub_id = ANY(%s)", (selected_ids,))
            if cur.rowcount != related_counts["statistics"]:
                raise RuntimeError("statistics changed while deleting publications")
            cur.execute(
                "DELETE FROM publications WHERE pub_id = ANY(%s)",
                (selected_ids,),
            )
            if cur.rowcount != len(publications):
                raise RuntimeError("publications changed while deleting")

            deleted_profiles = 0
            if profile_keys:
                cur.execute(
                    """
                    DELETE FROM embedding_profiles p
                    WHERE p.profile_key = ANY(%s)
                      AND NOT EXISTS (
                          SELECT 1 FROM statistics s
                          WHERE s.embedding_profile_key = p.profile_key
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM embedding_jobs j
                          WHERE j.profile_key = p.profile_key
                      )
                    """,
                    (profile_keys,),
                )
                deleted_profiles = cur.rowcount
            related_counts["embedding_profiles"] = deleted_profiles
            related_counts["publications"] = len(publications)
            conn.commit()
        return {
            "deleted_publications": publications,
            "deleted_counts": related_counts,
        }
