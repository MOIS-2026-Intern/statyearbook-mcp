import unittest

from backend.prompts import build_system_prompt


class SystemPromptTests(unittest.TestCase):
    def test_prompt_forbids_follow_up_questions_and_choice_requests(self) -> None:
        prompt = build_system_prompt(("search_statistics",))

        self.assertIn("사용자에게 후속 질문을 하지 않습니다", prompt)
        self.assertIn("사용자의 선택·확인·허락·추가 정보 제공을 요청하지 않으며", prompt)
        self.assertIn("대안 선택지를 나열하지 않습니다", prompt)
        self.assertIn("물음표를 사용하지 않습니다", prompt)
        self.assertIn("도구의 한계를 설명한 뒤 그대로 종료", prompt)
        self.assertNotIn("한 번 질문", prompt)

    def test_prompt_routes_publication_aggregates_to_analysis_tool(self) -> None:
        prompt = build_system_prompt(("analyze_publications",))

        self.assertIn("analyze_publications를 사용합니다", prompt)
        self.assertIn("search_statistics의 후보 개수", prompt)
        self.assertIn("analyze_publications 결과 처리", prompt)
        self.assertIn("count는 원칙적으로 두 문장 이내", prompt)
        self.assertIn("산출 기준만 밝힙니다", prompt)
        self.assertIn("limitations를 별도의", prompt)
        self.assertIn("내부 구현 표현", prompt)
        self.assertIn("공식 제출기관 수로 단정하지 않습니다", prompt)


if __name__ == "__main__":
    unittest.main()
