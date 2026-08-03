# -*- coding: utf-8 -*-
"""compare_publications 도구가 두 발간판의 수록 항목을 맞대어 비교하는지 검증한다."""
import unittest
from unittest.mock import patch

from app.tools.compare_publications import compare_publications_data


SUMMARY_ROW = {
    "base_item_count": 319,
    "base_record_count": 319,
    "base_duplicate_key_count": 0,
    "target_item_count": 306,
    "target_record_count": 318,
    "target_duplicate_key_count": 12,
    "only_in_base_count": 20,
    "only_in_target_count": 7,
    "in_both_count": 299,
    "changed_count": 32,
}
ONLY_IN_BASE_ROWS = [
    {
        "match_key": "모바일공무원증",
        "stat_id": 71,
        "ref_id": "3-1-7-1",
        "chapter": "디지털정부",
        "statistic_title": "모바일 공무원증",
        "unit": "건",
        "page_start": 72,
        "record_count": 1,
        "_total_count": 20,
    }
]


# DB를 대신해 고정된 발간연도 목록과 조회 결과를 돌려준다.
def _patched(rows):
    return (
        patch(
            "app.tools.compare_publications._publication_years",
            return_value=[2026, 2025],
        ),
        patch("app.tools.compare_publications._execute_plan", return_value=rows),
    )


class ComparePublicationsTests(unittest.TestCase):
    # 두 발간판을 지정하면 한쪽에만 있는 수와 공통 수를 산출 근거와 함께 돌려줘야 한다.
    def test_summary_reports_counts_for_both_publications(self) -> None:
        years_mock, execute_mock = _patched([SUMMARY_ROW])
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="summary",
                base_publication_year=2025,
                target_publication_year=2026,
            )

        self.assertEqual(result["only_in_base_count"], 20)
        self.assertEqual(result["only_in_target_count"], 7)
        self.assertEqual(result["in_both_count"], 299)
        self.assertEqual(result["base"]["item_count"], 319)
        self.assertEqual(result["target"]["duplicate_key_count"], 12)
        self.assertFalse(result["publication_years_defaulted"])
        self.assertEqual(execute_plan_mock.call_args.args[0].params, (2025, 2026))

    # 발간연도를 생략하면 가장 최근 두 발간판을 오래된 판에서 최신 판 방향으로 비교해야 한다.
    def test_defaults_to_two_most_recent_publications(self) -> None:
        years_mock, execute_mock = _patched([SUMMARY_ROW])
        with years_mock, execute_mock:
            result = compare_publications_data(operation="summary")

        self.assertEqual(result["base_publication_year"], 2025)
        self.assertEqual(result["target_publication_year"], 2026)
        self.assertTrue(result["publication_years_defaulted"])
        self.assertEqual(result["available_publication_years"], [2026, 2025])

    # base 발간판에만 있는 항목은 표 조회로 이어갈 stat_id와 함께 목록으로 나와야 한다.
    def test_only_in_base_returns_items_with_paging(self) -> None:
        years_mock, execute_mock = _patched(ONLY_IN_BASE_ROWS)
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="only_in_base",
                base_publication_year=2025,
                target_publication_year=2026,
                limit=1,
            )

        self.assertEqual(result["total_count"], 20)
        self.assertEqual(result["results"][0]["stat_id"], 71)
        self.assertNotIn("_total_count", result["results"][0])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_offset"], 1)
        self.assertEqual(execute_plan_mock.call_args.args[0].params, (2025, 2026, 1, 0))

    # 이름 기준 비교는 발간판마다 다시 매겨지는 목차 번호를 변경 판정 대상으로 삼아야 한다.
    def test_changed_compares_selected_fields_only(self) -> None:
        years_mock, execute_mock = _patched([])
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="changed",
                base_publication_year=2025,
                target_publication_year=2026,
                fields=["stat_id", "ref_id", "unit"],
            )

        self.assertEqual(result["compared_fields"], ["ref_id", "unit"])
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("b.ref_id IS DISTINCT FROM t.ref_id", sql)
        self.assertNotIn("b.stat_id IS DISTINCT FROM t.stat_id", sql)

    # 적재되지 않은 발간연도는 조용히 빈 결과를 주는 대신 오류로 알려야 한다.
    def test_rejects_publication_year_that_is_not_loaded(self) -> None:
        years_mock, execute_mock = _patched([])
        with years_mock, execute_mock:
            with self.assertRaises(ValueError) as error:
                compare_publications_data(
                    operation="summary",
                    base_publication_year=2024,
                    target_publication_year=2026,
                )

        self.assertIn("2024", str(error.exception))

    # subject가 지원하지 않는 대응 기준과 필드는 거부해야 한다.
    def test_rejects_unsupported_match_by_and_fields(self) -> None:
        years_mock, execute_mock = _patched([])
        with years_mock, execute_mock:
            with self.assertRaises(ValueError):
                compare_publications_data(
                    operation="summary",
                    subject="organizations",
                    match_by="number",
                )
            with self.assertRaises(ValueError):
                compare_publications_data(
                    operation="only_in_base",
                    subject="statistics",
                    fields=["organization"],
                )


if __name__ == "__main__":
    unittest.main()
