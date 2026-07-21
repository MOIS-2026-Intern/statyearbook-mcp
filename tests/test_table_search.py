import unittest

from shared.table_search import build_table_search_chunks


class TableSearchChunkTests(unittest.TestCase):
    def test_extracts_headers_and_non_numeric_labels(self) -> None:
        statistic = {
            "chapter": "일반행정",
            "level3_title": "민원행정",
            "title_ko": "안심상속 원스톱서비스",
        }
        table = {
            "body": {
                "columns": ["연도 Year", "사망신고 건수 No. of Death Reports"],
                "records": [
                    {"연도 Year": "2024", "사망신고 건수 No. of Death Reports": "360,757"},
                    {"연도 Year": "구분 합계", "사망신고 건수 No. of Death Reports": "-"},
                ],
            }
        }

        chunks = build_table_search_chunks(statistic, table)

        self.assertEqual(chunks[0]["chunk_kind"], "headers")
        self.assertIn("사망신고 건수", chunks[0]["search_text"])
        self.assertEqual(chunks[1]["chunk_kind"], "labels")
        self.assertEqual(chunks[1]["search_labels"], ["구분 합계"])
        self.assertNotIn("360,757", chunks[1]["search_text"])

    def test_splits_long_categorical_values_into_stable_chunks(self) -> None:
        table = {
            "body": {
                "columns": ["기관"],
                "records": [{"기관": f"기관 {index}"} for index in range(10)],
            }
        }

        chunks = build_table_search_chunks({"title_ko": "기관별 현황"}, table, max_chars=15)

        label_chunks = [chunk for chunk in chunks if chunk["chunk_kind"] == "labels"]
        self.assertGreater(len(label_chunks), 1)
        self.assertEqual(
            [chunk["chunk_no"] for chunk in label_chunks],
            list(range(1, len(label_chunks) + 1)),
        )


if __name__ == "__main__":
    unittest.main()
