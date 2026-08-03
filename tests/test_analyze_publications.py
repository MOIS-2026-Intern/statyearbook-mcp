# -*- coding: utf-8 -*-
"""analyze_publications 도구가 집계 값을 반환하는지 검증한다."""
import unittest
from unittest.mock import patch

from app.tools.analyze_publications import analyze_publications_data


class AnalyzePublicationsTests(unittest.TestCase):
    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[{"matched_publications": 1, "count": 319}],
    )
    @patch(
        "app.tools.analyze_publications._latest_publication_year",
        return_value=2026,
    )
    # 발간연도를 생략하면 최신 발간판을 기준으로 집계 값과 산출 근거를 돌려줘야 한다.
    def test_returns_count_for_latest_publication_year(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(operation="count", subject="statistics")

        self.assertEqual(result["count"], 319)
        self.assertEqual(result["matched_publications"], 1)
        self.assertEqual(result["applied_publication_year"], 2026)
        self.assertTrue(result["publication_year_defaulted"])
        self.assertIn("statistics.stat_id", result["basis"])
        latest_publication_year_mock.assert_called_once_with()
        self.assertEqual(execute_plan_mock.call_args.args[0].params, (2026,))


if __name__ == "__main__":
    unittest.main()
