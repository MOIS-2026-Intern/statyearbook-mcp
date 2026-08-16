# -*- coding: utf-8 -*-
"""search_statistics 도구가 검색된 통계 값을 그대로 반환하는지 검증한다."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tools.repository.statistics_search_repository import (
    LATEST_EDITIONS_CTE,
    LATEST_EDITIONS_KEY_SQL,
)
from app.tools.service.statistics_search_service import (
    RRF_K,
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
    @patch("app.tools.service.statistics_search_service.SEARCH_REPOSITORY.fetch_rows")
    @patch("app.tools.service.statistics_search_service.embed_query", return_value="[0.1,0.2]")
    @patch(
        "app.tools.service.statistics_search_service.table_search_embedding_profile",
        return_value=SimpleNamespace(profile_key="table-profile-key"),
    )
    @patch(
        "app.tools.service.statistics_search_service.embedding_profile",
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

        response = search_statistics_data(
            "행정기관 위원회",
            publication_year=2025,
            publication_kind="yearbook",
        )

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

    @patch("app.tools.service.statistics_search_service.SEARCH_REPOSITORY.fetch_rows")
    @patch("app.tools.service.statistics_search_service.embed_query", return_value="[0.1,0.2]")
    @patch(
        "app.tools.service.statistics_search_service.table_search_embedding_profile",
        return_value=SimpleNamespace(profile_key="table-profile-key"),
    )
    @patch(
        "app.tools.service.statistics_search_service.embedding_profile",
        return_value=SimpleNamespace(profile_key="profile-key"),
    )
    # 조직도처럼 표 본문이 없는 통계표를 표시해야 모델이 수치를 찾아 헛돌지 않는다.
    def test_reports_whether_the_statistic_has_a_table_body(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        _embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        chart_only = {
            **RESULT_ROW,
            "stat_id": 9,
            "ref_id": "1-1-6",
            "title_ko": "정부 조직도",
            "has_tables": False,
        }
        fetch_rows_mock.return_value = ([{**RESULT_ROW, "has_tables": True}, chart_only], [], [])

        results = search_statistics_data(
            "행정기관 위원회",
            limit=2,
            publication_kind="yearbook",
        )["results"]

        self.assertEqual(
            {result["stat_id"]: result["has_tables"] for result in results},
            {8: True, 9: False},
        )

    @patch("app.tools.service.statistics_search_service.SEARCH_REPOSITORY.fetch_rows")
    @patch("app.tools.service.statistics_search_service.embed_query", return_value="[0.1,0.2]")
    @patch(
        "app.tools.service.statistics_search_service.table_search_embedding_profile",
        return_value=SimpleNamespace(profile_key="table-profile-key"),
    )
    @patch(
        "app.tools.service.statistics_search_service.embedding_profile",
        return_value=SimpleNamespace(profile_key="profile-key"),
    )
    # 값이 없는 조회 경로 때문에 멀쩡한 후보가 표 없는 것으로 표시되면 안 된다.
    def test_missing_table_flag_defaults_to_having_a_table(
        self,
        _embedding_profile_mock,
        _table_profile_mock,
        _embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.return_value = ([RESULT_ROW], [], [])

        response = search_statistics_data("행정기관 위원회", publication_kind="yearbook")

        self.assertTrue(response["results"][0]["has_tables"])

    # 목차 번호는 발간판마다 다시 매겨지고 앞 판의 번호를 다른 통계가 물려받으므로,
    # 번호로 판을 이으면 번호를 뺏긴 구판 통계가 검색에서 통째로 빠진다.
    def test_latest_edition_key_uses_title_not_ref_id(self) -> None:
        self.assertIn("title_ko", LATEST_EDITIONS_KEY_SQL)
        self.assertNotIn("ref_id", LATEST_EDITIONS_KEY_SQL)
        self.assertIn(LATEST_EDITIONS_KEY_SQL, LATEST_EDITIONS_CTE)

    # 최신 발간판에 같은 제목이 여러 건 실려 있으면 한 건만 남기지 말고 모두 남겨야 한다.
    def test_latest_edition_keeps_every_row_of_the_newest_publication(self) -> None:
        self.assertNotIn("DISTINCT ON", LATEST_EDITIONS_CTE)
        self.assertIn("WHERE edition_rank = latest_rank", LATEST_EDITIONS_CTE)

    # RRF의 관례값 60은 후보가 수천 건일 때를 전제한다. 여기서는 경로마다 후보가
    # max(20, limit*5)로 20~100건뿐이라 K가 후보 수보다 크면 1위와 꼴찌의 점수 차가 거의 없어져
    # 순위가 지워지고, 제목이 정확히 맞는 표가 본문에 검색어가 흩어진 표에 밀린다.
    def test_rrf_k_is_scaled_to_the_candidate_pool(self) -> None:
        smallest_candidate_pool = 20
        self.assertLessEqual(RRF_K, smallest_candidate_pool)


# 발간물마다 다른 후보를 돌려주는 조회 경로를 대신한다.
def _rows_by_kind(rows_by_kind: dict[str, list[dict]]):
    def fetch_rows(*_args, publication_kind: str = "yearbook", **_kwargs):
        return (list(rows_by_kind.get(publication_kind, [])), [], [])

    return fetch_rows


def _search(rows_by_kind: dict[str, list[dict]], **kwargs) -> dict:
    with patch(
        "app.tools.service.statistics_search_service.SEARCH_REPOSITORY.fetch_rows",
        side_effect=_rows_by_kind(rows_by_kind),
    ), patch(
        "app.tools.service.statistics_search_service.embed_query",
        return_value="[0.1,0.2]",
    ), patch(
        "app.tools.service.statistics_search_service.embedding_profile",
        return_value=SimpleNamespace(profile_key="profile-key"),
    ), patch(
        "app.tools.service.statistics_search_service.table_search_embedding_profile",
        return_value=SimpleNamespace(profile_key="table-profile-key"),
    ):
        return search_statistics_data("생활인구", **kwargs)


YEARBOOK_ROW = {**RESULT_ROW, "publication_kind": "yearbook", "publication_period": ""}
MAJOR_ROW = {
    **RESULT_ROW,
    "stat_id": 91,
    "ref_id": "4-38-1",
    "title_ko": "생활인구",
    "publication_kind": "major_statistics",
    "publication_period": "H2",
    "publication_year": 2025,
}


class PublicationScopeSearchTests(unittest.TestCase):
    # 한 발간물에만 실린 통계도 찾아야 하므로 기본 범위는 두 발간물을 모두 검색한다.
    def test_default_scope_searches_both_publications(self) -> None:
        response = _search({"yearbook": [YEARBOOK_ROW], "major_statistics": [MAJOR_ROW]})

        self.assertEqual(
            response["searched_publication_kinds"], ["yearbook", "major_statistics"]
        )
        self.assertEqual(response["applied_publication_kind"], "all")
        self.assertEqual(
            [result["publication_kind"] for result in response["results"]],
            ["yearbook", "major_statistics"],
        )

    # 통계연보에 없는 주제는 주요통계집 후보만으로도 답할 수 있어야 한다.
    def test_falls_back_to_the_other_publication_when_one_has_no_candidate(self) -> None:
        response = _search({"yearbook": [], "major_statistics": [MAJOR_ROW]})

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["results"][0]["stat_id"], 91)
        self.assertEqual(response["results"][0]["publication_label"], "2025년 하반기 주요통계집")

    # 후보가 많은 발간물이 상위를 모두 채우면 다른 발간물에만 있는 표가 목록에서 빠진다.
    def test_each_publication_keeps_its_top_candidate(self) -> None:
        crowded = [{**YEARBOOK_ROW, "stat_id": index, "ref_id": f"1-1-{index}"} for index in range(5)]

        response = _search(
            {"yearbook": crowded, "major_statistics": [MAJOR_ROW]},
            limit=2,
        )

        self.assertEqual(
            [result["publication_kind"] for result in response["results"]],
            ["yearbook", "major_statistics"],
        )

    # 한 발간물로 좁힌 범위에서는 다른 발간물을 조회하지 않아야 한다.
    def test_narrow_scope_searches_only_the_selected_publication(self) -> None:
        response = _search(
            {"yearbook": [YEARBOOK_ROW], "major_statistics": [MAJOR_ROW]},
            publication_kind="major_statistics",
        )

        self.assertEqual(response["searched_publication_kinds"], ["major_statistics"])
        self.assertEqual(
            [result["stat_id"] for result in response["results"]], [MAJOR_ROW["stat_id"]]
        )

    # 반기는 주요통계집에만 있다. 통계연보 조회에까지 걸면 통계연보 후보가 통째로 사라진다.
    def test_period_filter_applies_only_to_major_statistics(self) -> None:
        with patch(
            "app.tools.service.statistics_search_service.SEARCH_REPOSITORY"
        ) as repository, patch(
            "app.tools.service.statistics_search_service.embed_query", return_value="[0]"
        ), patch(
            "app.tools.service.statistics_search_service.embedding_profile"
        ), patch(
            "app.tools.service.statistics_search_service.table_search_embedding_profile"
        ):
            repository.fetch_rows.return_value = ([], [], [])
            search_statistics_data("생활인구", publication_period="H2")

        periods = {
            call.kwargs["publication_kind"]: call.kwargs["publication_period"]
            for call in repository.fetch_rows.call_args_list
        }
        self.assertEqual(periods, {"yearbook": None, "major_statistics": "H2"})

    # 통계연보만 보는 범위에서는 반기를 적용할 발간물이 없다.
    def test_period_is_not_applied_without_major_statistics(self) -> None:
        response = _search(
            {"yearbook": [YEARBOOK_ROW]},
            publication_kind="yearbook",
            publication_period="하반기",
        )

        self.assertEqual(response["requested_publication_period"], "H2")
        self.assertIsNone(response["applied_publication_period"])


if __name__ == "__main__":
    unittest.main()
