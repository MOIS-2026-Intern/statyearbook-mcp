# -*- coding: utf-8 -*-
"""visualize가 두 통계표의 값을 항목마다 계산해 파생 지표로 그리는지 검증한다."""
import unittest

from mcp.server.fastmcp import FastMCP

from app.tools.service.visualization.chart_spec_builder import build_plot_spec
from app.tools.service.visualization.multi_table_spec_builder import build_multi_source_spec
from app.tools.service.visualization.vega_lite_renderer import build_vega_lite_spec
from app.tools.visualize import register as register_visualize


# 표 메타데이터의 공통 골격을 만든다.
def table(
    stat_id: int,
    title: str,
    unit: str,
    columns: list[str],
    rows: list[list[str]],
    base_date: str = "2025.12.31.",
) -> dict:
    return {
        "stat_id": stat_id,
        "ref_id": f"5-1-{stat_id}",
        "publication_year": 2026,
        "chapter_no": 5,
        "section_no": 1,
        "level3_no": stat_id,
        "level4_no": None,
        "chapter": "지방행정",
        "section": "지방공무원",
        "level3_title": title,
        "level4_title": title,
        "title_ko": title,
        "title_en": title,
        "unit": unit,
        "base_date": base_date,
        "page_start": 20,
        "table_seq": 1,
        "caption": f"{base_date} 기준",
        "body": {"columns": columns, "records": [dict(zip(columns, row)) for row in rows]},
    }


QUOTA = table(
    433, "지역별 지방공무원 정원", "명",
    ["지역", "정원"],
    [
        ["강 원 Gangwon", "22,884"],
        ["서 울 Seoul", "56,449"],
        ["경 기 Gyeonggi", "68,650"],
        ["합계", "148,000"],
    ],
)
# 같은 지역을 정식 명칭으로 적어 표기가 다른 표.
POPULATION = table(
    91, "지역별 주민등록인구", "명",
    ["구분 Classification 지역 Region", "인 구 수 Population_계 Total"],
    [
        ["계 Total", "51,117,378"],
        ["강원도", "1,527,000"],
        ["서울특별시", "9,299,548"],
        ["경기도", "13,660,000"],
    ],
)
# 한 지역이 본청·시군구 두 행으로 나뉜 정원 표.
QUOTA_SPLIT = table(
    434, "지역별 지방공무원 정원", "명",
    ["지역", "구분", "정원"],
    [
        ["강 원 Gangwon", "본청", "10,000"],
        ["강 원 Gangwon", "시군구", "12,884"],
        ["서 울 Seoul", "본청", "56,449"],
    ],
)
# 인구가 0으로 적힌 지역이 섞인 표.
POPULATION_WITH_ZERO = table(
    92, "지역별 주민등록인구", "명",
    ["지역", "인구"],
    [["강원도", "1,527,000"], ["서울특별시", "0"]],
)
# 단위 표기에 배수가 붙어 셀 값이 이미 줄어 있는 표.
POPULATION_IN_THOUSANDS = table(
    93, "지역별 주민등록인구", "천 명",
    ["지역", "인구"],
    [["강원도", "1,527"], ["서울특별시", "9,300"]],
)
# 정원과 단위가 달라 빼면 뜻이 없는 표.
DEBT = table(
    166, "지역별 지방자치단체 채무", "억원",
    ["지역", "계 Total"],
    [["강원도", "9,700"], ["서울특별시", "115,695"]],
)
# 연도를 기준으로 맞대는 표.
QUOTA_BY_YEAR = table(
    435, "연도별 지방공무원 정원", "명",
    ["연도", "정원"],
    [["2023", "320,000"], ["2024", "330,000"]],
)
POPULATION_BY_YEAR = table(
    94, "연도별 주민등록인구", "명",
    ["연도", "인구"],
    [["2023", "51,300,000"], ["2024", "51,200,000"]],
)


