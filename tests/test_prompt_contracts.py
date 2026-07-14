import unittest

from app.tool_descriptions import SEARCH_STATISTICS, SEARCH_TABLES, VISUALIZE
from backend.prompts import SYSTEM_PROMPT


class PromptContractTests(unittest.TestCase):
    def test_system_prompt_keeps_only_shared_workflow_rules(self) -> None:
        self.assertIn("stat_id를 모르면 search_statistics", SYSTEM_PROMPT)
        self.assertIn("각 도구의 용도", SYSTEM_PROMPT)
        self.assertNotIn("column_family", SYSTEM_PROMPT)
        self.assertNotIn("Vega-Lite", SYSTEM_PROMPT)

    def test_search_statistics_requires_table_lookup_for_values(self) -> None:
        self.assertIn("통계 수치를 답할 때", SEARCH_STATISTICS)
        self.assertIn("search_tables", SEARCH_STATISTICS)

    def test_search_tables_owns_table_and_unit_answer_rules(self) -> None:
        self.assertIn("Markdown 표", SEARCH_TABLES)
        self.assertIn("반환된 unit", SEARCH_TABLES)
        self.assertIn("'-'는 0으로 바꾸지 않고", SEARCH_TABLES)

    def test_visualize_owns_visualization_answer_rules(self) -> None:
        self.assertIn("6줄 이내", VISUALIZE)
        self.assertIn("데이터 포인트 수", VISUALIZE)


if __name__ == "__main__":
    unittest.main()
