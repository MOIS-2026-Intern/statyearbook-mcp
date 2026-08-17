# -*- coding: utf-8 -*-
"""주요통계집 HWPX 파서가 ❍/<> 표제를 통계 계층으로 복원하는지 검증한다."""
import tempfile
import unittest
import xml.sax.saxutils as saxutils
import zipfile

from pathlib import Path

from admin.backend.services.load_dml import build_load_dml
from admin.backend.services.load_major_statistics import parse_major_statistics


HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


# 문단 하나를 HWPX 본문 XML 조각으로 만든다.
def paragraph(text: str, in_box: bool = False) -> str:
    run = f"<hp:run><hp:t>{saxutils.escape(text)}</hp:t></hp:run>"
    if not in_box:
        return f"<hp:p>{run}</hp:p>"
    # 항목 제목과 번호는 실제 문서에서 묶음 개체 안의 글상자에 들어 있다.
    return f"<hp:p><hp:run><hp:rect><hp:subList><hp:p>{run}</hp:p></hp:subList></hp:rect></hp:run></hp:p>"


# 행렬을 병합 없는 HWPX 표 XML로 만든다.
def table(rows: list[list[str]]) -> str:
    cells = []
    for row_index, row in enumerate(rows):
        columns = "".join(
            f'<hp:tc><hp:cellAddr rowAddr="{row_index}" colAddr="{col_index}"/>'
            f'<hp:cellSpan colSpan="1" rowSpan="1"/>'
            "<hp:subList><hp:p><hp:run><hp:t>"
            f"{saxutils.escape(value)}</hp:t></hp:run></hp:p></hp:subList>"
            "</hp:tc>"
            for col_index, value in enumerate(row)
        )
        cells.append(f"<hp:tr>{columns}</hp:tr>")
    body = "".join(cells)
    return (
        f'<hp:p><hp:run><hp:tbl rowCnt="{len(rows)}" colCnt="{len(rows[0])}">'
        f"{body}</hp:tbl></hp:run></hp:p>"
    )


def section(*parts: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hp="{HP}" '
        f'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section">{"".join(parts)}</hs:sec>'
    )


# 목차 한 장과 본문 한 장으로 이루어진 최소 주요통계집 HWPX를 만든다.
def build_hwpx(directory: Path) -> str:
    contents = section(
        paragraph("4"),
        paragraph("지방자치분권"),
        paragraph("4-34. 지구촌 새마을운동 117"),
        paragraph("4-38. 서해 5도 133"),
    )
    body = section(
        paragraph("4"),
        paragraph("지방자치분권"),
        paragraph("지구촌 새마을운동", in_box=True),
        paragraph("4-34", in_box=True),
        paragraph("('25.6.30.)"),
        paragraph("❍ 추진개요"),
        paragraph("- 개도국의 빈곤퇴치와 농촌발전"),
        paragraph("< 지구촌 새마을운동 현황 >"),
        table([["구분", "'24"], ["초청연수", "990"]]),
        paragraph("주) 시범마을 53개소"),
        paragraph("• 새마을발전협력과 과장 신기동(044-205-3461)"),
        paragraph("서해 5도", in_box=True),
        paragraph("4-38", in_box=True),
        paragraph("('24.12.31.)"),
        paragraph("❍ 서해 5도 인구 : 8,151명(남 4,860 / 여 3,291)"),
        paragraph("- 연평면 1,993 / 백령면 4,722 / 대청면 1,436"),
        paragraph("※ 옹진군 전체 인구(19,996명)의 40.8%"),
        paragraph("❍ 서해 5도 관광객"),
        paragraph("(단위 : 명)"),
        table([["'23", "'24"], ["107,359", "105,934"]]),
        paragraph("• 균형발전진흥과 과장 박유정(044-205-3530)"),
    )
    path = directory / "major.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", contents)
        archive.writestr("Contents/section1.xml", body)
    return str(path)


class MajorStatisticsParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory()
        path = build_hwpx(Path(cls._directory.name))
        cls.parsed = parse_major_statistics(
            path,
            publication_year=2025,
            publication_period="H2",
        )
        cls.units = {unit["ref_id"]: unit for unit in cls.parsed["statistics"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    # 발간물은 같은 해의 다른 판과 구분되도록 반기를 갖고 제목에도 반기가 드러나야 한다.
    def test_publication_carries_the_half_year_period(self) -> None:
        publication = self.parsed["publication"]
        self.assertEqual(publication["publication_kind"], "major_statistics")
        self.assertEqual(publication["publication_period"], "H2")
        self.assertEqual(publication["title"], "2025년 하반기 주요통계집")

    # 항목 번호는 장·항목 두 단계이므로 chapter_no와 section_no에 들어가야 한다.
    def test_item_number_becomes_chapter_and_section(self) -> None:
        unit = self.units["4-38-1"]
        self.assertEqual(unit["chapter_no"], 4)
        self.assertEqual(unit["section_no"], 38)
        self.assertEqual(unit["chapter"], "지방자치분권")
        self.assertEqual(unit["section"], "서해 5도")
        self.assertIsNone(unit["level3_no"])
        self.assertIsNone(unit["level4_no"])

    # ❍ 표제는 3계층, <> 표제는 그 표의 실제 제목이므로 4계층으로 들어가야 한다.
    def test_bullet_becomes_level3_and_angle_title_becomes_level4(self) -> None:
        bullet = self.units["4-34-1"]
        self.assertEqual(bullet["level3_title"], "추진개요")
        self.assertIsNone(bullet["level4_title"])

        angle = self.units["4-34-2"]
        self.assertEqual(angle["level4_title"], "지구촌 새마을운동 현황")
        # 앞선 ❍가 이미 자기 본문을 가졌으므로 <>는 그 아래가 아니라 나란한 표다.
        self.assertIsNone(angle["level3_title"])

    # 항목 이름 없이는 뜻이 통하지 않는 묶음 제목은 항목 이름과 이어 붙여야 한다.
    def test_title_joins_the_item_name_only_when_it_is_missing(self) -> None:
        self.assertEqual(self.units["4-34-1"]["title_ko"], "지구촌 새마을운동 추진개요")
        self.assertEqual(self.units["4-34-2"]["title_ko"], "지구촌 새마을운동 현황")
        self.assertEqual(self.units["4-38-2"]["title_ko"], "서해 5도 관광객")

    # 표가 없는 ❍ 묶음도 제목에 적힌 수치와 본문 줄이 표로 저장되어야 검색·임베딩이 닿는다.
    def test_bullet_without_a_table_still_stores_its_text_as_a_table(self) -> None:
        unit = self.units["4-38-1"]
        self.assertEqual(len(unit["tables"]), 1)
        table_md = unit["tables"][0]["table_md"]
        self.assertIn("서해 5도 인구 : 8,151명(남 4,860 / 여 3,291)", table_md)
        self.assertIn("연평면 1,993", table_md)
        records = unit["tables"][0]["body"]["records"]
        self.assertEqual(len(records), 2)

    # 주석과 단위는 그 묶음에만 달려야 한다. 항목 전체에 퍼지면 표마다 뜻이 어긋난다.
    def test_notes_and_unit_stay_with_their_own_block(self) -> None:
        self.assertEqual(
            [note["content"] for note in self.units["4-38-1"]["footnotes"]],
            ["※ 옹진군 전체 인구(19,996명)의 40.8%"],
        )
        self.assertEqual(self.units["4-38-2"]["footnotes"], [])
        self.assertEqual(self.units["4-38-2"]["unit"], "명")
        self.assertIsNone(self.units["4-38-1"]["unit"])

    # 담당 부서는 항목 끝에 한 번만 적히므로 그 항목의 모든 통계 행이 함께 가져야 한다.
    def test_contacts_apply_to_every_row_of_the_item(self) -> None:
        for ref_id in ("4-38-1", "4-38-2"):
            contacts = self.units[ref_id]["contacts"]
            self.assertEqual(len(contacts), 1)
            self.assertEqual(contacts[0]["dept"], "균형발전진흥과")
            self.assertEqual(contacts[0]["phone"], "044-205-3530")

    # 기준일은 항목 제목 아래에 두 자리 연도로 적히므로 발간연도의 세기를 붙여야 한다.
    def test_base_date_gets_the_publication_century(self) -> None:
        self.assertEqual(self.units["4-34-1"]["base_date"], "2025.6.30.")
        self.assertEqual(self.units["4-38-1"]["base_date"], "2024.12.31.")

    # 인쇄 쪽 번호는 앞머리 목차에 있으므로 목차와 대조해 채워야 한다.
    def test_page_start_comes_from_the_table_of_contents(self) -> None:
        self.assertEqual(self.units["4-34-1"]["page_start"], 117)
        self.assertEqual(self.units["4-38-1"]["page_start"], 133)
        self.assertEqual(self.parsed["toc_reconciliation"]["toc_only_entries"], [])
        self.assertEqual(self.parsed["toc_reconciliation"]["body_only_entries"], [])

    # 한 항목이 여러 통계 행으로 갈리므로 ref_id에 순번을 붙여 발간물 안에서 유일해야 한다.
    def test_ref_ids_are_unique_within_the_publication(self) -> None:
        ref_ids = [unit["ref_id"] for unit in self.parsed["statistics"]]
        self.assertEqual(sorted(ref_ids), ["4-34-1", "4-34-2", "4-38-1", "4-38-2"])
        self.assertEqual(self.parsed["checks"]["duplicate_ref_ids"], [])

    # 적재 SQL은 같은 종류·연도·반기의 판만 교체 대상으로 삼아야 다른 반기가 지워지지 않는다.
    def test_load_dml_scopes_replacement_to_one_half_year(self) -> None:
        sql = build_load_dml(self.parsed, mode="replace")
        self.assertIn(
            "publication_kind = 'major_statistics' AND year = 2025 AND period = 'H2'",
            sql,
        )
        self.assertIn(
            "INSERT INTO publications (publication_kind, period, year, pub_no, title, page_count)",
            sql,
        )


if __name__ == "__main__":
    unittest.main()