# build_multi_source_spec 호출 인자를 간단히 구성한다.
def build(tables_and_requests: list[tuple[dict, dict]], **kwargs) -> dict:
    sources = [{"table": data, "request": request} for data, request in tables_and_requests]
    return build_multi_source_spec(sources, **kwargs)


# 정원 표와 인구 표로 '1만 명당' 파생 지표를 만드는 기본 호출을 구성한다.
def build_per_capita(**kwargs) -> dict:
    options = {
        "query": "시도별 주민 1만 명당 지방공무원 정원",
        "derive": {"op": "per_capita", "numerator": 0, "denominator": 1, "per": 10000},
    }
    options.update(kwargs)
    return build(
        [(QUOTA, {"label": "지방공무원 정원"}), (POPULATION, {"label": "주민등록인구"})],
        **options,
    )


class DerivedMetricTests(unittest.TestCase):
    # 두 표를 지역으로 맞춰 항목마다 나눈 값 하나짜리 계열을 만들어야 한다.
    def test_per_capita_divides_matched_regions(self) -> None:
        spec = build_per_capita()

        self.assertTrue(spec["ok"])
        self.assertEqual(spec["chart"]["type"], "bar")
        # 계열이 하나뿐이라 계열명을 두지 않는다. 항목이 하나인 범례만 늘기 때문이다.
        self.assertIsNone(spec["chart"]["group"])
        self.assertEqual([item["label"] for item in spec["chart"]["series"]], ["지방공무원 정원 (1만 명당)"])
        self.assertEqual(spec["chart"]["unit"], "명/1만 명")

        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertEqual(set(values), {"강원", "서울", "경기"})
        self.assertAlmostEqual(values["강원"], 22884 / 1527000 * 10000, places=6)
        self.assertAlmostEqual(values["서울"], 56449 / 9299548 * 10000, places=6)
        self.assertAlmostEqual(values["경기"], 68650 / 13660000 * 10000, places=6)
        self.assertTrue(all(record["series"] is None for record in spec["data"]["records"]))

    # 한 지역이 여러 행에 나뉘어 있으면 먼저 더하고 나서 나눠야 한다.
    # 행마다 나눈 뒤 평균을 내면 평균의 평균이 되어 값이 절반으로 어긋난다.
    def test_rows_are_summed_before_dividing(self) -> None:
        spec = build(
            [(QUOTA_SPLIT, {"label": "정원"}), (POPULATION, {"label": "인구"})],
            query="시도별 주민 1만 명당 지방공무원 정원",
            derive={"op": "per_capita", "per": 10000},
        )

        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertAlmostEqual(values["강원"], (10000 + 12884) / 1527000 * 10000, places=6)
        # 행별로 나눈 뒤 평균을 냈다면 나왔을 값이 아니어야 한다.
        self.assertNotAlmostEqual(values["강원"], (10000 + 12884) / 1527000 * 10000 / 2, places=2)

    # 분모가 0인 항목은 나눌 수 없으므로 빼고 그 사실을 알려야 한다.
    def test_zero_denominator_is_dropped_with_warning(self) -> None:
        spec = build(
            [(QUOTA, {"label": "정원"}), (POPULATION_WITH_ZERO, {"label": "인구"})],
            query="주민 1만 명당 정원",
            derive={"op": "per_capita", "per": 10000},
        )

        self.assertEqual([record["x"] for record in spec["data"]["records"]], ["강원"])
        self.assertTrue(
            any("0인 항목" in warning and "서울" in warning for warning in spec["warnings"]),
            spec["warnings"],
        )

    # 순위를 묻는 요청은 값 순서를 세워야 순위가 드러난다.
    def test_rank_query_sorts_values_descending(self) -> None:
        spec = build_per_capita(query="시도별 주민 1만 명당 지방공무원 정원 순위")

        self.assertEqual(spec["request"]["resolved_sort_order"], "descending")
        self.assertEqual([record["x"] for record in spec["data"]["records"]], ["강원", "서울", "경기"])
        self.assertEqual(spec["chart"]["category_order"], ["강원", "서울", "경기"])

    # 사용자가 정렬을 직접 요청하면 순위 기본값이 그 요청을 덮지 않아야 한다.
    def test_explicit_sort_order_wins_over_rank_default(self) -> None:
        spec = build_per_capita(query="1만 명당 정원 순위", sort_order="ascending")

        self.assertEqual(spec["request"]["resolved_sort_order"], "ascending")
        self.assertEqual([record["x"] for record in spec["data"]["records"]], ["경기", "서울", "강원"])

    # 답변이 계산 근거를 인용할 수 있도록 분자·분모와 결과를 한 줄에 담아야 한다.
    def test_joined_rows_keep_numerator_denominator_and_result(self) -> None:
        spec = build_per_capita()

        row = next(row for row in spec["data"]["joined_rows"] if row["항목"] == "강원")
        self.assertEqual(row["지방공무원 정원"], 22884.0)
        self.assertEqual(row["주민등록인구"], 1527000.0)
        self.assertAlmostEqual(row["지방공무원 정원 (1만 명당)"], 22884 / 1527000 * 10000, places=6)

    # 도구가 배수를 빠뜨려도 질의에 적힌 '1만 명당'에서 읽어 보완해야 한다.
    def test_scale_is_read_from_query_when_per_is_missing(self) -> None:
        spec = build_per_capita(derive={"op": "per_capita"})

        self.assertEqual(spec["chart"]["unit"], "명/1만 명")
        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertAlmostEqual(values["강원"], 22884 / 1527000 * 10000, places=6)

    # 질의에 적힌 배수가 10만 명당이면 그 배수를 적용해야 한다.
    def test_hundred_thousand_scale_is_read_from_query(self) -> None:
        spec = build_per_capita(query="인구 10만 명당 지방공무원 정원", derive={"op": "per_capita"})

        self.assertEqual(spec["chart"]["unit"], "명/10만 명")
        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertAlmostEqual(values["강원"], 22884 / 1527000 * 100000, places=6)

    # 두 표의 근거가 되는 표를 모두 밝혀야 답변이 출처를 빠뜨리지 않는다.
    def test_both_source_tables_are_reported(self) -> None:
        spec = build_per_capita()

        self.assertEqual([stat["stat_id"] for stat in spec["stats"]], [433, 91])
        self.assertEqual([source["label"] for source in spec["sources"]], ["지방공무원 정원", "주민등록인구"])
        self.assertEqual(spec["transform"]["type"], "multi_source_derive")
        self.assertEqual(spec["transform"]["derived"]["op"], "per_capita")
        self.assertEqual(spec["transform"]["derived"]["per"], 10000)
        self.assertEqual(spec["transform"]["derived"]["numerator"]["stat_id"], 433)
        self.assertEqual(spec["transform"]["derived"]["denominator"]["stat_id"], 91)

    # 분모 표의 단위에 배수가 붙어 있으면 자릿수가 어긋날 수 있음을 알려야 한다.
    def test_denominator_unit_multiplier_is_warned(self) -> None:
        spec = build(
            [(QUOTA, {"label": "정원"}), (POPULATION_IN_THOUSANDS, {"label": "인구"})],
            query="주민 1만 명당 정원",
            derive={"op": "per_capita", "per": 10000},
        )

        self.assertTrue(
            any("천 명" in warning and "자릿수" in warning for warning in spec["warnings"]),
            spec["warnings"],
        )

    # 기준일이 다른 표를 나누면 서로 다른 시점의 값을 나눈 결과임을 알려야 한다.
    def test_different_base_dates_are_warned(self) -> None:
        older = table(
            95, "지역별 주민등록인구", "명",
            ["지역", "인구"],
            [["강원도", "1,527,000"], ["서울특별시", "9,299,548"]],
            base_date="2023.12.31.",
        )
        spec = build(
            [(QUOTA, {"label": "정원"}), (older, {"label": "인구"})],
            query="주민 1만 명당 정원",
            derive={"op": "per_capita", "per": 10000},
        )

        self.assertTrue(
            any("기준일이 달라" in warning for warning in spec["warnings"]), spec["warnings"],
        )

    # 비중은 백분율이므로 단위를 %로 두어야 한다.
    def test_share_produces_percent_unit(self) -> None:
        spec = build(
            [(QUOTA, {"label": "정원"}), (POPULATION, {"label": "인구"})],
            query="인구 대비 공무원 비중",
            derive={"op": "share"},
        )

        self.assertEqual(spec["chart"]["unit"], "%")
        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertAlmostEqual(values["강원"], 22884 / 1527000 * 100, places=6)

    # 단위가 같은 두 값의 배수는 '배'로 읽는다.
    def test_ratio_of_same_unit_is_labelled_as_multiple(self) -> None:
        spec = build(
            [(QUOTA, {"label": "정원"}), (POPULATION, {"label": "인구"})],
            query="인구 대비 정원",
            derive={"op": "ratio"},
        )

        self.assertEqual(spec["chart"]["unit"], "배")

    # 연도로 맞댄 파생 지표는 추이를 보여주는 선그래프가 되어야 한다.
    def test_year_axis_derives_into_line_chart(self) -> None:
        spec = build(
            [(QUOTA_BY_YEAR, {"label": "정원"}), (POPULATION_BY_YEAR, {"label": "인구"})],
            query="연도별 주민 1만 명당 지방공무원 정원",
            derive={"op": "per_capita", "per": 10000},
        )

        self.assertEqual(spec["chart"]["type"], "line")
        self.assertEqual([record["x"] for record in spec["data"]["records"]], [2023, 2024])


