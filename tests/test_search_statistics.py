import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tools.search_statistics import (
    _search_sql,
    _table_lexical_sql,
    _table_vector_sql,
    search_statistics_data,
)


def result_row(publication_year: int = 2025) -> dict:
    return {
        "stat_id": 8,
        "publication_year": publication_year,
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


def table_result_row(
    stat_id: int = 22,
    ref_id: str = "2-1-1-5",
    chunk_kind: str = "headers",
) -> dict:
    row = result_row()
    row.update({
        "stat_id": stat_id,
        "ref_id": ref_id,
        "level3_title": "민원행정",
        "level4_title": "안심상속 원스톱서비스",
        "title_ko": "안심상속 원스톱서비스",
        "title_en": "One-stop Inheritance Service",
        "table_seq": 1,
        "chunk_kind": chunk_kind,
        "search_labels": ["연도 Year", "사망신고 건수 No. of Death Reports"],
        "search_text": "안심상속 원스톱서비스 컬럼: 연도 | 사망신고 건수",
    })
    return row


class SearchStatisticsTests(unittest.TestCase):
    def test_search_sql_selects_complete_title_hierarchy(self) -> None:
        sql = _search_sql(publication_year=2025)

        self.assertIn("chapter_no, section_no, level3_no, level4_no", sql)
        self.assertIn("level3_title, level4_title", sql)

    def test_search_sql_filters_one_year_without_latest_edition_cte(self) -> None:
        sql = _search_sql(publication_year=2025)

        self.assertIn("year = %s", sql)
        self.assertNotIn("latest_editions", sql)

    def test_search_sql_limits_to_latest_edition_of_each_statistic(self) -> None:
        sql = _search_sql(publication_year=None, latest_editions=True)

        self.assertIn("WITH latest_editions AS", sql)
        self.assertIn("DISTINCT ON (coalesce(nullif(ref_id, ''), title_ko))", sql)
        self.assertIn("stat_id IN (SELECT stat_id FROM latest_editions)", sql)
        self.assertNotIn("year = %s", sql)

    def test_table_search_sql_limits_to_latest_edition_of_each_statistic(self) -> None:
        lexical_sql = _table_lexical_sql(publication_year=None, latest_editions=True)
        vector_sql = _table_vector_sql(publication_year=None, latest_editions=True)

        for sql in (lexical_sql, vector_sql):
            self.assertIn("WITH latest_editions AS", sql)
            self.assertIn("s.stat_id IN (SELECT stat_id FROM latest_editions)", sql)
            self.assertNotIn("s.year = %s", sql)

    def test_table_search_sql_keeps_year_filter_when_edition_is_requested(self) -> None:
        lexical_sql = _table_lexical_sql(publication_year=2025, latest_editions=False)
        vector_sql = _table_vector_sql(publication_year=2025, latest_editions=False)

        for sql in (lexical_sql, vector_sql):
            self.assertIn("s.year = %s", sql)
            self.assertNotIn("latest_editions", sql)

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
    def test_relaxes_publication_year_when_filtered_search_is_empty(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.side_effect = [
            ([], [], []),
            ([result_row()], [], []),
        ]

        response = search_statistics_data("행정기관 위원회", publication_year=2024)

        self.assertEqual(response["requested_publication_year"], 2024)
        self.assertIsNone(response["applied_publication_year"])
        self.assertTrue(response["publication_year_filter_relaxed"])
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["results"][0]["publication_year"], 2025)
        self.assertEqual(response["results"][0]["level3_title"], "행정기관 위원회")
        self.assertEqual(response["results"][0]["level4_title"], "행정기관 위원회")
        self.assertTrue(response["latest_edition_per_statistic"])
        self.assertEqual(
            fetch_rows_mock.call_args_list[0].args,
            (
                "행정기관 위원회",
                "[0.1,0.2]",
                "profile-key",
                "table-profile-key",
                2024,
                False,
                5,
            ),
        )
        self.assertEqual(
            fetch_rows_mock.call_args_list[1].args,
            (
                "행정기관 위원회",
                "[0.1,0.2]",
                "profile-key",
                "table-profile-key",
                None,
                True,
                5,
            ),
        )
        embed_query_mock.assert_called_once_with("행정기관 위원회")

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
    def test_keeps_publication_year_when_filtered_search_succeeds(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        _embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.return_value = ([result_row()], [], [])

        response = search_statistics_data("행정기관 위원회", publication_year=2025)

        self.assertEqual(response["applied_publication_year"], 2025)
        self.assertFalse(response["publication_year_filter_relaxed"])
        self.assertFalse(response["latest_edition_per_statistic"])
        self.assertIsNone(response["message"])
        fetch_rows_mock.assert_called_once_with(
            "행정기관 위원회",
            "[0.1,0.2]",
            "profile-key",
            "table-profile-key",
            2025,
            False,
            5,
        )

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
    def test_exact_column_match_outranks_title_candidate(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.return_value = (
            [result_row()],
            [table_result_row()],
            [table_result_row()],
        )

        response = search_statistics_data("2024년 사망신고 건수 알려줘", limit=5)

        first = response["results"][0]
        self.assertEqual(first["ref_id"], "2-1-1-5")
        self.assertEqual(first["table_seq"], 1)
        self.assertEqual(first["matched_source"], "column")
        self.assertIn("사망신고 건수", first["matched_text"])
        self.assertIsNone(response["requested_publication_year"])
        self.assertIsNone(response["applied_publication_year"])
        self.assertTrue(response["latest_edition_per_statistic"])
        self.assertIn("통계마다 가장 최근 발간판", response["message"])
        self.assertIsNone(fetch_rows_mock.call_args.args[4])
        self.assertTrue(fetch_rows_mock.call_args.args[5])
        embed_query_mock.assert_called_once_with("사망신고 건수")

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
    def test_deduplicates_same_table_across_publication_editions(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        _embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        newest = table_result_row(stat_id=30)
        newest["publication_year"] = 2026
        older = table_result_row(stat_id=20)
        older["publication_year"] = 2025
        fetch_rows_mock.return_value = ([], [newest, older], [])

        response = search_statistics_data("사망신고 건수", limit=5)

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["results"][0]["publication_year"], 2026)

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
    def test_returns_older_edition_when_statistic_is_missing_from_newest(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        _embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.return_value = ([result_row(publication_year=2025)], [], [])

        response = search_statistics_data("행정기관 위원회")

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["results"][0]["publication_year"], 2025)
        self.assertIsNone(response["applied_publication_year"])
        self.assertTrue(response["latest_edition_per_statistic"])
        self.assertFalse(response["publication_year_filter_relaxed"])
        fetch_rows_mock.assert_called_once()

    @patch("app.tools.search_statistics._fetch_rows", return_value=([], [], []))
    @patch("app.tools.search_statistics.embed_query", return_value="[0.1,0.2]")
    @patch(
        "app.tools.search_statistics.table_search_embedding_profile",
        return_value=SimpleNamespace(profile_key="table-profile-key"),
    )
    @patch(
        "app.tools.search_statistics.embedding_profile",
        return_value=SimpleNamespace(profile_key="profile-key"),
    )
    def test_default_search_does_not_retry_other_editions(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        _embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        response = search_statistics_data("없는 통계")

        self.assertEqual(response["count"], 0)
        self.assertIsNone(response["applied_publication_year"])
        self.assertTrue(response["latest_edition_per_statistic"])
        fetch_rows_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
