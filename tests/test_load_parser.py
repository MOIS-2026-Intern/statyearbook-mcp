import unittest

from pathlib import Path

from admin.backend.services.load_parser import parse


YEARBOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "통계연보.hwpx"


@unittest.skipUnless(YEARBOOK_PATH.is_file(), "sample HWPX is not available")
class YearbookHierarchyParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed = parse(str(YEARBOOK_PATH), publication_year=2025)
        cls.by_ref = {
            unit["ref_id"]: unit for unit in cls.parsed["statistics"]
        }

    def test_combined_level3_and_level4_heading_uses_toc_leaf(self) -> None:
        unit = self.by_ref["3-1-7-1"]

        self.assertEqual(unit["chapter"], "디지털정부")
        self.assertEqual(unit["section"], "디지털 정책과 서비스")
        self.assertEqual(unit["level3_no"], 7)
        self.assertEqual(unit["level4_no"], 1)
        self.assertEqual(unit["level3_title"], "모바일 신분증")
        self.assertEqual(unit["level4_title"], "모바일 공무원증")
        self.assertEqual(unit["title_ko"], "모바일 공무원증")

    def test_level3_leaf_repeats_title_at_level4(self) -> None:
        unit = self.by_ref["1-1-2"]

        self.assertIsNone(unit["level4_no"])
        self.assertEqual(unit["level3_title"], "부속기관")
        self.assertEqual(unit["level4_title"], "부속기관")

    def test_all_body_statistics_match_unique_toc_entries(self) -> None:
        refs = [unit["ref_id"] for unit in self.parsed["statistics"]]

        self.assertEqual(len(refs), 319)
        self.assertEqual(len(refs), len(set(refs)))
        self.assertTrue(all("images" not in unit for unit in self.parsed["statistics"]))


if __name__ == "__main__":
    unittest.main()
