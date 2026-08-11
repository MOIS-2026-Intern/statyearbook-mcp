# -*- coding: utf-8 -*-
"""visualize 도구가 통계표 값을 차트 spec으로 옮기는지 검증한다."""
import unittest

from app.tools.service.visualization.chart_spec_builder import build_plot_spec
from app.tools.service.visualization.vega_lite_renderer import build_vega_lite_spec


COLUMNS = ["등급 Grade", "정원 Personnel"]

TABLE = {
    "stat_id": 12,
    "ref_id": "1-2-2",
    "publication_year": 2025,
    "chapter_no": 1,
    "section_no": 2,
    "level3_no": 2,
    "level4_no": None,
    "chapter": "정부조직",
    "section": "공무원 정원",
    "level3_title": "공무원 정원",
    "level4_title": "공무원 정원",
    "title_ko": "공무원 정원",
    "title_en": "Public Officials by Grade",
    "unit": "명",
    "base_date": "2024.12.31.",
    "table_seq": 1,
    "caption": "2024. 12. 31. 기준",
    "body": {
        "columns": COLUMNS,
        "records": [
            dict(zip(COLUMNS, ["1급 Grade 1", "1"])),
            dict(zip(COLUMNS, ["2급 Grade 2", "9"])),
            dict(zip(COLUMNS, ["3급 Grade 3", "90"])),
        ],
    },
}


STACKED_COLUMNS = ["지역 Region", "성별 Sex", "인원 Personnel"]

STACKED_TABLE = {
    **TABLE,
    "title_ko": "지역별 성별 인원",
    "body": {
        "columns": STACKED_COLUMNS,
        "records": [
            dict(zip(STACKED_COLUMNS, ["서울", "남자", "1200"])),
            dict(zip(STACKED_COLUMNS, ["서울", "여자", "1100"])),
            dict(zip(STACKED_COLUMNS, ["세종", "남자", "20"])),
            dict(zip(STACKED_COLUMNS, ["세종", "여자", "18"])),
        ],
    },
}


class VisualizeTests(unittest.TestCase):
    # 표의 숫자 값이 차트 데이터와 Vega-Lite spec에 그대로 전달돼야 한다.
    def test_bar_spec_carries_table_values_into_vega_lite(self) -> None:
        spec = build_plot_spec(
            TABLE,
            "등급별 정원",
            "bar",
            COLUMNS[0],
            COLUMNS[1],
            None,
            None,
            "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertTrue(spec["ok"])
        self.assertEqual(spec["chart"]["type"], "bar")
        self.assertEqual(spec["chart"]["unit"], "명")
        self.assertEqual(spec["chart"]["x"], COLUMNS[0])
        self.assertEqual(spec["chart"]["y"], COLUMNS[1])
        self.assertEqual(
            {record["x"]: record["value"] for record in spec["data"]["records"]},
            {"1급 Grade 1": 1.0, "2급 Grade 2": 9.0, "3급 Grade 3": 90.0},
        )
        self.assertEqual(len(vega_lite["data"]["values"]), 3)

    # 누적 막대는 층 값을 층 가운데에, 막대 합계를 꼭대기에 표시해야 한다.
    def test_stacked_bar_spec_labels_segments_and_totals(self) -> None:
        spec = build_plot_spec(
            STACKED_TABLE,
            "지역별 성별 인원",
            "stacked_bar",
            STACKED_COLUMNS[0],
            STACKED_COLUMNS[2],
            STACKED_COLUMNS[1],
            None,
            "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "stacked_bar")
        bar_layer, segment_layer, total_layer = vega_lite["layer"]
        self.assertEqual(bar_layer["mark"], "bar")
        self.assertEqual(segment_layer["encoding"]["y"]["stack"], "zero")
        self.assertEqual(segment_layer["encoding"]["y"]["bandPosition"], 0.5)
        # 층 크기는 확정된 축에서 재야 정확하므로 scale() 식으로 판단한다.
        self.assertIn("scale('y', 0)", segment_layer["encoding"]["text"]["condition"]["test"])
        self.assertEqual(segment_layer["encoding"]["text"]["value"], "")
        # 층이 얇아도 레코드를 지우지 않고 라벨만 비워 층 위치를 유지한다.
        self.assertEqual(len(vega_lite["data"]["values"]), 4)
        self.assertEqual(total_layer["encoding"]["y"]["aggregate"], "sum")
        self.assertEqual(total_layer["encoding"]["text"]["aggregate"], "sum")
        self.assertEqual(total_layer["mark"]["baseline"], "bottom")

    # 막대와 라벨이 같은 순서로 쌓이도록 계열 순서를 spec에 박아야 한다.
    def test_stacked_bar_spec_pins_stack_order(self) -> None:
        spec = build_plot_spec(
            STACKED_TABLE,
            "지역별 성별 인원",
            "stacked_bar",
            STACKED_COLUMNS[0],
            STACKED_COLUMNS[2],
            STACKED_COLUMNS[1],
            None,
            "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        bar_layer, segment_layer, total_layer = vega_lite["layer"]
        self.assertEqual(bar_layer["encoding"]["order"]["field"], "_stack_order")
        self.assertEqual(segment_layer["encoding"]["order"], bar_layer["encoding"]["order"])
        # 합계 레이어가 순서를 물려받으면 계열별로 나뉘어 합계 대신 낱값이 찍힌다.
        self.assertNotIn("order", total_layer["encoding"])
        # 계열명 오름차순의 첫 계열이 맨 위에 오도록 내림차순 순위를 매긴다.
        self.assertEqual(
            {value["series"]: value["_stack_order"] for value in vega_lite["data"]["values"]},
            {"여자": 0, "남자": 1},
        )

    # 누적 막대에서도 값 기준 정렬이 유지돼야 한다(레이어별 도메인 통합으로 정렬이 무시되지 않도록).
    def test_stacked_bar_spec_uses_precomputed_category_order(self) -> None:
        spec = build_plot_spec(
            STACKED_TABLE,
            "지역별 성별 인원",
            "stacked_bar",
            STACKED_COLUMNS[0],
            STACKED_COLUMNS[2],
            STACKED_COLUMNS[1],
            None,
            "exclude",
            sort_order="ascending",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(vega_lite["encoding"]["x"]["sort"], ["세종", "서울"])


if __name__ == "__main__":
    unittest.main()
