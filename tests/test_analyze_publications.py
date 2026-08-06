# -*- coding: utf-8 -*-
"""analyze_publications 도구가 집계 값을 반환하는지 검증한다."""
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.tools.analyze_publications import ValueFilter
from app.tools.repository.department_mapping import (
    DEPARTMENT_ALIASES,
    department_match_keys,
)
from app.tools.repository.publication_repository import (
    normalize_match_key,
    officer_match_keys,
)
from app.tools.service.publication_analysis_service import analyze_publications_data


class OfficerMatchKeyTests(unittest.TestCase):
    """담당자 검색어의 직급·경칭 표기가 달라도 같은 담당자를 찾아야 한다.

    저장값은 '주무관 위운비'처럼 직급이 이름 앞에 오지만, 사용자는 '위운비 주무관님'처럼
    순서를 바꿔 부른다. 검색어에서 직급·경칭을 뗀 키를 함께 만들어 어느 표기로 물어도
    같은 결과가 되게 한다.
    """

    # 직급 위치와 경칭이 달라도 이름만 남긴 키가 함께 만들어져야 한다.
    def test_rank_and_honorific_forms_share_the_name_key(self) -> None:
        for query in (
            "위운비",
            "위운비 주무관",
            "위운비주무관",
            "위운비 주무관님",
            "주무관 위운비",
            "위운비님",
            "위운비씨",
            "위운비 씨",
            "위운비 담당자",
        ):
            with self.subTest(query=query):
                self.assertIn("위운비", officer_match_keys(query))

    # 저장값을 그대로 넣은 질의는 원본 키가 남아 계속 맞아야 한다.
    def test_original_key_is_kept_for_stored_value_queries(self) -> None:
        keys = officer_match_keys("행정기획과주무관 안지현")

        self.assertIn("행정기획과주무관안지현", keys)
        self.assertIn("행정기획과안지현", keys)

    # 직급 자체로 찾는 질의는 지우고 나면 남는 게 없으므로 원본 키만 써야 한다.
    def test_rank_only_query_keeps_the_rank(self) -> None:
        self.assertEqual(officer_match_keys("주무관"), ("주무관",))
        self.assertEqual(officer_match_keys("사무관님"), ("사무관님",))

    # 부서 이름에 들어가는 '담당관'까지 떼면 부서를 함께 부른 검색어가 깨진다.
    def test_department_word_is_not_stripped(self) -> None:
        self.assertIn(
            "데이터정보화담당관실이동주",
            officer_match_keys("데이터정보화담당관실 이동주"),
        )

    # 뗄 직급이 없는 이름은 키가 하나뿐이어야 조건이 불필요하게 늘지 않는다.
    def test_plain_name_produces_a_single_key(self) -> None:
        self.assertEqual(officer_match_keys("위운비"), ("위운비",))


class DepartmentAliasTests(unittest.TestCase):
    """부서를 약칭이나 옛 이름으로 불러도 그 부서를 찾아야 한다.

    저장값은 '국가정보자원관리원'이지만 사용자는 '국정자원'처럼 줄여 부르거나 개편 전
    이름인 '정부통합전산센터'로 부른다. 둘 다 저장값의 부분 문자열이 아니라서 부분 일치로는
    한 건도 찾지 못하므로, 적어 둔 현재 이름을 비교 키로 함께 만들어 준다.
    """

    # 약칭은 그 기관의 현재 이름 키를 함께 가져야 한다.
    def test_abbreviation_carries_the_current_name(self) -> None:
        keys = department_match_keys("국정자원")

        self.assertIn("국정자원", keys)
        self.assertIn("국가정보자원관리원", keys)

    # 개편 전 이름으로 물어도 현재 이름으로 이어져야 한다.
    def test_former_name_carries_the_current_name(self) -> None:
        self.assertIn("국가정보자원관리원", department_match_keys("정부통합전산센터"))
        self.assertIn("지방자치인재개발원", department_match_keys("지방행정연수원"))
        self.assertIn("국립과학수사연구원", department_match_keys("국립과학수사연구소"))
        self.assertIn("국가재난안전교육원", department_match_keys("재난교육원"))
        self.assertIn("국립재난안전연구원", department_match_keys("재난안전연구원"))
        self.assertIn("국립재난안전연구원", department_match_keys("재난연구원"))

    # 적어 두지 않은 이름은 키가 늘지 않아야 조건이 불필요하게 넓어지지 않는다.
    def test_unlisted_query_keeps_a_single_key(self) -> None:
        self.assertEqual(department_match_keys("재난정보통신과"), ("재난정보통신과",))
        self.assertEqual(department_match_keys("국가기록원"), ("국가기록원",))

    # 검색어의 공백 표기는 부서 이름과 마찬가지로 비교 전에 지워야 한다.
    def test_spacing_is_normalized_before_lookup(self) -> None:
        self.assertIn("국가정보자원관리원", department_match_keys("국 정 자원"))

    # 현재 이름에 그대로 들어 있는 표현은 부분 일치로 이미 찾히므로 적을 이유가 없다.
    # 적어 두면 같은 뜻의 조건이 두 번 걸린다.
    def test_aliases_are_not_substrings_of_the_current_name(self) -> None:
        for name, aliases in DEPARTMENT_ALIASES.items():
            name_key = normalize_match_key(name)
            for alias in aliases:
                with self.subTest(name=name, alias=alias):
                    self.assertNotIn(normalize_match_key(alias), name_key)

    # 같은 약칭을 두 기관에 적으면 한쪽이 조용히 덮여 엉뚱한 기관으로 이어진다.
    def test_no_alias_points_at_two_departments(self) -> None:
        seen: dict[str, str] = {}
        for name, aliases in DEPARTMENT_ALIASES.items():
            for alias in aliases:
                key = normalize_match_key(alias)
                self.assertNotIn(key, seen, f"{alias}가 {seen.get(key)}와 {name}에 겹칩니다")
                seen[key] = name


