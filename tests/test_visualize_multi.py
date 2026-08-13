# -*- coding: utf-8 -*-
"""visualize가 서로 다른 통계표의 지표를 공통 항목으로 맞춰 그리는지 검증한다."""
import unittest

from app.tools.service.visualization.multi_table_spec_builder import build_multi_source_spec
from app.tools.service.visualization.vega_lite_renderer import build_vega_lite_spec


# 표 메타데이터의 공통 골격을 만든다.
def table(stat_id: int, title: str, unit: str, columns: list[str], rows: list[list[str]]) -> dict:
    return {
        "stat_id": stat_id,
        "ref_id": f"4-1-{stat_id}",
        "publication_year": 2025,
        "chapter_no": 4,
        "section_no": 1,
        "level3_no": stat_id,
        "level4_no": None,
        "chapter": "지방행정",
        "section": "지역",
        "level3_title": title,
        "level4_title": title,
        "title_ko": title,
        "title_en": title,
        "unit": unit,
        "base_date": "2024.12.31.",
        "page_start": 10,
        "table_seq": 1,
        "caption": "2024. 12. 31. 기준",
        "body": {"columns": columns, "records": [dict(zip(columns, row)) for row in rows]},
    }


POPULATION = table(
    91, "지역별 주민등록인구", "명",
    ["구분 Classification 지역 Region", "인 구 수 Population_계 Total"],
    [
        ["계 Total", "51,117,378"],
        ["서 울 Seoul", "9,299,548"],
        ["부 산 Busan", "3,241,600"],
        ["세 종 Sejong", "391,965"],
    ],
)
# 같은 지역을 정식 명칭으로 적고 행 순서도 다른 표.
DEBT = table(
    166, "지역별 지방자치단체 채무", "억원",
    ["지역", "계 Total"],
    [
        ["부산광역시", "33,640"],
        ["서울특별시", "115,695"],
        ["세종특별자치시", "4,927"],
        ["합계", "448,718"],
    ],
)
# 한 지역이 본청·시군구 두 행으로 나뉜 표.
FUND = table(
    252, "재난관리기금 적립 및 운용", "백만원",
    ["지역", "구분", "적립액"],
    [
        ["서 울 Seoul", "본청", "228,373"],
        ["서 울 Seoul", "시군구", "41,074"],
        ["부 산 Busan", "본청", "46,797"],
        ["부 산 Busan", "시군구", "12,182"],
    ],
)
DAMAGE_BY_YEAR = table(
    286, "연도별 자연재난 피해", "백만원",
    ["구분 연도 Year", "합 계 Total"],
    [["2020", "1,318,177"], ["2021", "66,054"], ["2022", "592,656"]],
)
HEAT_BY_YEAR = table(
    263, "연도별 폭염 인명피해", "명",
    ["연도", "합 계 Total"],
    [["2021", "1,376"], ["2022", "1,564"], ["2023", "2,818"]],
)
# 피해액과 단위·규모가 같아 한 축에 함께 올릴 수 있는 표.
RECOVERY_BY_YEAR = table(
    287, "연도별 자연재난 복구액", "백만원",
    ["연도", "합 계 Total"],
    [["2020", "2,914,027"], ["2021", "153,110"], ["2022", "1,281,392"]],
)
# 재난관리기금과 단위가 같아 나란히 견줄 수 있는 표.
DAMAGE_BY_REGION = table(
    285, "지역별 자연재난 피해", "백만원",
    ["지역", "재산피해"],
    [["서 울 Seoul", "1,204"], ["부 산 Busan", "3,517"]],
)
# 연도가 행인 표. 같은 주제를 다루는 아래 표와 행·열 방향이 서로 다르다.
QUOTA_BY_YEAR = table(
    433, "연도별 지방공무원 정원", "명",
    ["구 분 Classification 연도 Year", "지방공무원 정원 Number of Civil Servants"],
    [["2019", "345,992"], ["2020", "359,588"], ["2021", "372,446"]],
)
# 연도가 열인 표. 연도로 맞대려면 서버가 한 행을 골라 펴야 한다.
STAFF_BY_YEAR_COLUMNS = table(
    437, "연도별 지방공무원 현원", "명",
    ["연도 Year 구분 Classification", "2019", "2020", "2021"],
    [
        ["계 Total", "337,084", "292,182", "301,930"],
        ["시･도 Metropolitan City/Province", "104,442", "53,104", "54,593"],
    ],
)
# 단위 표기는 같은데 실제 수치가 천 배 가까이 큰 표(원본 단위 표기가 어긋난 경우).
INFLATED_DAMAGE = table(
    612, "지역별 자연재난 피해", "백만원",
    ["지역", "재산피해"],
    [["서 울 Seoul", "417,860,381"], ["부 산 Busan", "213,179,459"]],
)


