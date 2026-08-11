# -*- coding: utf-8 -*-
"""compare_publications 도구가 두 발간판의 수록 항목을 맞대어 비교하는지 검증한다."""
import unittest
from unittest.mock import patch

from app.tools.service.publication_comparison_service import compare_publications_data


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
CHANGED_ORGANIZATION_ROWS = [
    {
        "match_key": "지방자치단체의회의원정수",
        "base_stat_id": 118,
        "target_stat_id": 402,
        "base_statistic_title": "지방자치단체 의회의원 정수",
        "target_statistic_title": "지방자치단체 의회의원 정수",
        "base_organization": "자치분권제도과",
        "target_organization": "자치분권지원과",
        "base_record_count": 1,
        "target_record_count": 1,
        "changed_fields": ["organization"],
        "_total_count": 1,
    }
]
CHANGED_OFFICER_ROWS = [
    {
        "match_key": "정부원격근무서비스이용자수",
        "base_stat_id": 201,
        "target_stat_id": 511,
        "base_statistic_title": "정부원격근무서비스 이용자 수",
        "target_statistic_title": "정부원격근무서비스 이용자 수",
        "base_officer": "주무관 김일표",
        "target_officer": "사무관 김일표",
        "base_record_count": 1,
        "target_record_count": 1,
        "changed_fields": ["officer"],
        "_total_count": 1,
    }
]


# DB를 대신해 고정된 발간연도 목록과 조회 결과를 돌려준다.
def _patched(rows):
    return (
        patch(
            "app.tools.service.publication_comparison_service._publication_years",
            return_value=[2026, 2025],
        ),
        patch("app.tools.service.publication_comparison_service._execute_plan", return_value=rows),
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

    # 담당 부서 변경은 두 발간판의 부서 목록을 따로 받지 않고 한 번의 비교로 답해야 한다.
    def test_changed_compares_department_of_each_statistic(self) -> None:
        years_mock, execute_mock = _patched(CHANGED_ORGANIZATION_ROWS)
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="changed",
                base_publication_year=2025,
                target_publication_year=2026,
                fields=["stat_id", "statistic_title", "organization"],
            )

        self.assertEqual(result["compared_fields"], ["statistic_title", "organization"])
        self.assertIn("contacts", result["source_tables"])
        self.assertEqual(result["results"][0]["base_organization"], "자치분권제도과")
        self.assertEqual(result["results"][0]["target_organization"], "자치분권지원과")
        sql = execute_plan_mock.call_args.args[0].sql
        # 연락처는 통계당 한 행으로 접어 붙여야 record_count가 흔들리지 않는다.
        self.assertIn("LEFT JOIN LATERAL", sql)
        self.assertIn("string_agg(DISTINCT", sql)
        # 표기 차이는 정규화한 비교 컬럼으로 걸러 담당 변경만 남긴다.
        self.assertIn(
            "b.organization_compare_key IS DISTINCT FROM t.organization_compare_key",
            sql,
        )
        # 이름으로 대응시킨 비교에서 statistic_title 변경은 표기 차이임을 알려야 한다.
        self.assertTrue(
            any("statistic_title" in note for note in result["limitations"]),
            result["limitations"],
        )
        self.assertTrue(
            any("조직 개편" in note for note in result["limitations"]),
            result["limitations"],
        )

    # 담당자 변경은 contacts.officer 값을 그대로 비교하고 제목은 반환만 해야 한다.
    def test_changed_compares_officer_field_only(self) -> None:
        years_mock, execute_mock = _patched(CHANGED_OFFICER_ROWS)
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="changed",
                base_publication_year=2025,
                target_publication_year=2026,
                fields=["stat_id", "statistic_title", "officer"],
                compare_fields=["officer"],
            )

        self.assertEqual(result["compared_fields"], ["officer"])
        self.assertIn("contacts", result["source_tables"])
        self.assertEqual(result["results"][0]["base_officer"], "주무관 김일표")
        self.assertEqual(result["results"][0]["target_officer"], "사무관 김일표")
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("string_agg(DISTINCT", sql)
        self.assertIn("c.officer", sql)
        self.assertIn("b.officer IS DISTINCT FROM t.officer", sql)
        self.assertNotIn("b.statistic_title IS DISTINCT FROM t.statistic_title", sql)
        self.assertTrue(
            any("직급" in note for note in result["limitations"]),
            result["limitations"],
        )

    # 비교 필드가 반환 필드에 없어도 필요한 contacts 조인과 변경 판정을 준비해야 한다.
    def test_compare_fields_can_be_separate_from_returned_fields(self) -> None:
        years_mock, execute_mock = _patched([])
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="changed",
                base_publication_year=2025,
                target_publication_year=2026,
                fields=["stat_id", "statistic_title"],
                compare_fields=["officer"],
            )

        self.assertEqual(result["selected_fields"], ["stat_id", "statistic_title"])
        self.assertEqual(result["compared_fields"], ["officer"])
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("LEFT JOIN LATERAL", sql)
        self.assertIn("b.officer IS DISTINCT FROM t.officer", sql)
        self.assertNotIn("b.officer AS base_officer", sql)

    # 요약의 changed_count도 반환 기본 필드가 아니라 명시한 담당자 필드만 비교해야 한다.
    def test_summary_can_count_officer_changes_only(self) -> None:
        years_mock, execute_mock = _patched([SUMMARY_ROW])
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="summary",
                base_publication_year=2025,
                target_publication_year=2026,
                compare_fields=["officer"],
            )

        self.assertEqual(result["compared_fields"], ["officer"])
        self.assertIn("contacts", result["source_tables"])
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("b.officer IS DISTINCT FROM t.officer", sql)
        self.assertNotIn("b.ref_id IS DISTINCT FROM t.ref_id", sql)

    # 연락처 필드를 고르지 않은 비교는 연락처 조인 비용을 내지 않아야 한다.
    def test_omits_contact_join_when_no_contact_field_is_selected(self) -> None:
        years_mock, execute_mock = _patched([])
        with years_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="changed",
                base_publication_year=2025,
                target_publication_year=2026,
                fields=["statistic_title", "unit"],
            )

        sql = execute_plan_mock.call_args.args[0].sql
        self.assertNotIn("contacts", sql)
        self.assertNotIn("contacts", result["source_tables"])

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
            with self.assertRaises(ValueError) as error:
                compare_publications_data(
                    operation="only_in_base",
                    subject="chapters",
                    fields=["organization"],
                )
            with self.assertRaises(ValueError) as compare_error:
                compare_publications_data(
                    operation="summary",
                    compare_fields=["stat_id"],
                )

        self.assertIn("chapter_no", str(error.exception))
        self.assertIn("comparable", str(compare_error.exception))


if __name__ == "__main__":
    unittest.main()
