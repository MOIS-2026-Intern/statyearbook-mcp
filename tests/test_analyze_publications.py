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

    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[{"matched_publications": 1, "count": 140}],
    )
    @patch(
        "app.tools.analyze_publications._latest_publication_year",
        return_value=2026,
    )
    # distinct_field를 주면 연락처 레코드 수가 아니라 값의 가짓수를 세야 한다.
    def test_counts_distinct_values_of_requested_field(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="contacts",
            distinct_field="phone",
        )

        self.assertEqual(result["count"], 140)
        self.assertEqual(result["distinct_field"], "phone")
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("COUNT(DISTINCT NULLIF(BTRIM(c.phone), ''))", sql)
        self.assertNotIn("COUNT(DISTINCT c.contact_id)", sql)

    @patch("app.tools.analyze_publications._latest_publication_year", return_value=2026)
    # 빈 값이 하나의 종류로 잡히지 않도록 FILTER 절로 걸러야 한다.
    def test_distinct_count_excludes_empty_values(
        self,
        latest_publication_year_mock,
    ) -> None:
        with patch(
            "app.tools.analyze_publications._execute_plan",
            return_value=[{"matched_publications": 1, "count": 140}],
        ) as execute_plan_mock:
            analyze_publications_data(
                operation="count",
                subject="contacts",
                distinct_field="phone",
            )

        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("FILTER (WHERE NULLIF(BTRIM(c.phone), '') IS NOT NULL)", sql)

    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[{"organization": "재난경감과", "count": 4}],
    )
    @patch(
        "app.tools.analyze_publications._latest_publication_year",
        return_value=2026,
    )
    # breakdown에서도 그룹마다 레코드 수가 아니라 값의 가짓수를 세야 한다.
    def test_counts_distinct_values_per_group(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="breakdown",
            subject="contacts",
            group_by="organization",
            distinct_field="phone",
        )

        self.assertEqual(result["results"], [{"organization": "재난경감과", "count": 4}])
        self.assertEqual(result["distinct_field"], "phone")
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("COUNT(DISTINCT NULLIF(BTRIM(c.phone), ''))", sql)
        self.assertNotIn("COUNT(DISTINCT c.contact_id)", sql)
        self.assertIn("GROUP BY", sql)
        # 같은 값이 여러 그룹에 걸치면 합계가 전체 종류 수를 넘는다는 점을 알려야 한다.
        self.assertTrue(
            any("그룹 count의 합" in item for item in result["limitations"])
        )

    # distinct_field는 count·breakdown 이외의 operation에서 거부해야 한다.
    def test_rejects_distinct_field_outside_count(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="list",
                subject="contacts",
                distinct_field="phone",
            )

        self.assertIn(
            "distinct_field can only be used with count or breakdown",
            str(error.exception),
        )

    # subject가 다루지 않는 필드는 조인이 없으므로 거부해야 한다.
    def test_rejects_distinct_field_outside_subject(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="count",
                subject="footnotes",
                distinct_field="phone",
            )

        self.assertIn("unsupported distinct_field", str(error.exception))

    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[
            {
                "statistic_title": "지역별 재난 예･경보시스템 보유",
                "officer": "주무관 위운비",
                "_total_count": 1,
            }
        ],
    )
    @patch(
        "app.tools.analyze_publications._latest_publication_year",
        return_value=2026,
    )
    # 담당자 이름을 주면 그 값을 가진 레코드만 남기고 산출 근거에도 조건을 밝혀야 한다.
    def test_filters_list_rows_by_field_value(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="list",
            subject="contacts",
            fields=["statistic_title", "officer"],
            value_filters=[{"field": "officer", "contains": "위운비"}],
            publication_year=2025,
        )

        plan = execute_plan_mock.call_args.args[0]
        self.assertIn("strpos(", plan.sql)
        # 값 조건은 페이지 자르기 전인 CTE 안에서 걸러야 total_count가 맞는다.
        self.assertLess(plan.sql.index("strpos("), plan.sql.index("_total_count"))
        self.assertEqual(plan.params, (2025, "위운비", 500, 0))
        self.assertEqual(
            result["value_filters"],
            [{"field": "officer", "contains": "위운비"}],
        )
        self.assertEqual(result["total_count"], 1)
        self.assertIn("'위운비' 포함", result["basis"])

    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[{"matched_publications": 1, "count": 2}],
    )
    @patch(
        "app.tools.analyze_publications._latest_publication_year",
        return_value=2026,
    )
    # 검색어의 공백과 직함 표기가 달라도 비교 키가 같으면 찾아야 한다.
    def test_normalizes_filter_value_before_matching(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="contacts",
            distinct_field="stat_id",
            value_filters=[{"field": "department", "contains": "재난 정보통신과"}],
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(execute_plan_mock.call_args.args[0].params, (2026, "재난정보통신과"))

    # subject가 조인하지 않는 필드는 조건으로 받을 수 없어야 한다.
    def test_rejects_filter_field_outside_subject(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="list",
                subject="footnotes",
                value_filters=[{"field": "officer", "contains": "위운비"}],
            )

        self.assertIn("unsupported value_filters field", str(error.exception))

    # 발간판 단위 요약에는 값 조건을 걸 수 없어야 한다.
    def test_rejects_filter_on_overview(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="overview",
                subject="contacts",
                value_filters=[{"field": "officer", "contains": "위운비"}],
            )

        self.assertIn("value_filters can only be used with", str(error.exception))

    # 빈 검색어는 모든 행과 일치하므로 거부해야 한다.
    def test_rejects_empty_filter_value(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="list",
                subject="contacts",
                value_filters=[{"field": "officer", "contains": "   "}],
            )

        self.assertIn("must not be empty", str(error.exception))


if __name__ == "__main__":
    unittest.main()
