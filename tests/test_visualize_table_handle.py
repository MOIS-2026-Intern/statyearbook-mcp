# -*- coding: utf-8 -*-
"""visualize가 캐시 핸들을 못 쓰게 됐을 때 stat_id로 표를 다시 읽는지 검증한다."""
import unittest

from app.table_cache import cache_table, clear_table_cache
from app.tools.service.visualization.visualization_service import VisualizationService


COLUMNS = ["연도 Year", "인구 Population"]
TABLE = {
    "stat_id": 91,
    "ref_id": "4-1-1",
    "publication_year": 2025,
    "chapter_no": 4,
    "section_no": 1,
    "level3_no": 1,
    "level4_no": None,
    "chapter": "지방행정",
    "section": "지역",
    "level3_title": "연도별 인구",
    "level4_title": "연도별 인구",
    "title_ko": "연도별 인구",
    "title_en": "Population by Year",
    "unit": "명",
    "base_date": "2024.12.31.",
    "table_seq": 1,
    "caption": "2024. 12. 31. 기준",
    "body": {
        "columns": COLUMNS,
        "records": [
            dict(zip(COLUMNS, ["2023", "1,200"])),
            dict(zip(COLUMNS, ["2024", "1,150"])),
            dict(zip(COLUMNS, ["2025", "1,100"])),
        ],
    },
}

VISUALIZE_ARGS = dict(
    table_seq=1, query="연도별 인구 추이", title=None, chart_type="auto",
    x=None, y=None, group=None, top_n=None, total_mode="auto", year=None,
    city=None, column_family=None, filters=None, metrics=None,
    orientation="vertical", sort_order="auto",
)


# 표를 DB 대신 고정값으로 돌려주는 저장소 대역이다.
class StubRepository:
    def __init__(self) -> None:
        self.calls = 0

    def select_table_rows(self, stat_id: int) -> list[dict]:
        self.calls += 1
        return [{**TABLE, "body": TABLE["body"]}] if stat_id == TABLE["stat_id"] else []


class TableHandleFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_table_cache()
        self.repository = StubRepository()
        self.service = VisualizationService(self.repository)

    # 살아 있는 핸들은 표를 다시 읽지 않고 그대로 쓴다.
    def test_live_handle_skips_the_database(self) -> None:
        handle = cache_table(TABLE)

        result = self.service.visualize(stat_id=91, table_handle=handle, **VISUALIZE_ARGS)

        self.assertTrue(result.structuredContent["ok"])
        self.assertEqual(self.repository.calls, 0)
        self.assertEqual(result.structuredContent["request"]["table_source"], "search_tables_cache")

    # 지난 요청의 핸들이 남아 있어도 요청을 실패시키지 않고 stat_id로 다시 읽는다.
    def test_stale_handle_falls_back_to_stat_id(self) -> None:
        result = self.service.visualize(
            stat_id=91, table_handle="table_91_1_gone", **VISUALIZE_ARGS,
        )
        body = result.structuredContent

        self.assertFalse(result.isError)
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["data"]["records"]), 3)
        self.assertEqual(body["request"]["table_source"], "database")
        self.assertIn("table_handle", body["warnings"][0])

    # 핸들이 다른 표를 가리키면 stat_id 쪽을 믿는다.
    def test_handle_pointing_at_another_table_is_ignored(self) -> None:
        handle = cache_table({**TABLE, "stat_id": 999})

        body = self.service.visualize(
            stat_id=91, table_handle=handle, **VISUALIZE_ARGS,
        ).structuredContent

        self.assertTrue(body["ok"])
        self.assertEqual(self.repository.calls, 1)
        self.assertIn("stat_id", body["warnings"][0])

    # 차트 아래 인용 줄에 적을 발간물·담당·페이지가 stats에 실려 있어야 한다.
    def test_stats_carry_the_citation_fields(self) -> None:
        handle = cache_table({
            **TABLE,
            "publication_kind": "major_statistics",
            "publication_period": "H2",
            "department": "지역공동체과",
            "page_start": 42,
        })

        body = self.service.visualize(
            stat_id=91, table_handle=handle, **VISUALIZE_ARGS,
        ).structuredContent

        self.assertEqual(body["stat"]["publication_label"], "2025년 하반기 주요통계집")
        self.assertEqual(body["stat"]["department"], "지역공동체과")
        self.assertEqual(body["stat"]["page_start"], 42)

    # stat_id로도 표를 찾지 못하면 그때는 오류로 끝낸다.
    def test_missing_table_still_errors(self) -> None:
        result = self.service.visualize(
            stat_id=404, table_handle="table_404_1_gone", **VISUALIZE_ARGS,
        )

        self.assertTrue(result.isError)
        self.assertIn("찾지 못했습니다", result.structuredContent["error"])


if __name__ == "__main__":
    unittest.main()