class DerivedMetricFallbackTests(unittest.TestCase):
    # 단위가 다른 값을 빼면 뜻이 없으므로 계산하지 않고 두 계열을 그대로 그려야 한다.
    def test_difference_with_mismatched_units_falls_back(self) -> None:
        spec = build(
            [(QUOTA, {"label": "정원"}), (DEBT, {"label": "채무"})],
            query="정원과 채무의 차이",
            derive={"op": "difference"},
        )

        self.assertEqual([item["label"] for item in spec["chart"]["series"]], ["정원", "채무"])
        self.assertTrue(
            any("단위가 다른 값" in warning for warning in spec["warnings"]), spec["warnings"],
        )

    # 분자와 분모가 같은 표면 계산이 뜻을 잃으므로 두 계열을 그대로 그려야 한다.
    def test_same_source_for_numerator_and_denominator_falls_back(self) -> None:
        spec = build_per_capita(
            derive={"op": "per_capita", "numerator": 0, "denominator": 0, "per": 10000},
        )

        self.assertEqual(len(spec["chart"]["series"]), 2)
        self.assertTrue(
            any("분자와 분모가 같은 지표" in warning for warning in spec["warnings"]), spec["warnings"],
        )

    # sources에 없는 번호를 가리키면 계산하지 않고 두 계열을 그대로 그려야 한다.
    def test_out_of_range_index_falls_back(self) -> None:
        spec = build_per_capita(derive={"op": "per_capita", "numerator": 0, "denominator": 5})

        self.assertEqual(len(spec["chart"]["series"]), 2)
        self.assertTrue(
            any("범위를 벗어나" in warning for warning in spec["warnings"]), spec["warnings"],
        )

    # 알 수 없는 연산은 값을 지어내지 말고 두 계열을 그대로 그려야 한다.
    def test_unknown_operation_falls_back(self) -> None:
        spec = build_per_capita(derive={"op": "geometric_mean"})

        self.assertEqual(len(spec["chart"]["series"]), 2)
        self.assertTrue(
            any("지원하지 않는 파생 연산" in warning for warning in spec["warnings"]), spec["warnings"],
        )

    # 산점도는 지표 두 개가 필요하므로 파생 지표에는 쓰지 않고 막대로 바꿔야 한다.
    def test_scatter_request_on_derived_metric_falls_back_to_bar(self) -> None:
        spec = build_per_capita(chart_type="scatter")

        self.assertEqual(spec["chart"]["type"], "bar")


