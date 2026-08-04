# -*- coding: utf-8 -*-
"""통계연보 계층 복원이 본문 표제를 정본으로 삼는지 검증한다.

2026년 연보처럼 목차 leaf 번호가 본문보다 밀려 있어도 표 번호·제목·장·절이
본문과 같아야 한다. HWPX 원본 없이 돌도록 표제 셀 문자열만 입력으로 쓴다.
"""
import unittest

from admin.backend.services.load_dml import validate_yearbook
from admin.backend.services.load_outline import (
    build_outline,
    build_toc_catalog,
    is_colophon,
    parse_heading_cell,
    parse_section_cover,
    split_title,
)


# 목차 표 한 장을 흉내 낸다. cells는 파서가 넘기는 셀 dict 구조를 따른다.
def toc_table(rows: list[list[str]]) -> dict:
    return {"cells": [[{"text": text} for text in row] for row in rows]}


# 본문 표제 문자열을 순서대로 Heading 목록으로 바꾼다.
def headings(*texts: str) -> list[tuple[object, int | None]]:
    parsed = []
    for page, text in enumerate(texts, start=1):
        heading = parse_heading_cell(text)
        assert heading is not None, text
        parsed.append((heading, page))
    return parsed


class SplitTitleTests(unittest.TestCase):
    def test_splits_on_line_break_between_korean_and_english(self):
        self.assertEqual(
            split_title("새마을금고\nCommunity Credit Cooperatives"),
            ("새마을금고", "Community Credit Cooperatives"),
        )

    def test_splits_single_line_at_last_korean_token(self):
        self.assertEqual(
            split_title("지역별 새마을금고 회원 Members of Community Credit Cooperatives"),
            ("지역별 새마을금고 회원", "Members of Community Credit Cooperatives"),
        )

    def test_keeps_acronym_inside_korean_title(self):
        self.assertEqual(
            split_title("지역별 지자체 CCTV 통합관제센터 운영 현황 CCTV Control Center Operations"),
            ("지역별 지자체 CCTV 통합관제센터 운영 현황", "CCTV Control Center Operations"),
        )

    def test_accepts_lowercase_english_title(self):
        self.assertEqual(split_title("사이버교육 e-Learning"), ("사이버교육", "e-Learning"))

    def test_does_not_cut_trailing_acronym_as_english_title(self):
        self.assertEqual(split_title("1인당 GRDP"), ("1인당 GRDP", None))

    def test_allows_single_uppercase_token_for_chapter_titles(self):
        self.assertEqual(
            split_title("기타 OTHERS", allow_single_token_en=True), ("기타", "OTHERS")
        )

    def test_english_only_heading_has_no_korean_title(self):
        self.assertEqual(
            split_title("Government Organization Chart"),
            (None, "Government Organization Chart"),
        )


class ParseHeadingCellTests(unittest.TestCase):
    def test_reads_four_level_reference(self):
        heading = parse_heading_cell("4-2-7-2 지역별 새마을금고 회원 Members by Region")
        self.assertEqual(
            (heading.level, heading.ref_id, heading.chapter_no, heading.section_no,
             heading.level3_no, heading.level4_no, heading.title_ko),
            (4, "4-2-7-2", 4, 2, 7, 2, "지역별 새마을금고 회원"),
        )

    def test_reads_three_level_reference(self):
        heading = parse_heading_cell("4-2-10 기부금품 모집등록 Registration of Donations")
        self.assertEqual((heading.level, heading.ref_id, heading.level4_no), (3, "4-2-10", None))

    def test_reads_appendix_reference(self):
        heading = parse_heading_cell("부록 1-2 연도별 정원 Fixed Number of Civil Servants by Year")
        self.assertEqual((heading.level, heading.ref_id, heading.chapter_no), (4, "부록1-2", 9))

    def test_ignores_non_heading_cell(self):
        self.assertIsNone(parse_heading_cell("(2025. 12. 31. 기준) (단위 : 명)"))


