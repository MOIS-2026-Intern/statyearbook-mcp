import unittest

from app.table_cache import cache_table, clear_table_cache, get_cached_table


class TableCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_table_cache()

    def test_cached_handle_reuses_original_body_without_sharing_mutations(self) -> None:
        table = {
            "stat_id": 31,
            "ref_id": "2-1-4",
            "year": 2025,
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


if __name__ == "__main__":
    unittest.main()
