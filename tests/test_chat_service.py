import unittest

from backend.services.chat_service import _model_result_for_tool


class ChatServiceModelResultTests(unittest.TestCase):
    def test_visualize_result_is_compacted_for_model_but_keeps_answer_metadata(self) -> None:
        result = {
            "content": [{"type": "text", "text": "긴 시각화 설명"}],
            "structuredContent": {
                "ok": True,
                "stat": {
                    "stat_id": 8,
                    "ref_id": "1-1-5",
                    "publication_year": 2025,
                    "title_ko": "행정기관 위원회",
                    "unit": "개",
                    "base_date": "2024.12.31.",
                    "table_seq": 2,
                },
                "chart": {
                    "title": "행정기관 위원회 - 2024",
                    "type": "bar",
                    "decision_source": "selection_plan",
                    "reason": "원본 표와 대조한 행과 지표를 사용했습니다.",
                },
                "request": {"year": 2024, "metrics": ["대통령", "국무총리", "각 부처"]},
                "data": {"record_count": 3, "records": [{"x": "대통령", "value": 19}]},
                "vega_lite": {"mark": "bar", "data": {"values": []}},
                "warnings": [],
            },
            "isError": False,
        }

        compact = _model_result_for_tool("visualize", result)
        structured = compact["structuredContent"]

        self.assertTrue(structured["visualization_created"])
        self.assertEqual(structured["stat"]["title_ko"], "행정기관 위원회")
        self.assertEqual(structured["stat"]["stat_id"], 8)
        self.assertNotIn("vega_lite", structured)
        self.assertNotIn("data", structured)
        self.assertNotIn("request", structured)
        self.assertNotIn("decision_source", structured["chart"])
        self.assertNotIn("type", structured["chart"])
        self.assertNotIn("reason", structured["chart"])

    def test_non_visualize_result_is_not_compacted(self) -> None:
        result = {"structuredContent": {"count": 1}, "isError": False}

        self.assertIs(_model_result_for_tool("search_statistics", result), result)


if __name__ == "__main__":
    unittest.main()
