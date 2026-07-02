# -*- coding: utf-8 -*-
"""search_tables 도구.

통계표의 실제 표 값(마크다운)과 주석/출처를 가져온다.
"""
from mcp.server.fastmcp import FastMCP

from app.db import connect


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def search_tables(stat_id: int) -> dict:
        """통계표의 실제 표 값(마크다운)을 가져온다.

        search_statistics 로 관련 통계표를 찾아 stat_id 를 얻은 뒤, 그 stat_id 를
        넘기면 해당 통계표의 표 본문을 마크다운으로 돌려준다. LLM은 이 마크다운을
        그대로 사용자에게 표로 보여주면 된다. 단위/기준일은 caption 에, 세부 설명은
        footnotes(주석)에, 자료 출처는 source 에 담겨 있으니 함께 안내한다.

        한 통계표에 표가 여러 개(seq 1..N)일 수 있으므로 tables 는 리스트로 반환된다.

        Args:
            stat_id: search_statistics 결과의 stat_id.

        Returns:
            dict: {"found", "stat_id", "year", "title_ko", "title_en", "unit",
                   "base_date", "tables": [{seq, caption, n_rows, n_cols, table_md}],
                   "footnotes": [...], "source": [...]}
                  해당 stat_id 가 없으면 {"found": False, ...}.
        """
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT stat_id, year, title_ko, title_en, unit, base_date, ref_id
                   FROM statistics WHERE stat_id = %s""",
                (stat_id,),
            )
            stat = cur.fetchone()
            if stat is None:
                return {"found": False, "stat_id": stat_id, "tables": []}

            cur.execute(
                """SELECT seq, caption, n_rows, n_cols, table_md
                   FROM stat_tables WHERE stat_id = %s ORDER BY seq""",
                (stat_id,),
            )
            tables = cur.fetchall()

            cur.execute(
                """SELECT seq, note_no, content
                   FROM footnotes WHERE stat_id = %s ORDER BY seq""",
                (stat_id,),
            )
            footnotes = cur.fetchall()

            cur.execute(
                """SELECT dept, officer, phone, source_system, source_url
                   FROM contacts WHERE stat_id = %s""",
                (stat_id,),
            )
            source = cur.fetchall()

        return {
            "found": True,
            "stat_id": stat["stat_id"],
            "ref_id": stat["ref_id"],
            "year": stat["year"],
            "title_ko": stat["title_ko"],
            "title_en": stat["title_en"],
            "unit": stat["unit"],
            "base_date": stat["base_date"],
            "tables": [
                {
                    "seq": t["seq"],
                    "caption": t["caption"],
                    "n_rows": t["n_rows"],
                    "n_cols": t["n_cols"],
                    "table_md": t["table_md"],
                }
                for t in tables
            ],
            "footnotes": [
                {"seq": f["seq"], "note_no": f["note_no"], "content": f["content"]}
                for f in footnotes
            ],
            "source": [
                {
                    "dept": s["dept"],
                    "officer": s["officer"],
                    "phone": s["phone"],
                    "source_system": s["source_system"],
                    "source_url": s["source_url"],
                }
                for s in source
            ],
        }
