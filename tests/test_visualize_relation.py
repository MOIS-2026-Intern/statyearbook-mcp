# -*- coding: utf-8 -*-
"""한 표에서 고른 두 지표의 관계를 산점도와 나눈 칸으로 그리는지 검증한다."""
import unittest

from app.tools.service.visualization.chart_spec_builder import build_plot_spec
from app.tools.service.visualization.vega_lite_renderer import build_vega_lite_spec
from tests.test_visualize_derive import table


# 단위가 '개소, 백만원' 두 가지로 적혀 있고 지표 규모도 크게 벌어지는 표.
DISASTER_DISTRICTS = table(
    567, "지역별 자연재해위험개선지구 정비사업", "개소, 백만원",
    [
        "구분 Classification 지역 Region",
        "대상지구(개소) Target District(place)",
        "사업비 Working Expenses_계 Total",
    ],
    [
        ["계 Total", "842", "1,962,738"],
        ["부 산 Busan", "427", "993,180"],
        ["대 구 Daegu", "15", "28,554"],
        ["광 주 Gwangju", "8", "11,820"],
        ["경 남 Gyeongnam", "83", "254,060"],
        ["제 주 Jeju", "68", "153,328"],
        ["서 울 Seoul", "-", "-"],
    ],
)

DISTRICT_COUNT = "대상지구(개소) Target District(place)"
WORKING_EXPENSES = "사업비 Working Expenses_계 Total"


# 두 지표를 고른 기본 호출을 구성한다.
def build_spec(metrics: list[dict], **kwargs) -> dict:
    options = {
        "query": None,
        "chart_type": "scatter",
        "x": None,
        "y": None,
        "group": None,
        "top_n": None,
        "metrics": metrics,
    }
    options.update(kwargs)
    return build_plot_spec(DISASTER_DISTRICTS, **options)


class SingleTableRelationScatterTests(unittest.TestCase):
    # 한 표에서 고른 두 지표도 서로 다른 축에 놓아 산점도로 그려야 한다.
    def test_two_metrics_of_one_table_become_scatter(self) -> None:
        spec = build_spec([
            {"column": DISTRICT_COUNT, "label": "대상지구 수"},
            {"column": WORKING_EXPENSES, "label": "사업비"},
        ])

        self.assertEqual(spec["chart"]["type"], "scatter")
        self.assertEqual(spec["chart"]["decision_source"], "selection_plan")
        self.assertIsNone(spec["chart"]["group"])
        points = {record["label"]: (record["x"], record["value"]) for record in spec["data"]["records"]}
        self.assertEqual(points["부산"], (427, 993180))
        self.assertEqual(points["제주"], (68, 153328))

    # 축 제목에는 지표마다 갈라낸 단위가 붙어야 한다.
    def test_axis_titles_carry_each_metric_unit(self) -> None:
        spec = build_spec([
            {"column": DISTRICT_COUNT, "label": "대상지구 수"},
            {"column": WORKING_EXPENSES, "label": "사업비"},
        ])

        self.assertEqual(spec["chart"]["x_title"], "대상지구 수 (개소)")
        self.assertEqual(spec["chart"]["y_title"], "사업비 (백만원)")

    # 합계 행과 값이 없는 행은 점으로 찍지 않는다.
    def test_total_and_empty_rows_are_dropped(self) -> None:
        spec = build_spec([
            {"column": DISTRICT_COUNT, "label": "대상지구 수"},
            {"column": WORKING_EXPENSES, "label": "사업비"},
        ])

        labels = {record["label"] for record in spec["data"]["records"]}
        self.assertNotIn("계", labels)
        self.assertNotIn("서울", labels)
        self.assertTrue(any("서울" in warning for warning in spec["warnings"]))

    # 산점도 spec은 두 지표를 수량형 x·y로 렌더링해야 한다.
    def test_vega_spec_uses_quantitative_axes(self) -> None:
        spec = build_spec([
            {"column": DISTRICT_COUNT, "label": "대상지구 수"},
            {"column": WORKING_EXPENSES, "label": "사업비"},
        ])
        vega = build_vega_lite_spec(spec)

        self.assertEqual(vega["encoding"]["x"]["type"], "quantitative")
        self.assertEqual(vega["encoding"]["y"]["type"], "quantitative")
        self.assertEqual(vega["encoding"]["x"]["title"], "대상지구 수 (개소)")

    # 지표가 하나뿐이면 짝지을 값이 없어 산점도로 그릴 수 없다.
    def test_single_metric_falls_back(self) -> None:
        spec = build_spec([{"column": DISTRICT_COUNT, "label": "대상지구 수"}])

        self.assertNotEqual(spec["chart"]["type"], "scatter")

    # 차트를 지정하지 않고 관계만 물어도 두 지표를 축으로 갈라야 한다.
    def test_relation_query_selects_scatter_without_chart_type(self) -> None:
        spec = build_spec(
            [
                {"column": DISTRICT_COUNT, "label": "대상지구 수"},
                {"column": WORKING_EXPENSES, "label": "사업비"},
            ],
            chart_type="auto",
            query="시도별 대상지구 수와 사업비의 관계",
        )

        self.assertEqual(spec["chart"]["type"], "scatter")

    # 관계를 묻지 않은 auto 요청까지 산점도로 바꾸지는 않는다.
    def test_plain_auto_query_keeps_bar(self) -> None:
        spec = build_spec(
            [
                {"column": DISTRICT_COUNT, "label": "대상지구 수"},
                {"column": WORKING_EXPENSES, "label": "사업비"},
            ],
            chart_type="auto",
            query="시도별 대상지구 수와 사업비",
        )

        self.assertNotEqual(spec["chart"]["type"], "scatter")


