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


if __name__ == "__main__":
    unittest.main()
