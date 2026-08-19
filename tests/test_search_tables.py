# -*- coding: utf-8 -*-
"""search_tables 도구가 통계표 본문과 메타데이터를 반환하는지 검증한다."""
import unittest

from app.table_cache import clear_table_cache, get_cached_table
from app.tools.service.table_service import build_response, merge_bodies


STAT = {
    "stat_id": 32,
    "ref_id": "3-1-7-1",
    "publication_year": 2025,
    "chapter_no": 3,
    "section_no": 1,
    "level3_no": 7,
    "level4_no": 1,
    "chapter": "디지털정부",
    "section": "디지털 정책과 서비스",
    "level3_title": "모바일 신분증",
    "level4_title": "모바일 공무원증",
    "title_ko": "모바일 공무원증",
    "title_en": "Mobile Identification for Public Officials",
    "unit": "건",
    "base_date": "2024.12.31.",
    "page_start": 72,
}

TABLE = {
    "seq": 1,
    "caption": "2024. 12. 31. 기준",
    "n_rows": 1,
    "n_cols": 2,
    "body": {
        "columns": ["연도", "건수"],
        "records": [{"연도": "2024", "건수": "1,234"}],
    },
    "table_md": "| 연도 | 건수 |",
}
SOURCE = {
    "department": "디지털안전정책과",
    "officer": "홍길동",
    "phone": "044-205-0000",
    "source_system": None,
    "source_url": None,
}


class SearchTablesTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_table_cache()

    # 응답은 표 메타데이터를 담고, 발급한 handle로 원본 본문을 다시 꺼낼 수 있어야 한다.
    def test_returns_table_metadata_and_cached_body(self) -> None:
        response = build_response(STAT, [TABLE], [], [SOURCE])

        self.assertTrue(response["found"])
        self.assertEqual(response["stat_id"], 32)
        self.assertEqual(response["ref_id"], "3-1-7-1")
        self.assertEqual(response["title_ko"], "모바일 공무원증")
        self.assertEqual(response["level3_title"], "모바일 신분증")
        self.assertEqual(response["level4_title"], "모바일 공무원증")
        self.assertEqual(response["unit"], "건")
        self.assertEqual(len(response["tables"]), 1)
        self.assertEqual(response["tables"][0]["table_md"], "| 연도 | 건수 |")
        self.assertEqual(response["source"][0]["dept"], "디지털안전정책과")
        self.assertEqual(response["source"][0]["officer"], "홍길동")

        cached = get_cached_table(response["tables"][0]["table_handle"])
        self.assertEqual(cached["stat_id"], 32)
        # 같은 표로 그린 차트도 표 답변과 같은 담당 부서를 인용 줄에 적어야 한다.
        self.assertEqual(cached["department"], "디지털안전정책과")
        self.assertEqual(cached["body"]["columns"], ["연도", "건수"])
        self.assertEqual(cached["body"]["records"], [{"연도": "2024", "건수": "1,234"}])

    # row_label을 넘기면 전체 Markdown 미리보기에 없을 수 있는 행도 별도 구조로 반환해야 한다.
    def test_returns_rows_matching_the_requested_label(self) -> None:
        table = {
            "seq": 1,
            "caption": "지자체별 지역사랑상품권 도입현황",
            "n_rows": 20,
            "n_cols": 7,
            "table_md": "",
            "body": {
                "columns": ["구분", "계", "광역", "기초 / 총", "기초 / 발행", "기초 / 발행(179)", "기초 / 비고"],
                "records": [
                    {"구분": "충북", "계": "11", "광역": "-", "기초 / 총": "11",
                     "기초 / 발행": "11", "기초 / 발행(179)": "청주시, 충주시", "기초 / 비고": ""},
                    {"구분": "충남", "계": "15", "광역": "-", "기초 / 총": "15",
                     "기초 / 발행": "15",
                     "기초 / 발행(179)": "천안시, 공주시, 보령시, 아산시, 서산시, 논산시, 계룡시, 당진시, 금산군, 부여군, 서천군, 청양군, 홍성군, 예산군, 태안군",
                     "기초 / 비고": ""},
                ],
            },
        }

        response = build_response(STAT, [table], [], [], row_label="충남")
        matched = response["tables"][0]

        self.assertEqual(matched["row_label_query"], "충남")
        self.assertEqual(matched["matched_row_count"], 1)
        self.assertEqual(matched["matched_rows"][0]["구분"], "충남")
        self.assertEqual(matched["matched_rows"][0]["기초 / 발행"], "15")
        self.assertIn("천안시", matched["matched_rows"][0]["기초 / 발행(179)"])
        self.assertIn("| 충남 | 15 | - | 15 | 15 |", matched["matched_rows_md"])

    # 사용자가 축약 지명을 말해도 원문 행 라벨이 정식 시도명인 표를 찾을 수 있어야 한다.
    def test_matches_regional_aliases_for_row_labels(self) -> None:
        table = {
            "seq": 1,
            "caption": None,
            "n_rows": 1,
            "n_cols": 2,
            "table_md": "",
            "body": {
                "columns": ["시도", "값"],
                "records": [{"시도": "충청남도", "값": "15"}],
            },
        }

        response = build_response(STAT, [table], [], [], row_label="충남")

        self.assertEqual(response["tables"][0]["matched_rows"][0]["시도"], "충청남도")

    # 열이 나뉜 통계표는 합쳐도 seq마다 하나씩 발급하지 않고 같은 핸들을 공유해야 한다.
    def test_shares_one_handle_across_column_split_tables(self) -> None:
        left = {
            "seq": 1, "caption": None, "n_rows": 2, "n_cols": 2, "table_md": "",
            "body": {
                "columns": ["지역", "외국인근로자"],
                "records": [{"지역": "서울", "외국인근로자": "37,734"}],
            },
        }
        right = {
            "seq": 2, "caption": None, "n_rows": 2, "n_cols": 2, "table_md": "",
            "body": {
                "columns": ["지역", "귀화자"],
                "records": [{"지역": "서울", "귀화자": "47,124"}],
            },
        }

        response = build_response(STAT, [left, right], [], [SOURCE])

        handles = {table["table_handle"] for table in response["tables"]}
        self.assertEqual(len(handles), 1)
        cached = get_cached_table(handles.pop())
        self.assertEqual(cached["body"]["columns"], ["지역", "외국인근로자", "귀화자"])
        self.assertEqual(cached["n_rows"], 1)
        self.assertEqual(cached["n_cols"], 3)