# 한 표 안에 분자와 분모가 함께 있는 표. 연보의 '지역별 주민등록인구'와 같은 모양이다.
POPULATION_WITH_HOUSEHOLDS = table(
    96, "지역별 주민등록인구", "명, 세대",
    ["구분 Classification 지역 Region", "인 구 수 Population_계 Total", "인 구 수 Population_남 Male",
     "인 구 수 Population_여 Female", "세대수 No. of Households"],
    [
        ["강 원 Gangwon", "1,527,000", "766,000", "761,000", "700,000"],
        ["서 울 Seoul", "9,299,548", "4,510,000", "4,789,548", "4,600,000"],
    ],
)
# 한 지역이 본청·시군구 두 행으로 나뉜 표.
POPULATION_SPLIT_ROWS = table(
    97, "지역별 주민등록인구", "명, 세대",
    ["지역", "구분", "인구", "세대수"],
    [
        ["강 원 Gangwon", "본청", "1,000,000", "400,000"],
        ["강 원 Gangwon", "시군구", "527,000", "300,000"],
    ],
)


# 한 표 안의 두 컬럼을 나누는 기본 호출을 구성한다.
def build_single_table(table_data: dict, metrics: list[dict], derive: dict, **kwargs) -> dict:
    options = {
        "query": "시도별 세대당 인구",
        "chart_type": "auto",
        "x": None,
        "y": None,
        "group": None,
        "top_n": None,
        "metrics": metrics,
        "derive": derive,
    }
    options.update(kwargs)
    return build_plot_spec(table_data, **options)


