import unittest

from app.table_cache import cache_table, clear_table_cache, get_cached_table
from app.tools.search_tables import build_response


class TableCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_table_cache()

    def test_cached_handle_reuses_original_body_without_sharing_mutations(self) -> None:
        table = {
            "stat_id": 31,
            "ref_id": "2-1-4",
            "publication_year": 2025,
            "title_ko": "보조금24",
            "title_en": "Subsidies",
            "unit": "건, %",
            "base_date": "2024.12.31.",
            "table_seq": 1,
            "caption": "기준일",
            "n_rows": 2,
            "n_cols": 2,
            "body": {
                "columns": ["지역", "이용건수"],
                "records": [{"지역": "서울", "이용건수": "10"}],
            },
            "table_md": "| 지역 | 이용건수 |",
        }

        handle = cache_table(table)
        table["body"]["records"][0]["이용건수"] = "99"
        cached = get_cached_table(handle)

        self.assertIsNotNone(cached)
        self.assertEqual(cached["stat_id"], 31)
        self.assertEqual(cached["table_seq"], 1)
        self.assertEqual(cached["body"]["records"][0]["이용건수"], "10")

        cached["body"]["records"][0]["이용건수"] = "77"
        self.assertEqual(get_cached_table(handle)["body"]["records"][0]["이용건수"], "10")

    def test_search_tables_response_and_cache_include_title_hierarchy(self) -> None:
        stat = {
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
        table = {
            "seq": 1,
            "caption": None,
            "n_rows": 2,
            "n_cols": 2,
            "body": {"columns": ["연도", "건수"], "records": []},
            "table_md": "| 연도 | 건수 |",
        }

        response = build_response(stat, [table], [], [])
        cached = get_cached_table(response["tables"][0]["table_handle"])

        self.assertEqual(response["level3_title"], "모바일 신분증")
        self.assertEqual(response["level4_title"], "모바일 공무원증")
        self.assertEqual(cached["level3_title"], "모바일 신분증")
        self.assertEqual(cached["level4_title"], "모바일 공무원증")


if __name__ == "__main__":
    unittest.main()
