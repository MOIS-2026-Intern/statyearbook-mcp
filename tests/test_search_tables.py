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
        self.assertEqual(cached["body"]["columns"], ["연도", "건수"])
        self.assertEqual(cached["body"]["records"], [{"연도": "2024", "건수": "1,234"}])

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