# build_multi_source_spec 호출 인자를 간단히 구성한다.
def build(tables_and_requests: list[tuple[dict, dict]], **kwargs) -> dict:
    sources = [{"table": table_data, "request": request} for table_data, request in tables_and_requests]
    return build_multi_source_spec(sources, **kwargs)


class MultiSourceVisualizeTests(unittest.TestCase):
    # 표마다 지역 표기가 달라도 같은 지역으로 묶어 계열 두 개를 만들어야 한다.
    def test_joins_two_tables_on_region_despite_different_labels(self) -> None:
        spec = build(
            [(POPULATION, {"label": "인구"}), (DEBT, {"label": "채무"})],
            query="지역별 인구와 채무",
        )

        self.assertTrue(spec["ok"])
        # 명과 억원은 한 축에 못 올린다. 지역 축에는 흐름이 없으므로 지표마다 칸을 나눈다.
        self.assertEqual(spec["chart"]["type"], "paired_panels")
        self.assertEqual([item["label"] for item in spec["chart"]["series"]], ["인구", "채무"])
        # 합계·전국 행은 개별 지역과 중복되므로 축에서 빠진다.
        self.assertEqual(
            [row["항목"] for row in spec["data"]["joined_rows"]], ["서울", "부산", "세종"],
        )
        self.assertEqual(
            spec["data"]["joined_rows"][0], {"항목": "서울", "인구": 9299548.0, "채무": 115695.0},
        )
        # 첫 표의 행 순서가 곧 축 순서다(Vega-Lite 기본 가나다순 정렬에 밀리지 않도록 명시한다).
        self.assertEqual(spec["chart"]["category_order"], ["서울", "부산", "세종"])
        panels = build_vega_lite_spec(spec)["vconcat"]
        self.assertEqual(panels[0]["encoding"]["x"]["sort"], ["서울", "부산", "세종"])

    # 두 표의 값을 x축과 y축으로 짝지어 산점도를 만들어야 한다.
    def test_scatter_pairs_two_tables_into_x_and_y(self) -> None:
        spec = build(
            [(POPULATION, {"label": "인구"}), (DEBT, {"label": "채무"})],
            query="지역별 인구와 채무의 관계",
            chart_type="scatter",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "scatter")
        self.assertEqual(spec["chart"]["x_title"], "인구 (명)")
        self.assertEqual(spec["chart"]["y_title"], "채무 (억원)")
        self.assertEqual(
            spec["data"]["records"][0],
            {"x": 9299548.0, "value": 115695.0, "series": None, "label": "서울", "point_label": "서울"},
        )
        self.assertEqual(vega_lite["encoding"]["x"]["field"], "x")
        self.assertEqual(vega_lite["encoding"]["y"]["field"], "value")
        self.assertEqual(vega_lite["layer"][1]["encoding"]["text"]["field"], "point_label")

    # 질의가 관계를 물으면 차트 타입을 지정하지 않아도 산점도를 골라야 한다.
    def test_relation_query_selects_scatter_without_chart_type(self) -> None:
        spec = build(
            [(POPULATION, {"label": "인구"}), (DEBT, {"label": "채무"})],
            query="지역별 인구와 채무의 상관관계를 보여줘",
        )

        self.assertEqual(spec["chart"]["type"], "scatter")

    # 단위가 다른 두 계열은 값 축을 좌우로 나눠야 작은 계열이 보인다.
    def test_different_units_split_value_axis(self) -> None:
        spec = build(
            [(POPULATION, {"label": "인구"}), (DEBT, {"label": "채무"})],
            query="지역별 인구와 채무를 함께",
            chart_type="bar",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertTrue(spec["chart"]["dual_axis"])
        first, second = vega_lite["vconcat"]
        self.assertEqual(first["transform"][0]["filter"], {"field": "series", "oneOf": ["인구"]})
        self.assertEqual(first["encoding"]["y"]["title"], "인구 (명)")
        self.assertEqual(second["encoding"]["y"]["title"], "채무 (억원)")
        # 지역 축에는 흐름이 없으므로 어느 칸도 선으로 잇지 않는다.
        self.assertEqual(first["layer"][0]["mark"]["type"], "bar")
        self.assertEqual(second["layer"][0]["mark"]["type"], "bar")
        # 항목 이름은 맨 아래 칸에만 적어 위 칸의 눈금이 아래 칸 막대와 붙지 않게 한다.
        self.assertFalse(first["encoding"]["x"]["axis"]["labels"])
        self.assertNotIn("axis", second["encoding"]["x"])
        # 두 칸이 같은 항목 순서를 써야 위아래로 견줄 수 있다.
        self.assertEqual(first["encoding"]["x"]["sort"], second["encoding"]["x"]["sort"])

    # 단위가 같고 크기도 비슷하면 한 축에 나란히 그린다.
    def test_same_unit_keeps_single_value_axis(self) -> None:
        spec = build(
            [(FUND, {"label": "적립액"}), (FUND, {"label": "적립액2"})],
            query="지역별 재난관리기금",
        )

        self.assertFalse(spec["chart"]["dual_axis"])
        self.assertEqual(spec["chart"]["unit"], "백만원")

    # 한 지역이 여러 행으로 나뉜 표는 합계로 모아야 한다.
    def test_repeated_keys_are_summed(self) -> None:
        spec = build(
            [(FUND, {"label": "적립액"}), (POPULATION, {"label": "인구"})],
            query="지역별 재난관리기금 적립액과 인구",
        )

        # 본청·시군구 두 행이 한 지역 값으로 합쳐지고, 한쪽 표에만 있는 세종은 빈 값으로 남는다.
        self.assertEqual(
            {row["항목"]: row["적립액"] for row in spec["data"]["joined_rows"]},
            {"서울": 269447.0, "부산": 58979.0, "세종": None},
        )
        self.assertIn(
            "[적립액] 한 항목이 여러 행에 나뉘어 있어 합계로 집계했습니다.", spec["warnings"],
        )

    # 연도가 공통 항목이면 연도순으로 겹치고 한쪽에만 있는 연도도 남긴다.
    def test_year_key_sorts_by_year_and_keeps_gaps(self) -> None:
        spec = build(
            [(DAMAGE_BY_YEAR, {"label": "피해액"}), (HEAT_BY_YEAR, {"label": "인명피해"})],
            query="연도별 자연재난 피해액과 폭염 인명피해",
        )

        # 백만원과 명은 축을 나눠야 해서 막대+선 콤보가 된다.
        self.assertEqual(spec["chart"]["type"], "combo")
        self.assertTrue(spec["chart"]["dual_axis"])
        self.assertEqual(spec["chart"]["x"], "year")
        self.assertIsNone(spec["chart"]["category_order"])
        self.assertEqual([row["항목"] for row in spec["data"]["joined_rows"]], [2020, 2021, 2022, 2023])
        self.assertIsNone(spec["data"]["joined_rows"][0]["인명피해"])
        self.assertTrue(
            any("일부 표에만 있는 항목" in warning for warning in spec["warnings"]),
        )

    # 연도 컬럼에 연도가 아닌 라벨이 섞여 있어도 연도순 정렬이 깨지지 않아야 한다.
    def test_non_year_label_in_year_column_is_placed_last(self) -> None:
        mixed = table(
            999, "연도별 기타 피해", "명",
            ["연도 Year", "합 계 Total"],
            [["2021", "10"], ["2022", "20"], ["기타", "30"]],
        )
        spec = build(
            [(DAMAGE_BY_YEAR, {"label": "피해액"}), (mixed, {"label": "기타"})],
            query="연도별 피해",
        )

        self.assertEqual(
            [row["항목"] for row in spec["data"]["joined_rows"]], [2020, 2021, 2022, "기타"],
        )

    # 값 기준 정렬은 첫 계열의 값 순서로 축을 다시 세워야 한다.
    def test_sort_order_follows_first_series_values(self) -> None:
        spec = build(
            [(DEBT, {"label": "채무"}), (POPULATION, {"label": "인구"})],
            query="지역별 채무",
            sort_order="descending",
        )

        self.assertEqual(
            spec["chart"]["category_order"], ["서울특별시", "부산광역시", "세종특별자치시"],
        )
        self.assertEqual(
            [row["채무"] for row in spec["data"]["joined_rows"]], [115695.0, 33640.0, 4927.0],
        )

    # 지정한 값 컬럼과 단위를 그대로 사용해야 한다.
    def test_requested_value_column_and_unit_are_used(self) -> None:
        spec = build(
            [
                (FUND, {"label": "적립액", "value": "적립액", "unit": "백만원"}),
                (POPULATION, {"label": "인구", "value": "인 구 수 Population_계 Total"}),
            ],
            query="지역별 재난관리기금 적립액과 인구",
        )

        self.assertEqual(
            [(item["value_column"], item["unit"]) for item in spec["sources"]],
            [("적립액", "백만원"), ("인 구 수 Population_계 Total", "명")],
        )

    # 맞출 공통 항목이 없으면 차트를 만들지 않고 이유를 알려야 한다.
    def test_missing_common_key_reports_reason_without_chart(self) -> None:
        spec = build(
            [(POPULATION, {"label": "인구"}), (HEAT_BY_YEAR, {"label": "인명피해"})],
            query="인구와 폭염 인명피해",
        )

        self.assertTrue(spec["ok"])
        self.assertEqual(spec["chart"]["type"], "table")
        self.assertIn("공통", spec["chart"]["reason"])
        self.assertIsNone(build_vega_lite_spec(spec))

    # 단위와 규모가 같은 두 지표는 축을 나누지 않고 막대를 나란히 놓아야 크기를 바로 견줄 수 있다.
    def test_same_unit_region_values_use_grouped_bars(self) -> None:
        spec = build(
            [(FUND, {"label": "재난관리기금 적립액"}), (DAMAGE_BY_REGION, {"label": "자연재난 피해액"})],
            query="재난관리기금 적립액과 자연재난 피해액을 한 그래프에 표시해줘",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "grouped_bar")
        self.assertFalse(spec["chart"]["dual_axis"])
        self.assertEqual(spec["chart"]["unit"], "백만원")
        # 같은 축을 쓰므로 계열을 옆으로 밀어 막대를 짝지어 세운다.
        self.assertEqual(
            vega_lite["encoding"]["xOffset"]["sort"],
            ["재난관리기금 적립액", "자연재난 피해액"],
        )
        # 축을 나누면 눈금이 갈려 높이를 그대로 견줄 수 없으므로, 대신 규모 차이를 알린다.
        self.assertTrue(any("규모 차이가 커서" in warning for warning in spec["warnings"]))

    # 단위가 같아도 규모가 백 배를 넘으면 작은 쪽이 아예 보이지 않아 축을 나눠야 한다.
    def test_same_unit_but_huge_scale_gap_splits_the_axis(self) -> None:
        spec = build(
            [(FUND, {"label": "적립액"}), (INFLATED_DAMAGE, {"label": "피해액"})],
            query="지역별 재난관리기금 적립액과 자연재난 피해액을 한 그래프에",
        )

        self.assertEqual(spec["chart"]["type"], "paired_panels")
        self.assertTrue(spec["chart"]["dual_axis"])
        # 눈금이 갈렸다는 사실과, 그 원인이 단위 표기일 수 있다는 점을 함께 알린다.
        self.assertTrue(any("눈금이 서로 다르므로" in warning for warning in spec["warnings"]))
        self.assertTrue(any("단위가 실제 수치와 맞는지" in warning for warning in spec["warnings"]))

    # 단위와 규모가 같은 연도 지표는 축을 나누지 않고 선그래프로 겹쳐야 한다.
    def test_same_unit_year_values_stay_a_line_chart(self) -> None:
        spec = build(
            [(DAMAGE_BY_YEAR, {"label": "피해액"}), (RECOVERY_BY_YEAR, {"label": "복구액"})],
            query="연도별 자연재난 피해액과 복구액",
        )

        self.assertEqual(spec["chart"]["type"], "line")
        self.assertFalse(spec["chart"]["dual_axis"])

    # 격차를 묻는 요청은 두 값을 이어 벌어진 폭을 보여주는 아령 차트여야 한다.
    def test_gap_query_selects_dumbbell(self) -> None:
        spec = build(
            [(FUND, {"label": "적립액"}), (DAMAGE_BY_REGION, {"label": "피해액"})],
            query="지역별 재난관리기금 적립액과 피해액의 격차",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "dumbbell")
        connector, points = vega_lite["layer"][0], vega_lite["layer"][1]
        self.assertEqual(connector["encoding"]["y"]["aggregate"], "min")
        self.assertEqual(connector["encoding"]["y2"]["aggregate"], "max")
        self.assertEqual(points["mark"]["type"], "point")

    # 지역처럼 순서가 없는 축을 선으로 이으면 없는 추세가 보이므로 막대로 바꿔야 한다.
    def test_line_request_on_region_axis_falls_back_to_bars(self) -> None:
        spec = build(
            [(FUND, {"label": "적립액"}), (DAMAGE_BY_REGION, {"label": "피해액"})],
            query="지역별 재난관리기금 적립액과 피해액",
            chart_type="line",
        )

        self.assertEqual(spec["chart"]["type"], "grouped_bar")
        self.assertTrue(any("순서가 있는 축" in warning for warning in spec["warnings"]))

    # 여러 표를 그릴 때도 출처를 표마다 모두 남겨야 한다.
    def test_response_lists_every_source_table(self) -> None:
        spec = build(
            [(POPULATION, {"label": "인구"}), (DEBT, {"label": "채무"})],
            query="지역별 인구와 채무",
        )

        self.assertEqual([stat["stat_id"] for stat in spec["stats"]], [91, 166])
        self.assertEqual(
            [(source["title_ko"], source["unit"]) for source in spec["sources"]],
            [("지역별 주민등록인구", "명"), ("지역별 지방자치단체 채무", "억원")],
        )

    # 연도가 행인 표와 열인 표를 맞댈 때, 열이 연도인 쪽을 펴서 연도로 이어야 한다.
    def test_joins_row_years_with_column_years(self) -> None:
        spec = build(
            [(QUOTA_BY_YEAR, {"label": "정원"}), (STAFF_BY_YEAR_COLUMNS, {"label": "현원"})],
            query="연도별 지방공무원 정원 대비 현원 격차",
        )

        self.assertTrue(spec["ok"])
        self.assertEqual(
            spec["data"]["joined_rows"],
            [
                {"항목": 2019, "정원": 345992.0, "현원": 337084.0},
                {"항목": 2020, "정원": 359588.0, "현원": 292182.0},
                {"항목": 2021, "정원": 372446.0, "현원": 301930.0},
            ],
        )
        # 어느 행을 폈는지 밝혀야 사용자가 시･도 행이 아님을 알 수 있다.
        self.assertTrue(any("'계' 행" in warning for warning in spec["warnings"]))

    # 열이 연도인 표에서 행을 직접 고르면 그 행을 편다.
    def test_column_year_table_flattens_the_filtered_row(self) -> None:
        spec = build(
            [
                (QUOTA_BY_YEAR, {"label": "정원"}),
                (STAFF_BY_YEAR_COLUMNS, {
                    "label": "시도 현원",
                    "filters": [{"column": "구분", "value": "시･도"}],
                }),
            ],
            query="연도별 지방공무원 정원과 시도 현원",
        )

        self.assertEqual(
            [row["시도 현원"] for row in spec["data"]["joined_rows"]],
            [104442.0, 53104.0, 54593.0],
        )


if __name__ == "__main__":
    unittest.main()
