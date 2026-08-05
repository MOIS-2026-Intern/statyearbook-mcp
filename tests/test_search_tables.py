# -*- coding: utf-8 -*-
"""search_tables 도구가 통계표 본문과 메타데이터를 반환하는지 검증한다."""
import unittest

from app.table_cache import clear_table_cache, get_cached_table
from app.tools.service.table_service import build_response


STAT = {
    "stat_id": 32,
    "ref_id": "3-1-7-1",
    "publication_year": 2025,
    "chapter_no": 3,
    "section_no": 1,
    "level3_no": 7,
    "level4_no": 1,
    "chapter": "디지털정부",
    "section": "디지털 정책과 서비스",
    "level3_title": "모바일 신분증",
    "level4_title": "모바일 공무원증",
    "title_ko": "모바일 공무원증",
    "title_en": "Mobile Identification for Public Officials",
    "unit": "건",
    "base_date": "2024.12.31.",
    "page_start": 72,
}

TABLE = {
    "seq": 1,
    "caption": "2024. 12. 31. 기준",
    "n_rows": 1,
    "n_cols": 2,
    "body": {
        "columns": ["연도", "건수"],
        "records": [{"연도": "2024", "건수": "1,234"}],
    },
    "table_md": "| 연도 | 건수 |",
}
SOURCE = {
    "department": "디지털안전정책과",
    "officer": "홍길동",
    "phone": "044-205-0000",
    "source_system": None,
    "source_url": None,
}


class SearchTablesTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_table_cache()

    # 응답은 표 메타데이터를 담고, 발급한 handle로 원본 본문을 다시 꺼낼 수 있어야 한다.
    def test_returns_table_metadata_and_cached_body(self) -> None:
        response = build_response(STAT, [TABLE], [], [SOURCE])

        self.assertTrue(response["found"])
        self.assertEqual(response["stat_id"], 32)
        self.assertEqual(response["ref_id"], "3-1-7-1")
        self.assertEqual(response["title_ko"], "모바일 공무원증")
        self.assertEqual(response["level3_title"], "모바일 신분증")
        self.assertEqual(response["level4_title"], "모바일 공무원증")
        self.assertEqual(response["unit"], "건")
        self.assertEqual(len(response["tables"]), 1)
        self.assertEqual(response["tables"][0]["table_md"], "| 연도 | 건수 |")
        self.assertEqual(response["source"][0]["dept"], "디지털안전정책과")
        self.assertEqual(response["source"][0]["officer"], "홍길동")

        cached = get_cached_table(response["tables"][0]["table_handle"])
        self.assertEqual(cached["stat_id"], 32)
        self.assertEqual(cached["body"]["columns"], ["연도", "건수"])
        self.assertEqual(cached["body"]["records"], [{"연도": "2024", "건수": "1,234"}])


if __name__ == "__main__":
    unittest.main()