class MergeBodiesTests(unittest.TestCase):
    # 넓은 표는 지역 열만 되풀이하고 나머지 열을 다음 seq로 넘긴다. 이 조각을 행으로 이어
    # 붙이면 다른 항목의 수치가 엉뚱한 컬럼 이름 아래로 들어가고 뒤쪽 컬럼은 사라진다.
    def test_joins_column_split_pages_side_by_side(self) -> None:
        left = {
            "columns": ["지역", "외국인근로자", "결혼이민자"],
            "records": [
                {"지역": "서울", "외국인근로자": "37,734", "결혼이민자": "34,368"},
                {"지역": "부산", "외국인근로자": "12,361", "결혼이민자": "3,201"},
            ],
        }
        right = {
            "columns": ["지역", "귀화자", "외국인주민자녀"],
            "records": [
                {"지역": "서울", "귀화자": "47,124", "외국인주민자녀": "36,473"},
                {"지역": "부산", "귀화자": "2,824", "외국인주민자녀": "5,379"},
            ],
        }

        merged = merge_bodies([left, right])

        self.assertEqual(
            merged["columns"],
            ["지역", "외국인근로자", "결혼이민자", "귀화자", "외국인주민자녀"],
        )
        self.assertEqual(merged["records"], [
            {"지역": "서울", "외국인근로자": "37,734", "결혼이민자": "34,368",
             "귀화자": "47,124", "외국인주민자녀": "36,473"},
            {"지역": "부산", "외국인근로자": "12,361", "결혼이민자": "3,201",
             "귀화자": "2,824", "외국인주민자녀": "5,379"},
        ])

    # 컬럼이 같은 조각은 같은 표가 아래로 이어진 것이므로 행으로 붙여야 한다.
    def test_appends_rows_when_the_columns_match(self) -> None:
        first = {"columns": ["지역", "인구"], "records": [{"지역": "서울", "인구": "9"}]}
        second = {"columns": ["지역", "인구"], "records": [{"지역": "부산", "인구": "3"}]}

        merged = merge_bodies([first, second])

        self.assertEqual(merged["columns"], ["지역", "인구"])
        self.assertEqual(merged["records"], [
            {"지역": "서울", "인구": "9"},
            {"지역": "부산", "인구": "3"},
        ])

    # 행 라벨이 어긋나면 같은 행의 오른쪽 절반이 아니므로 가로로 붙이면 안 된다.
    def test_falls_back_to_position_when_the_row_labels_differ(self) -> None:
        first = {"columns": ["구분 연도", "인구"], "records": [{"구분 연도": "2024", "인구": "9"}]}
        second = {"columns": ["연도", "인구"], "records": [{"연도": "2023", "인구": "8"}]}

        merged = merge_bodies([first, second])

        self.assertEqual(merged["columns"], ["구분 연도", "인구"])
        self.assertEqual(merged["records"], [
            {"구분 연도": "2024", "인구": "9"},
            {"구분 연도": "2023", "인구": "8"},
        ])


if __name__ == "__main__":
    unittest.main()
