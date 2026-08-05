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


if __name__ == "__main__":
    unittest.main()
