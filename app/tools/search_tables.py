# -*- coding: utf-8 -*-
from mcp.server.fastmcp import FastMCP

from app.db import connect


# search_tables MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # stat_id에 해당하는 표 본문과 메타데이터를 가져온다.
    @mcp.tool()
    def search_tables(stat_id: int) -> dict:
        """통계표의 표 본문과 메타데이터를 가져온다."""
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
