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


if __name__ == "__main__":
    unittest.main()
