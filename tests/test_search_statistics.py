# -*- coding: utf-8 -*-
"""search_statistics 도구가 검색된 통계 값을 그대로 반환하는지 검증한다."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tools.search_statistics import (
    LATEST_EDITIONS_CTE,
    LATEST_EDITIONS_KEY_SQL,
    search_statistics_data,
)


RESULT_ROW = {
    "stat_id": 8,
    "publication_year": 2025,
    "ref_id": "1-1-5",
    "chapter_no": 1,
    "section_no": 1,
    "level3_no": 5,
    "level4_no": None,
    "chapter": "정부조직",
    "section": "정부조직",
    "level3_title": "행정기관 위원회",
    "level4_title": "행정기관 위원회",
    "title_ko": "행정기관 위원회",
    "title_en": "Administration Committees",
    "unit": "개",
    "base_date": "2024.12.31.",
    "page_start": 19,
    "distance": 0.1,
}


class SearchStatisticsTests(unittest.TestCase):
    @patch("app.tools.search_statistics._fetch_rows")
    @patch("app.tools.search_statistics.embed_query", return_value="[0.1,0.2]")
    @patch(
        "app.tools.search_statistics.table_search_embedding_profile",
        return_value=SimpleNamespace(profile_key="table-profile-key"),
    )
    @patch(
        "app.tools.search_statistics.embedding_profile",
        return_value=SimpleNamespace(profile_key="profile-key"),
    )
    # 조회된 행의 식별자, 제목 계층과 발간연도가 응답에 그대로 담겨야 한다.
    def test_returns_matched_statistic_rows_with_metadata(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.return_value = ([RESULT_ROW], [], [])

        response = search_statistics_data("행정기관 위원회", publication_year=2025)

        self.assertEqual(response["count"], 1)
        first = response["results"][0]
        self.assertEqual(first["stat_id"], 8)
        self.assertEqual(first["ref_id"], "1-1-5")
        self.assertEqual(first["title_ko"], "행정기관 위원회")
        self.assertEqual(first["level3_title"], "행정기관 위원회")
        self.assertEqual(first["level4_title"], "행정기관 위원회")
        self.assertEqual(first["publication_year"], 2025)
        self.assertEqual(first["unit"], "개")
        self.assertEqual(response["applied_publication_year"], 2025)
        embed_query_mock.assert_called_once_with("행정기관 위원회")

    # 목차 번호는 발간판마다 다시 매겨지고 앞 판의 번호를 다른 통계가 물려받으므로,
    # 번호로 판을 이으면 번호를 뺏긴 구판 통계가 검색에서 통째로 빠진다.
    def test_latest_edition_key_uses_title_not_ref_id(self) -> None:
        self.assertIn("title_ko", LATEST_EDITIONS_KEY_SQL)
        self.assertNotIn("ref_id", LATEST_EDITIONS_KEY_SQL)
        self.assertIn(LATEST_EDITIONS_KEY_SQL, LATEST_EDITIONS_CTE)

    # 최신 발간판에 같은 제목이 여러 건 실려 있으면 한 건만 남기지 말고 모두 남겨야 한다.
    def test_latest_edition_keeps_every_row_of_the_newest_publication(self) -> None:
        self.assertNotIn("DISTINCT ON", LATEST_EDITIONS_CTE)
        self.assertIn("WHERE year = latest_year", LATEST_EDITIONS_CTE)


if __name__ == "__main__":
    unittest.main()
