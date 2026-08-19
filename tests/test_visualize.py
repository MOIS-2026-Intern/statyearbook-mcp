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
MIXED_UNIT_COLUMNS = ["연도 Year", "전체 이용건수 Total", "온라인 이용건수 Online", "이용률 Ratio"]
# 건수와 비율처럼 단위가 갈리는 지표가 한 표에 같이 있는 모양.
MIXED_UNIT_TABLE = {
    **TABLE,
    "title_ko": "온라인 민원 이용률",
    "unit": "천건, %",
    "body": body(MIXED_UNIT_COLUMNS, [
        ["2023", "1,322,590", "1,058,072", "80.0"],
        ["2024", "1,481,307", "1,239,853", "83.7"],
        ["2025", "1,565,834", "1,326,261", "84.7"],
    ]),
}
LONG_CATEGORY_COLUMNS = [
    "연도 Year",
    "구분 Classification",
    "데이터셋 다운로드 건수 No. of Downloaded Data Sets",
    "합계 Total",
]
# 연도와 구분이 각각 열로 있어, 한 구분만 남기면 그 열의 값이 하나로 좁혀지는 모양.
LONG_CATEGORY_TABLE = {
    **TABLE,
    "title_ko": "공공데이터 민간활용 실적",
    "unit": "누적 건",
    "body": body(LONG_CATEGORY_COLUMNS, [
        ["2023", "중앙행정기관 Central Government", "11,679,293", "15,334,703"],
        ["2023", "지방자치단체 Local Government", "21,882,057", "22,451,089"],
        ["2024", "중앙행정기관 Central Government", "13,839,843", "17,775,028"],
        ["2024", "지방자치단체 Local Government", "27,277,404", "27,999,097"],
        ["2025", "중앙행정기관 Central Government", "17,593,345", "21,972,130"],
        ["2025", "지방자치단체 Local Government", "33,471,339", "34,369,546"],
    ]),
}
FLAT_CATEGORY_COLUMNS = ["구분 Classification", "합계 Total"]
# 남은 행을 가를 컬럼이 구분 하나뿐이라, 그 구분을 좁히면 축으로 쓸 컬럼이 남지 않는 모양.
FLAT_CATEGORY_TABLE = {
    **TABLE,
    "title_ko": "기관별 활용 실적",
    "unit": "건",
    "body": body(FLAT_CATEGORY_COLUMNS, [
        ["중앙행정기관 Central Government", "10"],
        ["중앙행정기관 Central Government", "20"],
        ["지방자치단체 Local Government", "30"],
    ]),
}
GRADE_COLUMNS = [
    "구분 Classification 기관 Organization",
    "계 Total",
    "행 정 부 Executive Branch_국가 State",
    "행 정 부 Executive Branch_지방 Local",
]
# 급수 행과 직종 행이 한 표에 섞여 있고, 행 라벨의 띄어쓰기가 들쭉날쭉한 모양.
GRADE_TABLE = {
    **TABLE,
    "title_ko": "계급별 공무원 정원",
    "body": body(GRADE_COLUMNS, [
        ["계 Total", "1,175,295", "753,689", "395,690"],
        ["고위공무원 Senior Civil Servants", "1,195", "1,195", "-"],
        ["1급 Grade 1", "14", "-", "11"],
        ["1･2급 Grade 1･2", "14", "-", "4"],
        ["2 급 Grade 2", "90", "-", "45"],
        ["3 급 Grade 3", "683", "-", "605"],
        ["경 찰 직 Police Service", "143,666", "143,503", "163"],
        ["교 육 직 Education Service", "371,962", "362,982", "8,980"],
    ]),
}
FAMILY_COLUMNS = [
    "연도 Year 구분 Classification",
    "전체 Total",
    "성별 Sex_남성 Men",
    "성별 Sex_여성 Women",
    "연령별 Age_20대 20s",
    "연령별 Age_60~74세 Aged 60~74",
]
# 상위 헤더가 성별과 연령별로 갈리는 모양. 한쪽 헤더만 그려 달라는 요청이 흔하다.
FAMILY_TABLE = {
    **TABLE,
    "title_ko": "전자정부서비스 인지도",
    "unit": "%",
    "body": body(FAMILY_COLUMNS, [
        ["2024", "98.5", "98.9", "98.0", "99.9", "96.1"],
        ["2025", "99.2", "99.5", "98.9", "99.9", "97.9"],
    ]),
}
WIDE_METRIC_COLUMNS = ["연도 Year 구분 Classification", "2023", "2024", "2025"]
# 행이 지표, 열이 연도인 모양. 지표마다 단위가 달라 한 축에 겹칠 수 없다.
WIDE_METRIC_TABLE = {
    **TABLE,
    "title_ko": "여성 지방공무원",
    "unit": "명, %",
    "body": body(WIDE_METRIC_COLUMNS, [
        ["전 체 Total", "313,296", "315,205", "313,924"],
        ["여 성 Female", "157,935", "161,710", "163,328"],
        ["여성비율 Female Percent(%)", "50.4", "51.3", "52"],
    ]),
}
SHORT_YEAR_COLUMNS = ["구 분", "'09", "'10", "'11", "'12", "'13", "'14", "'15", "'16"]
# 주요통계집에서 가장 흔한 모양: 행이 지표, 열이 두 자리로 줄여 적은 연도.
SHORT_YEAR_TABLE = {
    **TABLE,
    "title_ko": "전자정부서비스 이용실태조사 결과",
    "unit": "%",
    "body": body(SHORT_YEAR_COLUMNS, [
        ["인지도", "92.5", "92.6", "92.4", "81.9", "80.0", "86.0", "89.0", "90.4"],
        ["이용률", "60.2", "60.0", "63.5", "51.2", "56.9", "72.5", "76.7", "85.8"],
        ["만족도", "67.9", "74.0", "82.6", "91.2", "83.7", "85.6", "93.5", "95.8"],
    ]),
}
WRAPPED_YEAR_COLUMNS = ["구 분", "'17", "'18", "'19", "'20"]
# 지면 폭에 안 맞아 뒷부분을 아래로 내려 붙이고 머리글을 한 번 더 적은 모양.
WRAPPED_YEAR_TABLE = {
    **TABLE,
    "title_ko": "전자정부서비스 이용실태조사 결과",
    "unit": "%",
    "body": body(WRAPPED_YEAR_COLUMNS, [
        ["인지도", "90.7", "92.5", "93.8", "95.7"],
        ["이용률", "86.7", "87.5", "87.6", "88.9"],
        ["구 분", "'13", "'14", "'15", "'16"],
        ["인지도", "80.0", "86.0", "89.0", "90.4"],
        ["이용률", "56.9", "72.5", "76.7", "85.8"],
    ]),
}
# 첫 행이 머리글과 같은 표는 머리글을 덜 읽은 것이지 이어붙인 표가 아니다.
UNCONSUMED_HEADER_TABLE = {
    **TABLE,
    "title_ko": "정부부문 채무",
    "unit": "조원",
    "body": body(["구 분", "'22년", "'23년"], [
        ["구 분", "규모", "규모"],
        ["국가채무", "1,067.4", "1,126.8"],
        ["일반정부 부채", "1,157.2", "1,217.3"],
    ]),
}
TWO_COLUMN_YEAR_COLUMNS = ["시도 Region", "'23", "'24"]
# 연도가 둘뿐이라 지역끼리 견주는 편이 나은 모양.
TWO_COLUMN_YEAR_TABLE = {
    **TABLE,
    "title_ko": "시도별 지방세",
    "unit": "억원",
    "body": body(TWO_COLUMN_YEAR_COLUMNS, [
        ["서울", "2,410", "2,520"],
        ["부산", "830", "870"],
        ["대구", "610", "640"],
    ]),
}
YEAR_METRIC_COLUMNS = [
    "국가명 Country",
    "'20_순위 Ranking",
    "'20_지수 Index",
    "'22_순위 Ranking",
    "'22_지수 Index",
    "'24_순위 Ranking",
    "'24_지수 Index",
]
# 연도 아래에 지표가 되풀이되는 다단 헤더 모양.
YEAR_METRIC_TABLE = {
    **TABLE,
    "title_ko": "전자정부 발전지수",
    "unit": None,
    "body": body(YEAR_METRIC_COLUMNS, [
        ["대한민국", "2", "0.956", "3", "0.949", "1", "0.976"],
        ["덴마크", "1", "0.975", "1", "0.977", "2", "0.974"],
        ["일본", "14", "0.898", "14", "0.902", "13", "0.910"],
    ]),
}
BUDGET_YEAR_COLUMNS = ["구 분", "'24년 본예산 (A)", "'25년 본예산 (B)", "증감 (B-A)"]
# 열 이름이 연도로 시작하지만 실은 시점이 아니라 지표인 모양.
BUDGET_YEAR_TABLE = {
    **TABLE,
    "title_ko": "지방자치단체 예산",
    "unit": "억원",
    "body": body(BUDGET_YEAR_COLUMNS, [
        ["일반회계", "2,850", "2,970", "120"],
        ["특별회계", "305", "304", "-1"],
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
        # 축 라벨은 영문 병기를 뗀 한국어 부분만 남는다.
        self.assertEqual(
            {record["x"]: record["value"] for record in spec["data"]["records"]},
            {"1급": 1.0, "2급": 9.0, "3급": 90.0},
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

    # 한 표에서 뽑은 지표라도 단위가 갈리면 축을 나눠야 작은 단위 지표가 바닥에 눌리지 않는다.
    def test_mixed_unit_metrics_split_the_value_axis(self) -> None:
        spec = build_plot_spec(
            MIXED_UNIT_TABLE, "연도별 온라인 민원 이용건수와 이용률 추이", "auto",
            None, None, None, None, "auto",
            metrics=[
                {"column": "온라인 이용건수 Online", "label": "이용건수"},
                {"column": "이용률 Ratio", "label": "이용률"},
            ],
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "combo")
        self.assertTrue(spec["chart"]["dual_axis"])
        self.assertEqual(vega_lite["resolve"], {"scale": {"y": "independent"}})
        first, second = vega_lite["layer"]
        self.assertEqual(first["encoding"]["y"]["title"], "이용건수 (천건)")
        self.assertEqual(first["encoding"]["y"]["axis"]["orient"], "left")
        self.assertEqual(second["encoding"]["y"]["title"], "이용률 (%)")
        self.assertEqual(second["encoding"]["y"]["axis"]["orient"], "right")

    # 같은 단위 지표는 한 축에 모으고, 단위가 다른 지표만 반대쪽 축으로 보낸다.
    def test_same_unit_metrics_share_one_axis_of_the_combo(self) -> None:
        spec = build_plot_spec(
            MIXED_UNIT_TABLE, "연도별 민원 이용건수와 이용률", "auto",
            None, None, None, None, "auto",
            metrics=[
                {"column": "전체 이용건수 Total", "label": "전체"},
                {"column": "온라인 이용건수 Online", "label": "온라인"},
                {"column": "이용률 Ratio", "label": "이용률"},
            ],
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(spec["chart"]["type"], "combo")
        counts, ratio = vega_lite["layer"]
        self.assertEqual(counts["transform"][0]["filter"]["oneOf"], ["전체", "온라인"])
        # 한 축을 나눠 쓰는 막대는 서로 겹치지 않게 옆으로 민다.
        self.assertEqual(counts["layer"][0]["encoding"]["xOffset"]["sort"], ["전체", "온라인"])
        self.assertEqual(counts["encoding"]["y"]["title"], "천건")
        self.assertEqual(ratio["transform"][0]["filter"]["oneOf"], ["이용률"])

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

    # 선은 시간의 흐름을 나타내는 mark다. 지역처럼 순서 없는 축에서는 막대를 나란히 놓아야 한다.
    def test_combo_on_category_axis_becomes_grouped_bar(self) -> None:
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

        self.assertEqual(spec["chart"]["type"], "grouped_bar")
        self.assertIn("선이 흐름처럼 잘못 읽히므로", spec["chart"]["reason"])
        # 단위도 규모도 같은 두 계열이라 축을 나누지 않고 한 축에 나란히 둔다.
        self.assertFalse(spec["chart"]["dual_axis"])
        self.assertNotIn("resolve", vega_lite)
        self.assertNotIn("vconcat", vega_lite)

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


# 표에서 요청한 행·열만 골라 그리는 경로를 검증한다.
class SubsetSelectionTests(unittest.TestCase):
    # 급수 행만 그려 달라는 요청은 같은 컬럼의 여러 조건을 OR로 묶어 직종 행을 빼야 한다.
    def test_row_subset_keeps_only_requested_rows(self) -> None:
        spec = build_plot_spec(
            GRADE_TABLE, "공무원 정원을 급수별로", "auto", None, None, None, None, "exclude",
            filters=[{"column": "구분", "value": f"{n}급"} for n in (1, 2, 3)],
            metrics=[{"column": "계", "label": "정원"}],
        )

        # 라벨 띄어쓰기가 달라도 급수 행만 남고, '1･2급'처럼 다른 행은 섞이지 않는다.
        self.assertEqual(
            [record["x"] for record in spec["data"]["records"]], ["1급", "2급", "3급"],
        )
        self.assertEqual([record["value"] for record in spec["data"]["records"]], [14.0, 90.0, 683.0])
        self.assertEqual(spec["warnings"], [])

    # 표에 없는 값이 섞여도 확인된 행은 그리고, 빠진 값은 경고로 알려야 한다.
    def test_row_subset_keeps_verified_rows_and_warns_on_the_rest(self) -> None:
        spec = build_plot_spec(
            GRADE_TABLE, "급수별 정원", "auto", None, None, None, None, "exclude",
            filters=[{"column": "구분", "value": value} for value in ("1급", "2급", "10급")],
            metrics=[{"column": "계", "label": "정원"}],
        )

        self.assertEqual([record["x"] for record in spec["data"]["records"]], ["1급", "2급"])
        self.assertTrue(any("'10급'" in warning for warning in spec["warnings"]))

    # 어느 조건도 맞지 않으면 표 전체로 대체하지 않고 차트를 만들지 않아야 한다.
    def test_row_subset_without_any_match_draws_nothing(self) -> None:
        spec = build_plot_spec(
            GRADE_TABLE, "급수별 정원", "auto", None, None, None, None, "exclude",
            filters=[{"column": "구분", "value": "10급"}],
            metrics=[{"column": "계", "label": "정원"}],
        )

        self.assertEqual(spec["chart"]["type"], "table")
        self.assertEqual(spec["data"]["records"], [])

    # 조건 컬럼 자체를 표에서 찾지 못해도 표 전체로 되돌아가면 안 된다.
    def test_row_subset_with_unknown_column_draws_nothing(self) -> None:
        spec = build_plot_spec(
            GRADE_TABLE, "지역별 정원", "auto", None, None, None, None, "exclude",
            filters=[{"column": "지역", "value": "서울"}],
            metrics=[{"column": "계", "label": "정원"}],
        )

        self.assertEqual(spec["data"]["records"], [])
        self.assertTrue(any("'지역'" in warning for warning in spec["warnings"]))

    # 영문 병기를 뗀 짧은 컬럼명으로도 그릴 열을 고를 수 있어야 한다.
    def test_metric_columns_resolve_from_short_names(self) -> None:
        spec = build_plot_spec(
            GRADE_TABLE, "급수별 국가·지방 정원", "auto", None, None, None, None, "exclude",
            filters=[{"column": "구분", "value": f"{n}급"} for n in (2, 3)],
            metrics=[
                {"column": "행정부_국가", "label": "국가"},
                {"column": "행정부_지방", "label": "지방"},
            ],
        )

        self.assertEqual(spec["chart"]["type"], "grouped_bar")
        self.assertEqual(
            [(record["x"], record["series"], record["value"]) for record in spec["data"]["records"]],
            [("2급", "지방", 45.0), ("3급", "지방", 605.0)],
        )

    # '성별 말고 연령대별로'는 그 상위 헤더에 속한 컬럼만 남겨야 한다.
    def test_column_family_keeps_only_that_header(self) -> None:
        spec = build_plot_spec(
            FAMILY_TABLE, "연령대별 인지도", "heatmap", None, None, None, None, "exclude",
            column_family_name="연령별",
        )

        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}),
            ["20대", "60~74세"],
        )

    # 행이 지표, 열이 연도인 표에서 두 행을 고르면 연도가 x축, 고른 행이 계열이어야 한다.
    def test_wide_year_rows_become_series_over_years(self) -> None:
        spec = build_plot_spec(
            WIDE_METRIC_TABLE, "여성 지방공무원 수와 비율의 추이를 함께", "auto",
            None, None, None, None, "exclude",
            filters=[
                {"column": "구분", "value": "여성"},
                {"column": "구분", "value": "여성비율"},
            ],
        )

        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual([record["x"] for record in spec["data"]["records"][:2]], [2023, 2023])
        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}),
            ["여성", "여성비율"],
        )
        # 명과 %가 섞여 있으므로 값 축을 좌우로 나눈 콤보가 되어야 한다.
        self.assertEqual(spec["chart"]["type"], "combo")
        self.assertTrue(spec["chart"]["dual_axis"])

    # 연도 컬럼을 metrics로 받아도 연도는 계열이 아니라 x축이어야 한다.
    def test_year_columns_as_metrics_do_not_flip_axes(self) -> None:
        spec = build_plot_spec(
            WIDE_METRIC_TABLE, "여성 지방공무원 수와 비율의 추이를 함께", "combo",
            None, None, None, None, "exclude",
            filters=[
                {"column": "구분", "value": "여성"},
                {"column": "구분", "value": "여성비율"},
            ],
            metrics=[{"column": year} for year in ("2023", "2024", "2025")],
        )

        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}),
            ["여성", "여성비율"],
        )

    # 연도 컬럼 하나만 고른 요청은 그 해의 지표 비교이므로 지표가 x축이어야 한다.
    def test_single_year_column_stays_a_metric_comparison(self) -> None:
        spec = build_plot_spec(
            WIDE_METRIC_TABLE, "2025년 여성 지방공무원 수", "auto",
            None, None, None, None, "exclude",
            filters=[
                {"column": "구분", "value": "여성"},
                {"column": "구분", "value": "여성비율"},
            ],
            metrics=[{"column": "2025"}],
        )

        self.assertEqual(
            [record["x"] for record in spec["data"]["records"]], ["여성", "여성비율"],
        )

    # 주요통계집은 연도를 "'09"처럼 두 자리로 줄여 적는다. 이 표기도 연도 축으로 읽어야 한다.
    def test_short_year_columns_become_the_time_axis(self) -> None:
        spec = build_plot_spec(
            SHORT_YEAR_TABLE, "전자정부서비스 이용실태조사 결과를 연도별 추이로", "auto",
            None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["type"], "line")
        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual(spec["chart"]["group"], "구 분")
        self.assertEqual(
            sorted({record["x"] for record in spec["data"]["records"]}),
            [2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016],
        )
        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}),
            ["만족도", "이용률", "인지도"],
        )

    # 연도를 범례에 두면 시점 사이의 흐름이 사라진다. 행을 고르지 않아도 축을 펴야 한다.
    def test_year_columns_never_become_the_legend(self) -> None:
        spec = build_plot_spec(
            SHORT_YEAR_TABLE, "전자정부서비스 이용실태조사 결과", "auto",
            None, None, None, None, "auto",
        )
        vega_lite = build_vega_lite_spec(spec)

        self.assertEqual(vega_lite["encoding"]["color"]["scale"]["domain"], ["인지도", "이용률", "만족도"])
        self.assertEqual(
            vega_lite["encoding"]["x"]["sort"],
            [2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016],
        )

    # 클라이언트가 구분 컬럼을 x로 지정해 와도 연도가 열인 표에서는 구분이 범례가 되어야 한다.
    def test_requested_category_x_moves_to_the_legend(self) -> None:
        spec = build_plot_spec(
            SHORT_YEAR_TABLE, "전자정부서비스 이용실태조사 결과 추이", "grouped_bar",
            "구 분", None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual(spec["chart"]["group"], "구 분")

    # 시점이 둘뿐인 표는 연도를 범례에 두고 지역끼리 견주는 편이 나아 그대로 둔다.
    def test_two_year_columns_stay_a_category_comparison(self) -> None:
        spec = build_plot_spec(
            TWO_COLUMN_YEAR_TABLE, "시도별 지방세", "auto", None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["x"], "시도 Region")
        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}), ["'23", "'24"],
        )

    # 시점이 둘뿐이어도 추이를 물으면 연도를 축으로 편다.
    def test_two_year_columns_flip_when_a_trend_is_asked(self) -> None:
        spec = build_plot_spec(
            TWO_COLUMN_YEAR_TABLE, "시도별 지방세 연도별 추이", "auto",
            None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}), ["대구", "부산", "서울"],
        )

    # 합계 행을 다른 행과 같은 축에 두면 혼자 솟아 나머지 선을 바닥에 눌러 버린다.
    def test_total_row_is_left_out_of_the_year_axis_series(self) -> None:
        spec = build_plot_spec(
            WIDE_YEAR_TABLE, "지역별 인구 연도별 추이", "auto", None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}), ["대구", "부산", "서울"],
        )

    # 연도마다 같은 지표가 되풀이되는 다단 헤더는 지표 하나를 골라 연도 축을 세운다.
    def test_year_keyed_column_families_pick_one_metric(self) -> None:
        spec = build_plot_spec(
            YEAR_METRIC_TABLE, "전자정부 발전지수 순위 연도별 추이", "auto",
            None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual(sorted({record["x"] for record in spec["data"]["records"]}), [2020, 2022, 2024])
        self.assertEqual(
            sorted({record["series"] for record in spec["data"]["records"]}),
            ["대한민국", "덴마크", "일본"],
        )
        # 어느 지표를 그렸는지 알려야 나머지 지표를 따로 물을 수 있다.
        self.assertTrue(any("순위" in warning for warning in spec["warnings"]))

    # 연도로 시작해도 뒤에 지표 이름이 붙은 열은 시점이 아니라 지표다.
    def test_year_prefixed_metric_columns_are_not_a_time_axis(self) -> None:
        spec = build_plot_spec(
            BUDGET_YEAR_TABLE, "지방자치단체 예산 연도별 추이", "auto",
            None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["x"], "구 분")
        self.assertNotEqual(spec["chart"]["x"], "year")

    # 내려 붙인 뒷부분을 그대로 읽으면 '13년 값이 '17년 자리에 찍혀 한 해에 점이 둘씩 생긴다.
    def test_wrapped_table_blocks_are_folded_back_into_columns(self) -> None:
        spec = build_plot_spec(
            WRAPPED_YEAR_TABLE, "전자정부서비스 이용실태조사 결과 연도별 추이", "auto",
            None, None, None, None, "auto",
        )

        self.assertEqual(spec["chart"]["x"], "year")
        self.assertEqual(
            sorted({record["x"] for record in spec["data"]["records"]}),
            [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020],
        )
        # 계열마다 연도 하나에 점 하나여야 선이 톱니처럼 오르내리지 않는다.
        awareness = [
            (record["x"], record["value"])
            for record in spec["data"]["records"] if record["series"] == "인지도"
        ]
        self.assertEqual(
            awareness,
            [(2013, 80.0), (2014, 86.0), (2015, 89.0), (2016, 90.4),
             (2017, 90.7), (2018, 92.5), (2019, 93.8), (2020, 95.7)],
        )

    # 첫 행이 머리글과 같은 표는 열을 늘리지 말고 그대로 둬야 한다.
    def test_unconsumed_header_row_is_not_folded(self) -> None:
        spec = build_plot_spec(
            UNCONSUMED_HEADER_TABLE, "정부부문 채무 연도별 추이", "auto",
            None, None, None, None, "auto",
        )

        self.assertEqual(
            sorted({record["x"] for record in spec["data"]["records"]}), [2022, 2023],
        )

    # 상위 헤더 이름이 표에 없으면 전체 컬럼으로 대체하지 않아야 한다.
    def test_unknown_column_family_draws_nothing(self) -> None:
        spec = build_plot_spec(
            FAMILY_TABLE, "지역별 인지도", "auto", None, None, None, None, "exclude",
            column_family_name="지역별",
        )

        self.assertEqual(spec["data"]["records"], [])


# 값 라벨이 서로 겹칠 때 줄이거나 접는 규칙을 검증한다.
class ValueLabelTests(unittest.TestCase):
    # 시도 수만 바꿔 가며 같은 모양의 남녀 인구 표를 만든다.
    @staticmethod
    def _table(regions: int) -> dict:
        columns = ["지역 Region", "남 Male", "여 Female"]
        return {
            **TABLE,
            "title_ko": "지역별 주민등록인구",
            "body": body(columns, [
                [f"지역{index}", str(6_894_990 - index * 300_000), str(6_835_145 - index * 300_000)]
                for index in range(regions)
            ]),
        }

    def _spec(self, regions: int, orientation: str = "vertical") -> tuple[dict, dict]:
        spec = build_plot_spec(
            self._table(regions), "지역별 남녀 인구", "grouped_bar",
            "지역", None, None, 0, "exclude",
            metrics=[{"column": "남", "label": "남"}, {"column": "여", "label": "여"}],
        )
        # 방향은 서비스가 spec을 만든 뒤에 붙이므로 여기서도 같은 순서로 붙인다.
        spec["chart"]["orientation"] = orientation
        return spec, build_vega_lite_spec(spec)

    # 자리가 넉넉하면 값을 그대로 적는다.
    def test_sparse_chart_keeps_exact_values(self) -> None:
        _, vega_lite = self._spec(3)

        label_layer = vega_lite["layer"][1]
        self.assertEqual(label_layer["encoding"]["text"]["field"], "value")

    # 자리가 빠듯하면 만 단위로 줄여서라도 값을 보여준다.
    def test_crowded_chart_shortens_values(self) -> None:
        spec, vega_lite = self._spec(6)

        label_layer = vega_lite["layer"][1]
        self.assertEqual(label_layer["encoding"]["text"]["field"], "_label")
        self.assertEqual(vega_lite["data"]["values"][0]["_label"], "689만")
        self.assertIsNone(spec["chart"].get("value_labels"))

    # 줄여도 들어가지 않으면 라벨을 접고 값은 tooltip에 남긴다.
    def test_too_crowded_chart_drops_labels_and_keeps_tooltip(self) -> None:
        spec, vega_lite = self._spec(17)

        self.assertIs(spec["chart"]["value_labels"], False)
        self.assertEqual(len(vega_lite["layer"]), 1)
        tooltip_fields = [item["field"] for item in vega_lite["layer"][0]["encoding"]["tooltip"]]
        self.assertEqual(tooltip_fields, ["x", "series", "value"])
        # 접었다는 warnings에 다시 부를 방법을 적으면 모델이 그대로 따라 같은 데이터를 방향만 바꿔
        # 한 번 더 그린다. 화면에는 같은 차트가 둘 남으므로 일어난 일만 적어야 한다.
        folded = [warning for warning in spec["warnings"] if "겹쳐" in warning]
        self.assertTrue(folded, spec["warnings"])
        self.assertNotIn("가로 막대로 요청", folded[0])
        self.assertNotIn("요청하면", folded[0])

    # 선그래프는 같은 연도의 라벨이 한 자리에 겹치므로 값이 붙은 쪽을 비워야 한다.
    def test_line_chart_blanks_labels_that_land_on_each_other(self) -> None:
        # 2023년 두 값은 서로 붙어 있고, 2021년 두 값은 축 위아래로 멀리 떨어져 있다.
        close_table = {
            **YEAR_SERIES_TABLE,
            "body": body(YEAR_SERIES_COLUMNS, [
                ["2021", "서울", "950"],
                ["2021", "부산", "330"],
                ["2023", "서울", "980"],
                ["2023", "부산", "1000"],
            ]),
        }
        spec = build_plot_spec(
            close_table, "연도별 지역 인구 추이", "line",
            YEAR_SERIES_COLUMNS[0], YEAR_SERIES_COLUMNS[2], YEAR_SERIES_COLUMNS[1],
            None, "exclude",
        )
        vega_lite = build_vega_lite_spec(spec)

        labels = {
            (value["x"], value["series"]): value["_label"]
            for value in vega_lite["data"]["values"]
        }
        self.assertEqual(labels[(2023, "부산")], "1,000")
        self.assertEqual(labels[(2023, "서울")], "")
        self.assertEqual(labels[(2021, "서울")], "950")
        self.assertEqual(labels[(2021, "부산")], "330")

    # 가로 막대는 범주마다 줄이 따로 있어 라벨을 접지 않고, 축 끝에 라벨 자리를 남긴다.
    def test_horizontal_chart_keeps_labels_with_axis_headroom(self) -> None:
        spec, vega_lite = self._spec(17, orientation="horizontal")

        self.assertIsNone(spec["chart"].get("value_labels"))
        self.assertEqual(vega_lite["layer"][1]["encoding"]["text"]["field"], "value")
        largest = max(value["value"] for value in vega_lite["data"]["values"])
        self.assertGreater(vega_lite["encoding"]["x"]["scale"]["domainMax"], largest)


# 필터로 값이 하나만 남은 컬럼을 x축에 두면 남은 행이 한 칸에 겹쳐 쌓여 합계 막대 하나가 된다.
class CollapsedAxisTests(unittest.TestCase):
    CENTRAL = {"column": "구분", "value": "중앙행정기관"}
    YEARS = [2023, 2024, 2025]
    TOTALS = [15334703.0, 17775028.0, 21972130.0]

    # x로 지정한 구분 컬럼이 필터로 한 값만 남으면 연도 축으로 옮겨야 한다.
    def test_filtered_column_given_as_x_moves_to_the_year_axis(self) -> None:
        spec = build_plot_spec(
            LONG_CATEGORY_TABLE, "중앙행정기관의 공공데이터 활용 건수 추이", "auto",
            "구분 Classification", "합계 Total", None, None, "exclude",
            filters=[self.CENTRAL],
        )

        records = spec["data"]["records"]
        self.assertEqual(spec["chart"]["x"], "연도 Year")
        self.assertEqual([record["x"] for record in records], self.YEARS)
        self.assertEqual([record["value"] for record in records], self.TOTALS)
        self.assertTrue(any(
            "'구분 Classification'" in warning and "'연도 Year'" in warning
            for warning in spec["warnings"]
        ))

    # metrics로 지표를 고른 선택 계획 경로도 같은 축 교정을 받아야 한다.
    def test_selection_plan_moves_collapsed_x_to_the_year_axis(self) -> None:
        spec = build_plot_spec(
            LONG_CATEGORY_TABLE, "중앙행정기관의 공공데이터 활용 건수 추이", "auto",
            "구분 Classification", None, None, None, "exclude",
            filters=[self.CENTRAL],
            metrics=[{"column": "합계 Total", "label": "합계"}],
        )

        records = spec["data"]["records"]
        self.assertEqual(spec["chart"]["x"], "연도 Year")
        self.assertEqual([record["x"] for record in records], self.YEARS)
        self.assertEqual([record["value"] for record in records], self.TOTALS)

    # 축을 지정하지 않아도 필터가 좁힌 컬럼이 축으로 뽑히면 안 된다.
    def test_collapsed_column_is_not_picked_as_x_without_a_request(self) -> None:
        spec = build_plot_spec(
            LONG_CATEGORY_TABLE, "중앙행정기관 공공데이터 활용 추이", "auto",
            None, "합계 Total", None, None, "exclude",
            filters=[self.CENTRAL],
        )

        self.assertEqual([record["x"] for record in spec["data"]["records"]], self.YEARS)

    # 옮길 컬럼이 없으면 조용히 쌓지 말고 왜 겹쳤는지 알려야 한다.
    def test_collapsed_x_without_a_replacement_warns(self) -> None:
        spec = build_plot_spec(
            FLAT_CATEGORY_TABLE, "중앙행정기관 활용 실적", "auto",
            "구분 Classification", None, None, None, "exclude",
            filters=[self.CENTRAL],
            metrics=[{"column": "합계 Total", "label": "합계"}],
        )

        self.assertEqual(spec["chart"]["x"], "구분 Classification")
        self.assertTrue(any(
            "'구분 Classification'" in warning and "겹쳐 쌓" in warning
            for warning in spec["warnings"]
        ))

    # 값이 여럿 남은 컬럼은 축으로 멀쩡하므로 손대지 않아야 한다.
    def test_category_column_with_many_values_stays_on_the_x_axis(self) -> None:
        spec = build_plot_spec(
            LONG_CATEGORY_TABLE, "2025년 기관별 공공데이터 활용 실적", "auto",
            "구분 Classification", "합계 Total", None, None, "exclude", year=2025,
        )

        self.assertEqual(spec["chart"]["x"], "구분 Classification")
        self.assertEqual(
            [record["x"] for record in spec["data"]["records"]],
            ["중앙행정기관", "지방자치단체"],
        )
        self.assertEqual(spec["warnings"], [])



if __name__ == "__main__":
    unittest.main()
