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


YEAR_SERIES_COLUMNS = ["연도 Year", "지역 Region", "인구 Population"]


# 컬럼-값 목록으로 표 본문을 만든다.
def body(columns: list[str], rows: list[list[str]]) -> dict:
    return {"columns": columns, "records": [dict(zip(columns, row)) for row in rows]}


YEAR_SERIES_TABLE = {
    **TABLE,
    "title_ko": "연도별 지역 인구",
    "unit": "천명",
    "body": body(YEAR_SERIES_COLUMNS, [
        ["2021", "서울", "950"],
        ["2021", "부산", "330"],
        ["2022", "서울", "930"],
        ["2022", "부산", "340"],
        ["2023", "서울", "900"],
        ["2023", "부산", "960"],
    ]),
}
TWO_YEAR_TABLE = {
    **YEAR_SERIES_TABLE,
    "body": body(YEAR_SERIES_COLUMNS, [
        ["2021", "서울", "950"],
        ["2021", "부산", "330"],
        ["2023", "서울", "900"],
        ["2023", "부산", "360"],
    ]),
}
WIDE_YEAR_COLUMNS = ["연도 Year 지역 Region", "2021", "2022", "2023"]
# 통계연보에서 가장 흔한 모양: 행이 지역, 열이 연도.
WIDE_YEAR_TABLE = {
    **TABLE,
    "title_ko": "연도별 지역 인구",
    "unit": "천명",
    "body": body(WIDE_YEAR_COLUMNS, [
        ["계 Total", "2,300", "2,290", "2,270"],
        ["서 울 Seoul", "950", "930", "900"],
        ["부 산 Busan", "930", "940", "960"],
        ["대 구 Daegu", "420", "420", "410"],
    ]),
}
DELTA_COLUMNS = ["지역 Region", "전년 대비 증감 Change"]
DELTA_TABLE = {
    **TABLE,
    "title_ko": "지역별 전년 대비 인구 증감",
    "body": body(DELTA_COLUMNS, [
        ["서울", "-12,400"],
        ["부산", "-3,100"],
        ["세종", "5,600"],
    ]),
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


class ChartSelectionTests(unittest.TestCase):
    # 구성비를 묻는데 계열이 있으면 항목마다 100%로 맞춰 구성만 견주게 해야 한다.
    def test_share_query_with_series_selects_normalized_stacked_bar(self) -> None:
        spec = build_plot_spec(
            STACKED_TABLE,
            "지역별 성별 인원 구성비",
            "auto",
            STACKED_COLUMNS[0],
            STACKED_COLUMNS[2],
            STACKED_COLUMNS[1],
            None,
            "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "stacked_bar_100")
        self.assertEqual(vega_lite["encoding"]["y"]["stack"], "normalize")
        # 정규화 축은 원래 값을 감추므로 층 라벨에 쓸 비중을 서버가 미리 계산한다.
        shares = {
            (value["x"], value["series"]): round(value["_share"], 4)
            for value in vega_lite["data"]["values"]
        }
        self.assertEqual(shares[("서울", "남자")], round(1200 / 2300, 4))
        self.assertEqual(shares[("세종", "여자")], round(18 / 38, 4))

    # 음수가 섞인 값은 0을 기준으로 갈라야 늘었는지 줄었는지 한눈에 보인다.
    def test_negative_values_select_a_diverging_bar(self) -> None:
        spec = build_plot_spec(
            DELTA_TABLE, "지역별 인구 증감", "auto",
            DELTA_COLUMNS[0], DELTA_COLUMNS[1], None, None, "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "diverging_bar")
        bar_layer, baseline = vega_lite["layer"][0], vega_lite["layer"][1]
        self.assertEqual(bar_layer["encoding"]["color"]["condition"]["test"], "datum.value < 0")
        # 기준선은 범주 인코딩을 물려받지 않아야 축을 가로지른다.
        self.assertEqual(baseline["mark"]["type"], "rule")
        self.assertEqual(baseline["encoding"], {"y": {"datum": 0}})
        self.assertNotIn("encoding", vega_lite)
        # 증감 차트는 부호가 곧 정보라 라벨에 +/- 를 붙인다.
        self.assertTrue(
            all(
                layer["encoding"]["text"]["format"] == "+,.2~f"
                for layer in vega_lite["layer"][2:]
            )
        )

    # 폭포 차트는 앞 단계의 누적 위에 다음 단계를 얹어야 한다.
    def test_waterfall_stacks_each_step_on_the_running_total(self) -> None:
        spec = build_plot_spec(
            DELTA_TABLE, "지역별 인구 증감", "waterfall",
            DELTA_COLUMNS[0], DELTA_COLUMNS[1], None, None, "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "waterfall")
        self.assertEqual(
            [(value["_start"], value["_end"]) for value in vega_lite["data"]["values"]],
            [(0.0, -12400.0), (-12400.0, -15500.0), (-15500.0, -9900.0)],
        )
        bar_layer = vega_lite["layer"][0]
        self.assertEqual(bar_layer["encoding"]["y"]["field"], "_start")
        self.assertEqual(bar_layer["encoding"]["y2"]["field"], "_end")
        # 라벨은 막대의 바깥쪽 끝에 붙어야 줄어든 단계에서도 막대를 가리지 않는다.
        self.assertEqual(vega_lite["layer"][1]["encoding"]["y"]["field"], "_label_at")

    # 순위 변화를 물으면 값 대신 시점별 순위를 이어야 자리바꿈이 보인다.
    def test_rank_query_over_years_selects_a_bump_chart(self) -> None:
        spec = build_plot_spec(
            YEAR_SERIES_TABLE, "연도별 인구 순위 변화", "auto",
            YEAR_SERIES_COLUMNS[0], YEAR_SERIES_COLUMNS[2], YEAR_SERIES_COLUMNS[1],
            None, "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "bump")
        self.assertEqual(vega_lite["encoding"]["y"]["field"], "_rank")
        # 1위가 위로 오도록 축을 뒤집는다.
        self.assertTrue(vega_lite["encoding"]["y"]["scale"]["reverse"])
        ranks = {
            (value["x"], value["series"]): value["_rank"] for value in vega_lite["data"]["values"]
        }
        self.assertEqual(ranks[(2021, "서울")], 1)
        self.assertEqual(ranks[(2023, "서울")], 2)
        self.assertEqual(ranks[(2023, "부산")], 1)

    # 시점이 둘뿐이면 선그래프보다 항목별 기울기가 변화 방향을 잘 보여준다.
    def test_two_year_series_selects_a_slope_chart(self) -> None:
        spec = build_plot_spec(
            TWO_YEAR_TABLE, "연도별 지역 인구", "auto",
            YEAR_SERIES_COLUMNS[0], YEAR_SERIES_COLUMNS[2], YEAR_SERIES_COLUMNS[1],
            None, "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "slope")
        edges = {
            (value["x"], value["series"]): value["_edge_label"]
            for value in vega_lite["data"]["values"]
        }
        # 선이 겹쳐 범례로 계열을 찾기 어려우므로 시작점에 이름을 함께 적는다.
        self.assertEqual(edges[(2021, "서울")], "서울 950")
        self.assertEqual(edges[(2023, "서울")], "900")

    # 롤리팝은 막대보다 가벼워 항목이 많은 순위 비교에 쓴다.
    def test_lollipop_draws_a_rule_from_zero_to_each_value(self) -> None:
        spec = build_plot_spec(
            TABLE, "등급별 정원", "lollipop", COLUMNS[0], COLUMNS[1], None, None, "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "lollipop")
        rule_layer, point_layer = vega_lite["layer"][0], vega_lite["layer"][1]
        self.assertEqual(rule_layer["encoding"]["y2"], {"datum": 0})
        self.assertEqual(point_layer["mark"]["type"], "point")

    # 행이 지역, 열이 연도인 표는 그대로는 순위를 매길 수 없어 범주별 시계열로 펴야 한다.
    def test_wide_year_table_is_pivoted_for_a_rank_query(self) -> None:
        spec = build_plot_spec(
            WIDE_YEAR_TABLE, "연도별 지역 인구 순위 변화", "auto",
            None, None, None, None, "auto",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "bump")
        self.assertEqual(spec["transform"]["type"], "wide_year_rows_to_series")
        # 전국 합계 행을 개별 지역과 나란히 두면 순위가 뒤틀린다.
        self.assertEqual(
            {record["series"] for record in spec["data"]["records"]}, {"서울", "부산", "대구"},
        )
        ranks = {
            (value["x"], value["series"]): value["_rank"] for value in vega_lite["data"]["values"]
        }
        self.assertEqual(ranks[(2021, "서울")], 1)
        self.assertEqual(ranks[(2023, "부산")], 1)

    # 기울기 그래프는 처음과 마지막 연도만 남겨 변화 방향을 보여준다.
    def test_wide_year_table_slope_keeps_only_both_ends(self) -> None:
        spec = build_plot_spec(
            WIDE_YEAR_TABLE, "지역별 인구 변화", "slope",
            None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["type"], "slope")
        self.assertEqual({record["x"] for record in spec["data"]["records"]}, {2021, 2023})

    # 특정 지역 하나의 추이를 물으면 기존처럼 그 행만 펴야 한다.
    def test_wide_year_table_still_follows_one_row_for_a_trend_query(self) -> None:
        spec = build_plot_spec(
            WIDE_YEAR_TABLE, "서울 인구 추이", "auto", None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["type"], "line")
        self.assertEqual(spec["transform"]["selected_category"], "서울")

    # 한 표 안의 계열도 콤보로 그릴 수 있어야 하며, 계열 목록은 레코드에서 세운다.
    def test_combo_builds_series_from_records(self) -> None:
        spec = build_plot_spec(
            STACKED_TABLE,
            "지역별 성별 인원",
            "combo",
            STACKED_COLUMNS[0],
            STACKED_COLUMNS[2],
            STACKED_COLUMNS[1],
            None,
            "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "combo")
        first, second = vega_lite["layer"]
        self.assertEqual(first["transform"][0]["filter"], {"field": "series", "equal": "남자"})
        self.assertEqual(first["layer"][0]["mark"]["type"], "bar")
        self.assertEqual(second["layer"][0]["mark"]["type"], "line")
        # 축을 나누지 않았으므로 두 계열이 같은 값 축을 쓴다.
        self.assertNotIn("resolve", vega_lite)
        self.assertEqual(first["encoding"]["y"]["title"], second["encoding"]["y"]["title"])

    # 지역처럼 순서가 없는 축을 선으로 이으면 없는 추세가 보이므로 막대로 바꿔야 한다.
    def test_line_request_on_unordered_categories_falls_back_to_bars(self) -> None:
        spec = build_plot_spec(
            DELTA_TABLE, "지역별 인구 증감", "line",
            DELTA_COLUMNS[0], DELTA_COLUMNS[1], None, None, "exclude",
        )

        self.assertEqual(spec["chart"]["type"], "bar")
        self.assertIn("순서가 있는 축", spec["chart"]["reason"])

    # 숫자가 들어간 라벨은 순서가 있으므로 선그래프 요청을 그대로 둔다.
    def test_line_request_on_ordered_categories_is_kept(self) -> None:
        spec = build_plot_spec(
            TABLE, "등급별 정원", "line", COLUMNS[0], COLUMNS[1], None, None, "exclude",
        )

        self.assertEqual(spec["chart"]["type"], "line")


if __name__ == "__main__":
    unittest.main()