class AnalyzePublicationsTests(unittest.TestCase):
    # 통계 제목은 연락처 값 필터가 아니므로 MCP 입력 스키마 단계에서 거부해야 한다.
    def test_value_filter_rejects_statistic_title(self) -> None:
        with self.assertRaises(ValidationError):
            ValueFilter.model_validate(
                {"field": "statistic_title", "contains": "마을세무사"}
            )

        value_filter = ValueFilter.model_validate(
            {"field": "officer", "contains": "홍길동"}
        )
        self.assertEqual(value_filter.field, "officer")

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"matched_publications": 1, "count": 319}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 발간연도를 생략하면 최신 발간판을 기준으로 집계 값과 산출 근거를 돌려줘야 한다.
    def test_returns_count_for_latest_publication_year(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(operation="count", subject="statistics")

        self.assertEqual(result["count"], 319)
        self.assertEqual(result["matched_publications"], 1)
        self.assertEqual(result["applied_publication_year"], 2026)
        self.assertTrue(result["publication_year_defaulted"])
        self.assertIn("statistics.stat_id", result["basis"])
        latest_publication_year_mock.assert_called_once_with()
        self.assertEqual(execute_plan_mock.call_args.args[0].params, (2026,))

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"matched_publications": 1, "count": 140}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # distinct_field를 주면 연락처 레코드 수가 아니라 값의 가짓수를 세야 한다.
    def test_counts_distinct_values_of_requested_field(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="contacts",
            distinct_field="phone",
        )

        self.assertEqual(result["count"], 140)
        self.assertEqual(result["distinct_field"], "phone")
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("COUNT(DISTINCT NULLIF(BTRIM(c.phone), ''))", sql)
        self.assertNotIn("COUNT(DISTINCT c.contact_id)", sql)

    @patch("app.tools.repository.publication_analysis_repository._latest_publication_year", return_value=2026)
    # 빈 값이 하나의 종류로 잡히지 않도록 FILTER 절로 걸러야 한다.
    def test_distinct_count_excludes_empty_values(
        self,
        latest_publication_year_mock,
    ) -> None:
        with patch(
            "app.tools.service.publication_analysis_service._execute_plan",
            return_value=[{"matched_publications": 1, "count": 140}],
        ) as execute_plan_mock:
            analyze_publications_data(
                operation="count",
                subject="contacts",
                distinct_field="phone",
            )

        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("FILTER (WHERE NULLIF(BTRIM(c.phone), '') IS NOT NULL)", sql)

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"organization": "재난경감과", "count": 4}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # breakdown에서도 그룹마다 레코드 수가 아니라 값의 가짓수를 세야 한다.
    def test_counts_distinct_values_per_group(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="breakdown",
            subject="contacts",
            group_by="organization",
            distinct_field="phone",
        )

        self.assertEqual(result["results"], [{"organization": "재난경감과", "count": 4}])
        self.assertEqual(result["distinct_field"], "phone")
        sql = execute_plan_mock.call_args.args[0].sql
        self.assertIn("COUNT(DISTINCT NULLIF(BTRIM(c.phone), ''))", sql)
        self.assertNotIn("COUNT(DISTINCT c.contact_id)", sql)
        self.assertIn("GROUP BY", sql)
        # 같은 값이 여러 그룹에 걸치면 합계가 전체 종류 수를 넘는다는 점을 알려야 한다.
        self.assertTrue(
            any("그룹 count의 합" in item for item in result["limitations"])
        )

    # distinct_field는 count·breakdown 이외의 operation에서 거부해야 한다.
    def test_rejects_distinct_field_outside_count(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="list",
                subject="contacts",
                distinct_field="phone",
            )

        self.assertIn(
            "distinct_field can only be used with count or breakdown",
            str(error.exception),
        )

    # subject가 다루지 않는 필드는 조인이 없으므로 거부해야 한다.
    def test_rejects_distinct_field_outside_subject(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="count",
                subject="footnotes",
                distinct_field="phone",
            )

        self.assertIn("unsupported distinct_field", str(error.exception))

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[
            {
                "statistic_title": "지역별 재난 예･경보시스템 보유",
                "officer": "주무관 위운비",
                "_total_count": 1,
            }
        ],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 담당자 이름을 주면 그 값을 가진 레코드만 남기고 산출 근거에도 조건을 밝혀야 한다.
    def test_filters_list_rows_by_field_value(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="list",
            subject="contacts",
            fields=["statistic_title", "officer"],
            value_filters=[{"field": "officer", "contains": "위운비"}],
            publication_year=2025,
        )

        plan = execute_plan_mock.call_args.args[0]
        self.assertIn("strpos(", plan.sql)
        # 값 조건은 페이지 자르기 전인 CTE 안에서 걸러야 total_count가 맞는다.
        self.assertLess(plan.sql.index("strpos("), plan.sql.index("_total_count"))
        self.assertEqual(plan.params, (2025, "위운비", 500, 0))
        self.assertEqual(
            result["value_filters"],
            [{"field": "officer", "contains": "위운비"}],
        )
        self.assertEqual(result["total_count"], 1)
        self.assertIn("'위운비' 포함", result["basis"])

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"matched_publications": 1, "count": 2}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 검색어의 공백과 직함 표기가 달라도 비교 키가 같으면 찾아야 한다.
    def test_normalizes_filter_value_before_matching(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="contacts",
            distinct_field="stat_id",
            value_filters=[{"field": "department", "contains": "재난 정보통신과"}],
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(execute_plan_mock.call_args.args[0].params, (2026, "재난정보통신과"))

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"matched_publications": 1, "count": 1}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 담당자는 직급·경칭을 뗀 키까지 조건에 넣어 어느 표기로 물어도 같은 결과가 되어야 한다.
    def test_officer_filter_matches_any_rank_notation(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        analyze_publications_data(
            operation="count",
            subject="contacts",
            value_filters=[{"field": "officer", "contains": "위운비 주무관님"}],
        )

        plan = execute_plan_mock.call_args.args[0]
        self.assertEqual(plan.params, (2026, "위운비주무관님", "위운비"))
        self.assertEqual(plan.sql.count("strpos("), 2)

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"matched_publications": 1, "count": 3}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 약칭으로 물어도 그 기관의 현재 이름을 조건에 함께 넣어 찾아야 한다.
    def test_department_filter_matches_an_alias(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="contacts",
            value_filters=[{"field": "department", "contains": "국정자원"}],
        )

        plan = execute_plan_mock.call_args.args[0]
        self.assertEqual(plan.params, (2026, "국정자원", "국가정보자원관리원"))
        self.assertEqual(plan.sql.count("strpos("), 2)
        # 응답의 value_filters는 사용자가 넣은 검색어를 그대로 유지해야 한다.
        self.assertEqual(
            result["value_filters"],
            [{"field": "department", "contains": "국정자원"}],
        )
        # 무엇을 바꿔 맞췄는지 밝혀야 모델이 근거를 정확히 인용한다.
        self.assertIn("'국정자원' 포함(약칭·옛 이름으로 보고", result["basis"])

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"matched_publications": 1, "count": 1}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 현재 이름으로 찾던 질의는 조건이 늘지 않아야 결과가 넓어지지 않는다.
    def test_current_department_name_keeps_one_condition(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="contacts",
            value_filters=[{"field": "department", "contains": "국가정보자원관리원"}],
        )

        plan = execute_plan_mock.call_args.args[0]
        self.assertEqual(plan.params, (2026, "국가정보자원관리원"))
        self.assertEqual(plan.sql.count("strpos("), 1)
        self.assertNotIn("약칭", result["basis"])

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[{"matched_publications": 1, "count": 282}],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 직급으로 목록을 뽑는 질의는 조건이 늘지 않고 그대로 유지되어야 한다.
    def test_rank_only_officer_filter_keeps_one_condition(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        analyze_publications_data(
            operation="count",
            subject="contacts",
            value_filters=[{"field": "officer", "contains": "주무관"}],
        )

        plan = execute_plan_mock.call_args.args[0]
        self.assertEqual(plan.params, (2026, "주무관"))
        self.assertEqual(plan.sql.count("strpos("), 1)

    # subject가 조인하지 않는 필드는 조건으로 받을 수 없어야 한다.
    def test_rejects_filter_field_outside_subject(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="list",
                subject="footnotes",
                value_filters=[{"field": "officer", "contains": "위운비"}],
            )

        self.assertIn("unsupported value_filters field", str(error.exception))

    # 발간판 단위 요약에는 값 조건을 걸 수 없어야 한다.
    def test_rejects_filter_on_overview(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="overview",
                subject="contacts",
                value_filters=[{"field": "officer", "contains": "위운비"}],
            )

        self.assertIn("value_filters can only be used with", str(error.exception))

    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 최신 발간판에 없으면 전체 발간판에서 다시 찾고 어느 판인지 밝혀야 한다.
    def test_falls_back_to_all_publications_when_latest_has_no_rows(
        self,
        latest_publication_year_mock,
    ) -> None:
        with patch(
            "app.tools.service.publication_analysis_service._execute_plan",
            side_effect=[
                [],
                [
                    {
                        "publication_year": 2025,
                        "statistic_title": "지역별 재난 예･경보시스템 보유",
                        "_total_count": 1,
                    }
                ],
            ],
        ) as execute_plan_mock:
            result = analyze_publications_data(
                operation="list",
                subject="contacts",
                fields=["statistic_title"],
                value_filters=[{"field": "officer", "contains": "홍길동"}],
            )

        self.assertEqual(execute_plan_mock.call_count, 2)
        self.assertTrue(result["publication_year_filter_relaxed"])
        self.assertIsNone(result["applied_publication_year"])
        self.assertEqual(result["result_count"], 1)
        # 넓혀 찾은 결과는 어느 발간판인지 밝힐 수 있어야 하므로 발간연도를 덧붙인다.
        self.assertEqual(
            result["selected_fields"],
            ["publication_year", "statistic_title"],
        )
        self.assertEqual(result["results"][0]["publication_year"], 2025)
        self.assertIn("2026", result["message"])
        # 두 번째 조회는 발간연도 조건 없이 값 조건만 남아야 한다.
        self.assertEqual(execute_plan_mock.call_args_list[1].args[0].params, ("홍길동", 500, 0))

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        side_effect=[
            [{"matched_publications": 0, "count": 0}],
            [{"matched_publications": 0, "count": 0}],
        ],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # count가 0이면 행이 있어도 비어 있는 결과로 보고 전체 발간판을 확인해야 한다.
    def test_falls_back_when_count_is_zero(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="contacts",
            distinct_field="stat_id",
            value_filters=[{"field": "officer", "contains": "없는이름"}],
        )

        self.assertEqual(execute_plan_mock.call_count, 2)
        # 넓혀도 없으면 처음 적용한 발간판 기준 응답을 유지한다.
        self.assertFalse(result["publication_year_filter_relaxed"])
        self.assertEqual(result["applied_publication_year"], 2026)
        self.assertEqual(result["count"], 0)
        self.assertIn("전체 발간판을 다시 조회해도", result["message"])

    @patch(
        "app.tools.service.publication_analysis_service._execute_plan",
        return_value=[],
    )
    @patch(
        "app.tools.repository.publication_analysis_repository._latest_publication_year",
        return_value=2026,
    )
    # 페이지를 넘기는 중에는 범위가 달라지면 안 되므로 넓히지 않는다.
    def test_does_not_relax_while_paging(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="list",
            subject="contacts",
            fields=["statistic_title"],
            offset=500,
        )

        self.assertEqual(execute_plan_mock.call_count, 1)
        self.assertFalse(result["publication_year_filter_relaxed"])
        self.assertEqual(result["applied_publication_year"], 2026)
        self.assertIsNone(result["message"])

    # 빈 검색어는 모든 행과 일치하므로 거부해야 한다.
    def test_rejects_empty_filter_value(self) -> None:
        with self.assertRaises(ValueError) as error:
            analyze_publications_data(
                operation="list",
                subject="contacts",
                value_filters=[{"field": "officer", "contains": "   "}],
            )

        self.assertIn("must not be empty", str(error.exception))


if __name__ == "__main__":
    unittest.main()
