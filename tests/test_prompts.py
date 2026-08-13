# -*- coding: utf-8 -*-
"""도구별 결과 표현 규칙이 모델 프롬프트에 포함되는지 검증한다."""
import unittest

from backend.prompts import COMPARE_PUBLICATIONS_RESULT_PROMPT, build_system_prompt


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


if __name__ == "__main__":
    unittest.main()