class BuildOutlineTests(unittest.TestCase):
    def setUp(self):
        # 2026년 연보 4장 2절 목차를 축약했다. "4-2-1 지역주도형 청년일자리 사업 실적 ?"은
        # 본문에서 빠졌는데도 목차에 남아 그 뒤 leaf 번호를 하나씩 밀어 놓은 항목이다.
        self.catalog = build_toc_catalog([
            toc_table([
                ["4", "지방행정/지역발전\nLOCAL ADMINISTRATION/REGIONAL DEVELOPMENT"],
                [
                    "",
                    "제2절 지역발전 REGIONAL DEVELOPMENT\n"
                    "4-2-1 지역주도형 청년일자리 사업 실적 ?\n"
                    "Community-led Youth Employment Project\n"
                    "4-2-2 마을기업 육성사업 Community Business 158\n"
                    "1. 연도별 마을기업 육성사업 158\n"
                    "Community Business by Year\n"
                    "4-2-11 기부금품 모집등록 Registration of Donations 175\n"
                    "4-2-12 옥외광고물 허가 및 신고 Outdoor Advertisements Permit & Report 176",
                ],
            ]),
        ])

    def test_uses_body_reference_numbers_not_toc(self):
        nodes, _ = build_outline(
            headings(
                "4-2-1 마을기업 육성사업 Community Business",
                "4-2-1-1 연도별 마을기업 육성사업 Community Business by Year",
                "4-2-10 기부금품 모집등록 Registration of Donations",
                "4-2-11 옥외광고물 허가 및 신고 Outdoor Advertisements Permit & Report",
            ),
            self.catalog,
            {},
        )
        self.assertEqual(
            [(node.ref_id, node.level4_title or node.level3_title) for node in nodes],
            [
                ("4-2-1-1", "연도별 마을기업 육성사업"),
                ("4-2-10", "기부금품 모집등록"),
                ("4-2-11", "옥외광고물 허가 및 신고"),
            ],
        )

    def test_level3_with_children_is_not_a_leaf(self):
        nodes, _ = build_outline(
            headings(
                "4-2-1 마을기업 육성사업 Community Business",
                "4-2-1-1 연도별 마을기업 육성사업 Community Business by Year",
                "4-2-1-2 지역별 마을기업 육성사업 Community Business by Region",
            ),
            self.catalog,
            {},
        )
        self.assertEqual([node.ref_id for node in nodes], ["4-2-1-1", "4-2-1-2"])
        self.assertEqual([node.level3_title for node in nodes], ["마을기업 육성사업"] * 2)

    def test_level3_without_children_keeps_empty_level4(self):
        nodes, _ = build_outline(
            headings("4-2-10 기부금품 모집등록 Registration of Donations"),
            self.catalog,
            {},
        )
        self.assertEqual(
            (nodes[0].level3_title, nodes[0].level4_no, nodes[0].level4_title),
            ("기부금품 모집등록", None, None),
        )

    def test_repeated_reference_does_not_create_second_leaf(self):
        # 쪽이 넘어가며 영문 제목만 다시 실린 표제는 같은 통계의 계속 표시다.
        nodes, by_ref = build_outline(
            headings(
                "1-1-1 정부조직 Government Organization",
                "1-1-1-1 정부 조직도",
                "1-1-1-1 Government Organization Chart",
            ),
            self.catalog,
            {},
        )
        self.assertEqual([node.ref_id for node in nodes], ["1-1-1-1"])
        self.assertEqual(by_ref["1-1-1-1"].level4_title, "정부 조직도")

    def test_chapter_comes_from_reference_number_not_document_position(self):
        nodes, _ = build_outline(
            headings("4-2-10 기부금품 모집등록 Registration of Donations"),
            self.catalog,
            {},
        )
        self.assertEqual(nodes[0].chapter, "지방행정/지역발전")
        self.assertEqual(nodes[0].section, "지역발전")

    def test_body_section_cover_wins_over_toc_section_name(self):
        nodes, _ = build_outline(
            headings("4-2-10 기부금품 모집등록 Registration of Donations"),
            self.catalog,
            {(4, 2): ("지역발전", "REGIONAL DEVELOPMENT")},
        )
        self.assertEqual(nodes[0].section, "지역발전")

    def test_ordinal_follows_document_order(self):
        nodes, _ = build_outline(
            headings(
                "4-2-10 기부금품 모집등록 Registration of Donations",
                "4-2-11 옥외광고물 허가 및 신고 Outdoor Advertisements Permit & Report",
            ),
            self.catalog,
            {},
        )
        self.assertEqual([node.ordinal for node in nodes], [1, 2])


class TocCatalogTests(unittest.TestCase):
    def test_reads_chapter_and_section_names(self):
        catalog = build_toc_catalog([
            toc_table([
                ["8", "기타 OTHERS"],
                ["", "8-1-1 국가기록원 기록보존 및 관리 377\nPreservation & Management of Archives"],
            ]),
        ])
        self.assertEqual(catalog.chapters[8], ("기타", "OTHERS"))
        self.assertEqual(catalog.leaves[0]["ref_id"], "8-1-1")
        self.assertEqual(catalog.leaves[0]["page"], 377)

    def test_missing_page_marker_is_not_a_page_number(self):
        catalog = build_toc_catalog([
            toc_table([
                ["4", "지방행정/지역발전"],
                ["", "4-2-1 지역주도형 청년일자리 사업 실적 ?\nCommunity-led Youth Employment Project"],
            ]),
        ])
        self.assertIsNone(catalog.leaves[0]["page"])
        self.assertEqual(catalog.leaves[0]["title_ko"], "지역주도형 청년일자리 사업 실적")


class SectionCoverTests(unittest.TestCase):
    def test_reads_section_number_and_titles(self):
        self.assertEqual(
            parse_section_cover(["제2절", "지역발전", "REGIONAL DEVELOPMENT"]),
            (2, "지역발전", "REGIONAL DEVELOPMENT"),
        )

    def test_rejects_ordinary_table(self):
        self.assertIsNone(parse_section_cover(["구분", "합계"]))


class ColophonTests(unittest.TestCase):
    def test_detects_print_information_table(self):
        self.assertTrue(is_colophon("인 쇄 2025년 8월 발 행 2025년 8월 발행처 행정안전부"))

    def test_ordinary_table_is_not_colophon(self):
        self.assertFalse(is_colophon("구분 지역 합계 서울 부산"))


class ValidateYearbookTests(unittest.TestCase):
    def payload(self, statistics: list[dict]) -> dict:
        return {
            "publication": {"year": 2026, "title": "2026 행정안전통계연보"},
            "statistics": statistics,
        }

    def test_rejects_duplicate_reference_ids(self):
        data = self.payload([
            {"ref_id": "4-2-10", "title_ko": "기부금품 모집등록"},
            {"ref_id": "4-2-10", "title_ko": "기부금품 모집등록"},
        ])
        with self.assertRaises(ValueError) as raised:
            validate_yearbook(data)
        self.assertIn("4-2-10", str(raised.exception))

    def test_rejects_statistic_without_title(self):
        with self.assertRaises(ValueError):
            validate_yearbook(self.payload([{"ref_id": "4-2-10", "title_ko": ""}]))

    def test_accepts_unique_statistics(self):
        validate_yearbook(self.payload([
            {"ref_id": "4-2-10", "title_ko": "기부금품 모집등록"},
            {"ref_id": "4-2-11", "title_ko": "옥외광고물 허가 및 신고"},
        ]))


if __name__ == "__main__":
    unittest.main()