class SingleTableDerivedMetricTests(unittest.TestCase):
    # 한 표에서 고른 두 컬럼을 행마다 나눠 파생 지표 하나를 만들어야 한다.
    def test_two_columns_of_one_table_are_divided(self) -> None:
        spec = build_single_table(
            POPULATION_WITH_HOUSEHOLDS,
            [{"column": "인 구 수 Population_계 Total"}, {"column": "세대수 No. of Households"}],
            {"op": "per_capita", "numerator": 0, "denominator": 1, "per": 1},
        )

        self.assertEqual(spec["chart"]["type"], "bar")
        self.assertIsNone(spec["chart"]["group"])
        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertAlmostEqual(values["강원"], 1527000 / 700000, places=6)
        self.assertAlmostEqual(values["서울"], 9299548 / 4600000, places=6)
        self.assertTrue(all(record["series"] is None for record in spec["data"]["records"]))

    # 성비처럼 같은 표의 두 컬럼을 견주는 계산도 되어야 한다.
    def test_sex_ratio_within_one_table(self) -> None:
        spec = build_single_table(
            POPULATION_WITH_HOUSEHOLDS,
            [{"column": "인 구 수 Population_남 Male", "label": "남"},
             {"column": "인 구 수 Population_여 Female", "label": "여"}],
            {"op": "share"},
            query="시도별 여성 대비 남성 비율",
        )

        self.assertEqual(spec["chart"]["unit"], "%")
        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertAlmostEqual(values["강원"], 766000 / 761000 * 100, places=6)

    # 한 표 안에서도 같은 항목이 여러 행이면 먼저 더하고 나서 나눠야 한다.
    def test_repeated_rows_are_summed_before_dividing(self) -> None:
        spec = build_single_table(
            POPULATION_SPLIT_ROWS,
            [{"column": "인구"}, {"column": "세대수"}],
            {"op": "per_capita", "per": 1},
        )

        values = {record["x"]: record["value"] for record in spec["data"]["records"]}
        self.assertAlmostEqual(values["강원"], 1527000 / 700000, places=6)
        self.assertTrue(
            any("합계로 모은 뒤 계산" in warning for warning in spec["warnings"]), spec["warnings"],
        )

    # 계산 근거를 답변이 인용할 수 있도록 어느 컬럼을 나눴는지 남겨야 한다.
    def test_transform_records_the_two_columns(self) -> None:
        spec = build_single_table(
            POPULATION_WITH_HOUSEHOLDS,
            [{"column": "인 구 수 Population_계 Total"}, {"column": "세대수 No. of Households"}],
            {"op": "per_capita", "per": 1},
        )

        derived = spec["transform"]["derived"]
        self.assertEqual(spec["transform"]["type"], "derived_selection_plan")
        self.assertEqual(derived["op"], "per_capita")
        self.assertEqual(derived["numerator"]["column"], "인 구 수 Population_계 Total")
        self.assertEqual(derived["denominator"]["column"], "세대수 No. of Households")

    # 숫자 컬럼을 하나만 고르면 나눌 대상이 없으므로 무엇이 빠졌는지 알려야 한다.
    def test_single_metric_reports_what_is_missing(self) -> None:
        spec = build_single_table(
            POPULATION_WITH_HOUSEHOLDS,
            [{"column": "세대수 No. of Households"}],
            {"op": "per_capita", "per": 1},
        )

        self.assertTrue(
            any("두 개 필요해" in warning for warning in spec["warnings"]), spec["warnings"],
        )
        # 계산은 못 했어도 고른 지표는 그대로 그려 준다.
        self.assertTrue(spec["data"]["records"])


