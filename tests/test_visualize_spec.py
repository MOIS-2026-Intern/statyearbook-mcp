import unittest

from app.tools.visualize_service.chart_spec_builder import build_plot_spec
from app.tools.visualize_service.table_interpreter import profile_columns, resolve_column
from app.tools.visualize_service.vega_lite_renderer import build_vega_lite_spec, summary_text


def make_table(columns: list[str], records: list[dict[str, str]], title: str = "테스트 통계") -> dict:
    return {
        "stat_id": 12,
        "ref_id": "1-2-2",
        "publication_year": 2025,
        "title_ko": title,
        "title_en": "Test statistics",
        "unit": "명",
        "base_date": "2024.12.31.",
        "table_seq": 1,
        "caption": "2024. 12. 31. 기준",
        "body": {"columns": columns, "records": records},
    }


class VisualizeSpecTests(unittest.TestCase):
    def test_success_summary_does_not_expose_internal_chart_details(self) -> None:
        spec = {
            "chart": {
                "title": "행정기관 위원회",
                "type": "bar",
                "decision_source": "selection_plan",
                "reason": "원본 표와 대조했습니다.",
            },
            "data": {"record_count": 3},
            "vega_lite": {"mark": "bar"},
            "warnings": [],
        }

        text = summary_text(spec)

        self.assertEqual(text, "행정기관 위원회 시각화를 생성했습니다.")
        self.assertNotIn("Vega-Lite", text)
        self.assertNotIn("데이터 포인트", text)
        self.assertNotIn("선택 이유", text)

    def test_validated_selection_plan_uses_all_requested_subsidy_metrics(self) -> None:
        columns = [
            "구분 Classification 지역 Region",
            "계 Total",
            "온라인 Online_이용건수 Usage",
            "온라인 Online_비율 Percentage",
            "방문 In-person_이용건수 Usage",
            "방문 In-person_비율 Percentage",
            "찾아가는 보조금 Subsidy 24_이용건수 Usage",
            "찾아가는 보조금 Subsidy 24_비율 Percentage",
        ]
        records = [
            dict(zip(columns, ["계 Total", "1,773,222", "1,753,905", "98.9", "15,001", "0.8", "4,316", "0.2"])),
            dict(zip(columns, ["서 울 Seoul", "307,020", "304,977", "99.3", "1,662", "0.5", "381", "0.1"])),
        ]
        metrics = [
            {"column": "온라인 Online_이용건수 Usage", "label": "온라인", "unit": "건"},
            {"column": "방문 In-person_이용건수 Usage", "label": "방문", "unit": "건"},
            {"column": "찾아가는 보조금 Subsidy 24_이용건수 Usage", "label": "찾아가는 보조금", "unit": "건"},
        ]

        spec = build_plot_spec(
            {**make_table(columns, records, "보조금24"), "unit": "건, %"},
            "서울의 온라인, 방문, 찾아가는 보조금 이용건수를 시각화",
            "bar",
            None,
            None,
            None,
            None,
            "exclude",
            filters=[{"column": columns[0], "value": "서 울 Seoul"}],
            metrics=metrics,
        )

        self.assertEqual(spec["chart"]["decision_source"], "selection_plan")
        self.assertEqual(spec["chart"]["unit"], "건")
        self.assertEqual(spec["transform"]["type"], "validated_selection_plan")
        self.assertEqual(spec["data"]["record_count"], 3)
        self.assertEqual(
            {record["x"]: record["value"] for record in spec["data"]["records"]},
            {"온라인": 304977.0, "방문": 1662.0, "찾아가는 보조금": 381.0},
        )
        self.assertEqual(
            spec["data"]["selected_dataset"]["records"],
            spec["data"]["records"],
        )
        self.assertEqual(len(spec["data"]["selected_dataset"]["provenance"]), 3)
        vega_lite = build_vega_lite_spec(spec)
        self.assertEqual(len(vega_lite["data"]["values"]), 3)

    def test_invalid_metric_selection_does_not_fall_back_to_query_heuristics(self) -> None:
        columns = ["지역 Region", "온라인 이용건수", "방문 이용건수"]
        records = [dict(zip(columns, ["서울", "10", "2"]))]

        spec = build_plot_spec(
            make_table(columns, records),
            "서울 온라인 방문",
            "bar",
            None,
            None,
            None,
            None,
            "auto",
            filters=[{"column": "지역 Region", "value": "서울"}],
            metrics=[{"column": "없는 지표", "label": "온라인", "unit": None}],
        )

        self.assertEqual(spec["chart"]["type"], "table")
        self.assertEqual(spec["chart"]["decision_source"], "server_validation")
        self.assertEqual(spec["data"]["record_count"], 0)
        self.assertTrue(any("없는 지표" in warning for warning in spec["warnings"]))

    def test_invalid_exact_filter_does_not_use_partial_match(self) -> None:
        columns = ["지역 Region", "이용건수 Usage"]
        records = [dict(zip(columns, ["서 울 Seoul", "10"]))]

        spec = build_plot_spec(
            make_table(columns, records),
            "서울 이용건수",
            "bar",
            None,
            None,
            None,
            None,
            "auto",
            filters=[{"column": "지역 Region", "value": "서울"}],
            metrics=[{"column": "이용건수 Usage", "label": "이용건수", "unit": "명"}],
        )

        self.assertEqual(spec["chart"]["decision_source"], "server_validation")
        self.assertEqual(spec["data"]["record_count"], 0)
        self.assertTrue(any("값 '서울'" in warning for warning in spec["warnings"]))

    def test_semantic_category_request_selects_2024_row_and_flattened_family(self) -> None:
        columns = [
            "구분 Classification 연도 Year",
            "계 Total",
            "국 가 공 무 원 State Civil Servants_소계 Sub-total",
            "국 가 공 무 원 State Civil Servants_정무직 Political Service",
            "국 가 공 무 원 State Civil Servants_별정직 Special Government Service",
            "국 가 공 무 원 State Civil Servants_계약직 Contractual Service",
            "국 가 공 무 원 State Civil Servants_특정직 Special Service",
            "국 가 공 무 원 State Civil Servants_일반직 General Service",
            "국 가 공 무 원 State Civil Servants_기능직 Technical Service",
        ]
        records = [
            dict(zip(columns, ["2023", "1,145,458", "753,974", "141", "279", "-", "581,469", "172,085", "-"])),
            dict(zip(columns, ["2024", "1,145,047", "752,174", "140", "221", "-", "579,988", "171,825", "-"])),
        ]

        spec = build_plot_spec(
            make_table(columns, records, "행정부 공무원 정원"),
            "기준연도: 2024.12.31.",
            "bar",
            "분류",
            "정원",
            None,
            None,
            "auto",
        )

        self.assertEqual(spec["chart"]["type"], "bar")
        self.assertEqual(spec["chart"]["group"], None)
        self.assertEqual(spec["transform"]["type"], "wide_row_to_categories")
        self.assertEqual(spec["transform"]["selected_year"], 2024)
        self.assertEqual(spec["transform"]["column_family"], "국 가 공 무 원 State Civil Servants")
        self.assertEqual(
            {record["x"]: record["value"] for record in spec["data"]["records"]},
            {"정무직": 140.0, "별정직": 221.0, "특정직": 579988.0, "일반직": 171825.0},
        )
        self.assertTrue(spec["transform"]["aggregate_matches_components"])

    def test_missing_only_column_is_not_a_category_alias(self) -> None:
        columns = ["연도 Year", "계약직 Contractual Service"]
        rows = [
            {"연도 Year": "2023", "계약직 Contractual Service": "-"},
            {"연도 Year": "2024", "계약직 Contractual Service": "-"},
        ]
        profiles = profile_columns(columns, rows)

        self.assertIsNone(resolve_column("분류", profiles))
        self.assertTrue(profiles[1]["is_missing_only"])

    def test_explicit_year_and_city_are_applied_as_and_filter(self) -> None:
        columns = [
            "연도 Year",
            "도시 City",
            "인구 Population_남자 Male",
            "인구 Population_여자 Female",
            "인구 Population_계 Total",
            "가구 Household_일반 General",
            "가구 Household_1인가구 Single",
        ]
        records = [
            dict(zip(columns, ["2024", "서울특별시", "10", "20", "30", "7", "3"])),
            dict(zip(columns, ["2024", "부산광역시", "11", "21", "32", "8", "4"])),
            dict(zip(columns, ["2023", "서울특별시", "9", "19", "28", "6", "2"])),
        ]

        spec = build_plot_spec(
            make_table(columns, records, "도시 통계"),
            "서울의 인구",
            "bar",
            "분류",
            "값",
            None,
            None,
            "auto",
            year=2024,
            city="서울",
            column_family_name="인구",
        )

        self.assertEqual(spec["request"]["selection"]["selected_row_count"], 1)
        self.assertEqual(spec["request"]["selection"]["city_value"], "서울특별시")
        self.assertEqual(spec["transform"]["column_family"], "인구 Population")
        self.assertEqual(
            {record["x"]: record["value"] for record in spec["data"]["records"]},
            {"남자": 10.0, "여자": 20.0},
        )

    def test_unknown_city_does_not_fall_back_to_all_rows(self) -> None:
        columns = ["연도 Year", "도시 City", "인구 Population_남자 Male", "인구 Population_여자 Female"]
        records = [
            dict(zip(columns, ["2024", "서울특별시", "10", "20"])),
            dict(zip(columns, ["2024", "부산광역시", "11", "21"])),
        ]

        spec = build_plot_spec(
            make_table(columns, records),
            "대구 인구",
            "bar",
            "분류",
            "값",
            None,
            None,
            "auto",
            year=2024,
            city="대구",
            column_family_name="인구",
        )

        self.assertEqual(spec["chart"]["type"], "table")
        self.assertEqual(spec["chart"]["decision_source"], "server_validation")
        self.assertEqual(spec["data"]["record_count"], 0)
        self.assertTrue(any("대구" in warning for warning in spec["warnings"]))

    def test_unknown_year_does_not_fall_back_to_all_rows(self) -> None:
        columns = ["연도 Year", "지표 Metrics_남자 Male", "지표 Metrics_여자 Female"]
        records = [
            dict(zip(columns, ["2023", "10", "20"])),
            dict(zip(columns, ["2024", "11", "21"])),
        ]

        spec = build_plot_spec(
            make_table(columns, records),
            "2025년 지표",
            "bar",
            "분류",
            "값",
            None,
            None,
            "auto",
            year=2025,
            column_family_name="지표",
        )

        self.assertEqual(spec["chart"]["type"], "table")
        self.assertEqual(spec["chart"]["decision_source"], "server_validation")
        self.assertEqual(spec["data"]["record_count"], 0)
        self.assertTrue(any("2025년" in warning for warning in spec["warnings"]))

    def test_column_family_uses_text_before_first_underscore(self) -> None:
        columns = [
            "연도 Year",
            "인구 Population_내국인 Korean_남자 Male",
            "인구 Population_내국인 Korean_여자 Female",
            "인구 Population_외국인 Foreigner_남자 Male",
        ]
        records = [dict(zip(columns, ["2024", "10", "20", "3"]))]

        spec = build_plot_spec(
            make_table(columns, records),
            "2024년 인구",
            "bar",
            "분류",
            "값",
            None,
            None,
            "auto",
            year=2024,
            column_family_name="인구",
        )

        self.assertEqual(spec["transform"]["column_family"], "인구 Population")
        self.assertEqual(spec["data"]["record_count"], 3)
        self.assertEqual(
            {record["x"] for record in spec["data"]["records"]},
            {"내국인 / 남자", "내국인 / 여자", "외국인 / 남자"},
        )

    def test_query_city_value_is_selected_before_record_reshape(self) -> None:
        columns = ["도시 City", "인구 Population_남자 Male", "인구 Population_여자 Female"]
        records = [
            dict(zip(columns, ["서울특별시", "10", "20"])),
            dict(zip(columns, ["부산광역시", "11", "21"])),
        ]

        spec = build_plot_spec(
            make_table(columns, records),
            "부산광역시 인구를 분류별로 보여줘",
            "bar",
            "분류",
            "값",
            None,
            None,
            "auto",
            column_family_name="인구",
        )

        self.assertEqual(spec["request"]["selection"]["query_row_value"], "부산광역시")
        self.assertEqual(spec["data"]["source_row_count"], 1)
        self.assertEqual(
            {record["x"]: record["value"] for record in spec["data"]["records"]},
            {"남자": 11.0, "여자": 21.0},
        )


if __name__ == "__main__":
    unittest.main()
