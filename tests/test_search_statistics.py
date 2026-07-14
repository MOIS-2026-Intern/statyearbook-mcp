import asyncio
import unittest
from unittest.mock import patch

from app.mcp_app import create_app
from app.tools.search_statistics import search_statistics_data


def result_row(publication_year: int = 2025) -> dict:
    return {
        "stat_id": 8,
        "publication_year": publication_year,
        "ref_id": "1-1-5",
        "chapter": "정부조직",
        "section": "정부조직",
        "title_ko": "행정기관 위원회",
        "title_en": "Administration Committees",
        "unit": "개",
        "base_date": "2024.12.31.",
        "page_start": 19,
        "distance": 0.1,
    }


class SearchStatisticsTests(unittest.TestCase):
    def test_mcp_schema_exposes_publication_year_with_external_description(self) -> None:
        tools = asyncio.run(create_app().list_tools())
        tool = next(item for item in tools if item.name == "search_statistics")
        properties = tool.inputSchema["properties"]

        self.assertIn("publication_year", properties)
        self.assertNotIn("year", properties)
        self.assertIn("발간연도", properties["publication_year"]["description"])

    @patch("app.tools.search_statistics._fetch_rows")
    @patch("app.tools.search_statistics.embed_query", return_value="[0.1,0.2]")
    def test_relaxes_publication_year_when_filtered_search_is_empty(
        self,
        embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.side_effect = [[], [result_row()]]

        response = search_statistics_data("행정기관 위원회", publication_year=2024)

        self.assertEqual(response["requested_publication_year"], 2024)
        self.assertIsNone(response["applied_publication_year"])
        self.assertTrue(response["publication_year_filter_relaxed"])
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["results"][0]["publication_year"], 2025)
        self.assertEqual(
            fetch_rows_mock.call_args_list[0].args,
            ("[0.1,0.2]", 2024, 5),
        )
        self.assertEqual(
            fetch_rows_mock.call_args_list[1].args,
            ("[0.1,0.2]", None, 5),
        )
        embed_query_mock.assert_called_once_with("행정기관 위원회")

    @patch("app.tools.search_statistics._fetch_rows")
    @patch("app.tools.search_statistics.embed_query", return_value="[0.1,0.2]")
    def test_keeps_publication_year_when_filtered_search_succeeds(
        self,
        _embed_query_mock,
        fetch_rows_mock,
    ) -> None:
        fetch_rows_mock.return_value = [result_row()]

        response = search_statistics_data("행정기관 위원회", publication_year=2025)

        self.assertEqual(response["applied_publication_year"], 2025)
        self.assertFalse(response["publication_year_filter_relaxed"])
        self.assertIsNone(response["message"])
        fetch_rows_mock.assert_called_once_with("[0.1,0.2]", 2025, 5)


if __name__ == "__main__":
    unittest.main()