class DerivedMetricToolTests(unittest.IsolatedAsyncioTestCase):
    # 표를 하나만 준 파생 요청은 조용히 무시하지 말고 무엇이 빠졌는지 알려야 한다.
    async def test_derive_with_one_source_reports_what_is_missing(self) -> None:
        mcp = FastMCP("test")
        register_visualize(mcp)

        result = await mcp.call_tool(
            "visualize",
            {"sources": [{"stat_id": 433}], "derive": {"op": "per_capita", "per": 10000}},
        )

        self.assertTrue(result.isError)
        self.assertIn("sources에 표를 두 개", result.structuredContent["error"])
        self.assertIn("metrics에 숫자 컬럼을 두 개", result.structuredContent["error"])


class DerivedMetricRenderTests(unittest.TestCase):
    # 값 라벨을 접었을 때 warnings에 다시 부를 방법을 적으면 모델이 그대로 따라 같은 데이터를
    # 방향만 바꿔 한 번 더 그린다. 화면에는 같은 차트가 둘 남으므로 일어난 일만 적어야 한다.
    def test_folded_value_labels_do_not_invite_another_call(self) -> None:
        names = [
            "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
            "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
        ]
        quota = table(
            436, "지역별 지방공무원 정원", "명", ["지역", "정원"],
            [[name, str(1000 + index * 7)] for index, name in enumerate(names)],
        )
        population = table(
            98, "지역별 주민등록인구", "명", ["지역", "인구"],
            [[name, str(100000 + index * 900)] for index, name in enumerate(names)],
        )
        spec = build(
            [(quota, {"label": "정원"}), (population, {"label": "인구"})],
            query="주민 1만 명당 정원",
            derive={"op": "per_capita", "per": 10000},
        )
        spec["vega_lite"] = build_vega_lite_spec(spec)

        folded = [warning for warning in spec["warnings"] if "값 라벨이 서로 겹쳐" in warning]
        self.assertTrue(folded, spec["warnings"])
        self.assertNotIn("가로 막대로 요청", folded[0])
        self.assertNotIn("요청하면", folded[0])

    # 계열이 하나인 파생 지표에는 색 범례를 붙이지 않아야 한다.
    def test_rendered_chart_has_no_series_legend(self) -> None:
        spec = build_per_capita()
        spec["vega_lite"] = build_vega_lite_spec(spec)

        encoding = spec["vega_lite"]["encoding"]
        self.assertNotIn("color", encoding)
        self.assertEqual(encoding["x"]["sort"], ["강원", "서울", "경기"])
        self.assertEqual(encoding["y"]["title"], "명/1만 명")


if __name__ == "__main__":
    unittest.main()
