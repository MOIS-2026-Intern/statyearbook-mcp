import unittest

from app.tool_descriptions import SEARCH_STATISTICS, SEARCH_TABLES, VISUALIZE
from backend.prompts import (
    SEARCH_TABLES_RESULT_PROMPT,
    SYSTEM_PROMPT,
    VISUALIZE_RESULT_PROMPT,
    build_system_prompt,
)


class PromptContractTests(unittest.TestCase):
    def test_system_prompt_keeps_only_shared_workflow_rules(self) -> None:
        self.assertIn("stat_id를 모르면 search_statistics", SYSTEM_PROMPT)
        self.assertIn("각 도구의 용도", SYSTEM_PROMPT)
        self.assertNotIn("column_family", SYSTEM_PROMPT)
        self.assertNotIn("Vega-Lite", SYSTEM_PROMPT)

    def test_search_statistics_requires_table_lookup_for_values(self) -> None:
        self.assertIn("통계 수치를 답할 때", SEARCH_STATISTICS)
        self.assertIn("search_tables", SEARCH_STATISTICS)

    def test_search_tables_tool_description_only_owns_lookup_rules(self) -> None:
        self.assertIn("반환된 unit", SEARCH_TABLES)
        self.assertNotIn("Markdown 표", SEARCH_TABLES)

    def test_search_tables_result_prompt_owns_answer_format(self) -> None:
        self.assertIn("Markdown 표 형식을 우선", SEARCH_TABLES_RESULT_PROMPT)
        self.assertIn("영문 병기", SEARCH_TABLES_RESULT_PROMPT)
        self.assertNotIn("반드시", SEARCH_TABLES_RESULT_PROMPT)

    def test_result_prompt_is_added_only_after_matching_tool(self) -> None:
        initial_prompt = build_system_prompt()
        table_prompt = build_system_prompt(("search_tables",))

        self.assertNotIn("search_tables 결과 응답 형식", initial_prompt)
        self.assertIn("search_tables 결과 응답 형식", table_prompt)
        self.assertNotIn("visualize 결과 응답 형식", table_prompt)

    def test_visualize_description_keeps_call_rules(self) -> None:
        self.assertIn("filters와 metrics", VISUALIZE)
        self.assertNotIn("6줄 이내", VISUALIZE)

    def test_visualize_result_uses_separate_markdown_paragraphs(self) -> None:
        self.assertIn("빈 줄을 하나 넣어", VISUALIZE_RESULT_PROMPT)
        self.assertIn("별도의 Markdown 문단", VISUALIZE_RESULT_PROMPT)
        self.assertIn("빈 줄 다음의 둘째 줄", VISUALIZE_RESULT_PROMPT)


if __name__ == "__main__":
    unittest.main()
