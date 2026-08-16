# -*- coding: utf-8 -*-
"""도구별 결과 표현 규칙이 모델 프롬프트에 포함되는지 검증한다."""
import unittest

from backend.prompts import (
    ALL_PUBLICATIONS_SCOPE_PROMPT,
    COMPARE_PUBLICATIONS_RESULT_PROMPT,
    MAJOR_STATISTICS_SCOPE_PROMPT,
    YEARBOOK_SCOPE_PROMPT,
    build_system_prompt,
)


class ToolResultPromptTests(unittest.TestCase):
    # 발간판 비교 결과의 ref_id는 화면 표에서 자연스러운 한국어 제목으로 보여야 한다.
    def test_compare_publications_uses_catalog_number_table_header(self) -> None:
        prompt = build_system_prompt(["compare_publications"])

        self.assertIn(COMPARE_PUBLICATIONS_RESULT_PROMPT, prompt)
        self.assertIn("`목차 번호`", prompt)
        self.assertIn("원시 필드명을 제목 행에 노출하지 않습니다", prompt)


class StatisticalCalculationPromptTests(unittest.TestCase):
    # 상관계수 같은 통계량은 도구가 산출하지 않으므로 어떤 도구를 거쳤든 모델이 직접 계산해야 한다.
    def test_calculation_rule_applies_to_every_tool_context(self) -> None:
        for tools in ([], ["search_tables"], ["visualize"], ["search_tables", "visualize"]):
            with self.subTest(tools=tools):
                prompt = build_system_prompt(tools)

                self.assertIn("상관계수", prompt)
                self.assertIn("당신이 직접 계산해 답합니다", prompt)

    # 시각화 결과를 받은 뒤에도 함께 요구한 통계량 계산을 거르지 않아야 한다.
    def test_visualize_context_still_allows_calculation(self) -> None:
        prompt = build_system_prompt(["visualize"])

        self.assertIn("차트에 그 값이 그려지지 않았다는 이유로 계산을", prompt)

    # '관계'라는 낱말만으로 차트를 그리면 계산 요청이 시각화로 새어 나간다.
    def test_relation_wording_alone_does_not_route_to_visualize(self) -> None:
        prompt = build_system_prompt([])

        self.assertIn("'관계'라는 낱말만 보고 차트를 그리지 않습니다", prompt)
        self.assertIn("그래프·차트·그림을 요구했을 때만", prompt)


class PublicationScopePromptTests(unittest.TestCase):
    # 조회 범위마다 규칙이 다르므로 선택한 범위의 규칙만 붙어야 한다.
    def test_each_scope_gets_its_own_rules(self) -> None:
        expected = {
            "all": ALL_PUBLICATIONS_SCOPE_PROMPT,
            "yearbook": YEARBOOK_SCOPE_PROMPT,
            "major_statistics": MAJOR_STATISTICS_SCOPE_PROMPT,
        }
        for scope, scope_prompt in expected.items():
            with self.subTest(scope=scope):
                prompt = build_system_prompt([], scope)

                self.assertIn(scope_prompt, prompt)
                for other, other_prompt in expected.items():
                    if other != scope:
                        self.assertNotIn(other_prompt, prompt)

    # 범위를 주지 않으면 두 발간물을 함께 보는 전체 범위로 답해야 한다.
    def test_default_scope_searches_both_publications(self) -> None:
        self.assertIn(ALL_PUBLICATIONS_SCOPE_PROMPT, build_system_prompt())

    # 한 발간물로 좁힌 범위에서 다른 발간물의 내용을 끌어다 쓰면 사용자가 고른 범위가 무너진다.
    def test_narrow_scope_forbids_answering_from_the_other_publication(self) -> None:
        self.assertIn("주요통계집의 수치나 이전 대화에서 본 주요통계집 내용으로 대신", YEARBOOK_SCOPE_PROMPT)
        self.assertIn("통계연보의 수치나 이전 대화에서 본 통계연보 내용으로 대신", MAJOR_STATISTICS_SCOPE_PROMPT)

    # 전체 범위에서는 한 번의 검색으로 두 발간물을 모두 보므로 발간물만 바꿔 다시 부르면 낭비다.
    def test_all_scope_explains_the_single_cross_publication_search(self) -> None:
        self.assertIn("publication_kind=all", ALL_PUBLICATIONS_SCOPE_PROMPT)
        self.assertIn("같은 검색어로 다시 호출하지 않습니다", ALL_PUBLICATIONS_SCOPE_PROMPT)


if __name__ == "__main__":
    unittest.main()