class SharedUnitAxisSplitTests(unittest.TestCase):
    # 표가 단위를 '개소, 백만원'으로 묶어 적어도 지표마다 단위를 갈라야 한다.
    def test_table_unit_is_split_across_metrics(self) -> None:
        spec = build_spec(
            [
                {"column": DISTRICT_COUNT, "label": "대상지구 수"},
                {"column": WORKING_EXPENSES, "label": "사업비"},
            ],
            chart_type="grouped_bar",
        )

        units = {item["label"]: item["unit"] for item in spec["chart"]["series"]}
        self.assertEqual(units["대상지구 수"], "개소")
        self.assertEqual(units["사업비"], "백만원")

    # 규모가 크게 벌어지는 두 지표를 한 축에 두면 작은 쪽이 아예 보이지 않는다.
    def test_scale_gap_splits_value_axis(self) -> None:
        spec = build_spec(
            [
                {"column": DISTRICT_COUNT, "label": "대상지구 수"},
                {"column": WORKING_EXPENSES, "label": "사업비"},
            ],
            chart_type="grouped_bar",
        )

        self.assertTrue(spec["chart"]["dual_axis"])
        # 지역 축이라 막대와 선을 겹치지 않고 지표마다 칸을 나눈다.
        self.assertEqual(spec["chart"]["type"], "paired_panels")


class CategoryAxisComboTests(unittest.TestCase):
    # 선은 시간의 흐름을 그리는 mark다. 시도 축에 콤보를 요청해도 막대와 선을 겹치지 않는다.
    def test_combo_request_on_region_axis_becomes_panels(self) -> None:
        spec = build_spec(
            [
                {"column": DISTRICT_COUNT, "label": "대상지구 수"},
                {"column": WORKING_EXPENSES, "label": "사업비"},
            ],
            chart_type="combo",
        )

        self.assertEqual(spec["chart"]["type"], "paired_panels")
        self.assertTrue(spec["chart"]["dual_axis"])
        self.assertIn("칸마다 눈금이 다르므로", spec["chart"]["reason"])

    # 나눈 칸은 지표마다 자기 값 축을 쓰고, 항목 순서는 두 칸이 같아야 한다.
    def test_panels_share_the_category_axis(self) -> None:
        spec = build_spec(
            [
                {"column": DISTRICT_COUNT, "label": "대상지구 수"},
                {"column": WORKING_EXPENSES, "label": "사업비"},
            ],
            chart_type="combo",
        )
        first, second = build_vega_lite_spec(spec)["vconcat"]

        self.assertEqual(first["encoding"]["y"]["title"], "대상지구 수 (개소)")
        self.assertEqual(second["encoding"]["y"]["title"], "사업비 (백만원)")
        self.assertEqual(first["layer"][0]["mark"]["type"], "bar")
        self.assertEqual(second["layer"][0]["mark"]["type"], "bar")
        self.assertEqual(first["encoding"]["x"]["sort"], second["encoding"]["x"]["sort"])
        # 칸을 두 개 쌓아도 한 장짜리 차트만큼만 자리를 쓰도록 칸 높이를 정해 보낸다.
        self.assertTrue(all(panel["height"] > 0 for panel in (first, second)))


if __name__ == "__main__":
    unittest.main()
