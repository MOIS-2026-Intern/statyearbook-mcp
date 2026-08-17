# -*- coding: utf-8 -*-
"""같은 해에 두 판이 나오는 주요통계집의 반기 구분이 도구까지 이어지는지 검증한다."""
import unittest
from unittest.mock import patch

from app.tools.repository.statistics_search_repository import (
    _edition_params,
    _search_sql,
)
from app.tools.service.publication_comparison_service import compare_publications_data
from app.tools.service.statistics_search_service import search_statistics_data
from utils.publication_kind import (
    normalize_publication_period,
    normalize_publication_period_filter,
    publication_period_label,
)


SUMMARY_ROW = {
    "base_item_count": 391,
    "base_record_count": 391,
    "base_duplicate_key_count": 0,
    "target_item_count": 402,
    "target_record_count": 402,
    "target_duplicate_key_count": 0,
    "only_in_base_count": 11,
    "only_in_target_count": 22,
    "in_both_count": 380,
    "changed_count": 5,
}
HALF_YEAR_EDITIONS = [(2025, "H2"), (2025, "H1")]


# DB를 대신해 고정된 발간판 목록과 조회 결과를 돌려준다.
def _patched(editions, rows=(SUMMARY_ROW,)):
    return (
        patch(
            "app.tools.service.publication_comparison_service._publication_editions",
            return_value=list(editions),
        ),
        patch(
            "app.tools.service.publication_comparison_service._execute_plan",
            return_value=list(rows),
        ),
    )


class PublicationPeriodTests(unittest.TestCase):
    # 사용자와 모델이 쓰는 한국어 표기도 저장값과 같은 정규 값으로 받아야 한다.
    def test_period_accepts_korean_and_short_forms(self) -> None:
        self.assertEqual(normalize_publication_period("상반기"), "H1")
        self.assertEqual(normalize_publication_period("h2"), "H2")
        self.assertEqual(normalize_publication_period(None), "")
        self.assertEqual(publication_period_label("H2"), "하반기")
        with self.assertRaises(ValueError):
            normalize_publication_period("3분기")

    # 반기를 주지 않은 검색은 반기로 좁히지 않아야 통계연보가 지금과 똑같이 동작한다.
    def test_missing_period_filter_stays_unset(self) -> None:
        self.assertIsNone(normalize_publication_period_filter(None))
        self.assertEqual(normalize_publication_period_filter("하반기"), "H2")

    # 반기를 주지 않으면 SQL에 반기 조건이 붙지 않아야 한다.
    def test_search_sql_only_filters_period_when_requested(self) -> None:
        without = _search_sql("yearbook", 2026, False, None)
        self.assertNotIn("p.period = %s", without)
        self.assertEqual(_edition_params("yearbook", 2026, None), ["yearbook", 2026])

        with_period = _search_sql("major_statistics", 2025, False, "H2")
        self.assertIn("p.period = %s", with_period)
        self.assertEqual(
            _edition_params("major_statistics", 2025, "H2"),
            ["major_statistics", 2025, "H2"],
        )

    # 최신 발간판 판정은 연도만으로는 갈리지 않는다. 같은 해면 하반기가 더 최신이다.
    def test_latest_edition_ranks_second_half_above_first_half(self) -> None:
        sql = _search_sql("major_statistics", None, True, None)
        self.assertIn("WHEN 'H2' THEN 2", sql)
        self.assertIn("WHEN 'H1' THEN 1", sql)
        self.assertIn("WHERE edition_rank = latest_rank", sql)

    # 반기를 전달하면 검색 결과 범위와 응답에 그 반기가 그대로 남아야 한다.
    def test_search_passes_the_period_to_the_repository(self) -> None:
        with patch(
            "app.tools.service.statistics_search_service.SEARCH_REPOSITORY"
        ) as repository, patch(
            "app.tools.service.statistics_search_service.embed_query",
            return_value="[0]",
        ), patch(
            "app.tools.service.statistics_search_service.embedding_profile"
        ), patch(
            "app.tools.service.statistics_search_service.table_search_embedding_profile"
        ):
            repository.fetch_rows.return_value = ([], [], [])
            result = search_statistics_data(
                "서해 5도",
                publication_kind="major_statistics",
                publication_period="하반기",
            )
        self.assertEqual(
            repository.fetch_rows.call_args.kwargs["publication_period"], "H2"
        )
        self.assertEqual(result["applied_publication_period"], "H2")
        self.assertIn("하반기", result["message"])

    # 같은 해의 두 반기를 맞대어 비교할 수 있어야 한다.
    def test_compare_matches_two_halves_of_the_same_year(self) -> None:
        editions_mock, execute_mock = _patched(HALF_YEAR_EDITIONS)
        with editions_mock, execute_mock as execute_plan_mock:
            result = compare_publications_data(
                operation="summary",
                publication_kind="major_statistics",
                base_publication_year=2025,
                target_publication_year=2025,
                base_publication_period="H1",
                target_publication_period="H2",
            )
        self.assertEqual(result["base_publication_period"], "H1")
        self.assertEqual(result["target_publication_period"], "H2")
        self.assertEqual(
            execute_plan_mock.call_args.args[0].params,
            ("major_statistics", 2025, "H1", "major_statistics", 2025, "H2"),
        )
        self.assertIn("2025 상반기", result["basis"])

    # 연도만 주면 그 해에 두 판이 있어 하나로 정해지지 않으므로 반기를 요구해야 한다.
    def test_compare_rejects_an_ambiguous_year(self) -> None:
        editions_mock, execute_mock = _patched(HALF_YEAR_EDITIONS)
        with editions_mock, execute_mock, self.assertRaises(ValueError) as error:
            compare_publications_data(
                operation="summary",
                publication_kind="major_statistics",
                base_publication_year=2025,
                target_publication_year=2025,
            )
        self.assertIn("more than one edition", str(error.exception))

    # 발간판을 생략하면 최신 두 판, 곧 같은 해의 하반기와 상반기를 비교해야 한다.
    def test_compare_defaults_to_the_two_most_recent_editions(self) -> None:
        editions_mock, execute_mock = _patched(HALF_YEAR_EDITIONS)
        with editions_mock, execute_mock:
            result = compare_publications_data(
                operation="summary",
                publication_kind="major_statistics",
            )
        self.assertEqual(result["base_publication_period"], "H1")
        self.assertEqual(result["target_publication_period"], "H2")
        self.assertTrue(result["publication_years_defaulted"])
        self.assertEqual(
            result["available_publication_editions"], ["2025 하반기", "2025 상반기"]
        )


if __name__ == "__main__":
    unittest.main()
