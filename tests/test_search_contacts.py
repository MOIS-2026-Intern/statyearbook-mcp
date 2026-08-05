# -*- coding: utf-8 -*-
"""search_contacts 도구가 통계표 담당 정보를 반환하는지 검증한다."""
import unittest
from unittest.mock import MagicMock

from app.tools.service.contact_service import ContactService


STAT = {
    "stat_id": 32,
    "publication_year": 2025,
    "ref_id": "3-1-7-1",
    "level3_title": "모바일 신분증",
    "level4_title": "모바일 공무원증",
    "title_ko": "모바일 공무원증",
}

CONTACT = {
    "dept": "디지털안전정책과",
    "officer": "홍길동",
    "phone": "044-205-0000",
    "source_system": "업무관리시스템",
    "source_url": "https://example.test/statistics",
}


class SearchContactsTests(unittest.TestCase):
    # 응답은 통계표 문맥과 담당 부서·담당자·전화번호를 함께 반환해야 한다.
    def test_returns_contacts_for_statistic(self) -> None:
        service = ContactService()
        response = service.build_response(STAT, [service.contact_result(CONTACT)])

        self.assertTrue(response["found"])
        self.assertEqual(response["stat_id"], 32)
        self.assertEqual(response["publication_year"], 2025)
        self.assertEqual(response["title_ko"], "모바일 공무원증")
        self.assertEqual(response["contact_count"], 1)
        self.assertEqual(
            response["contacts"][0],
            {
                "department": "디지털안전정책과",
                "officer": "홍길동",
                "phone": "044-205-0000",
                "source_system": "업무관리시스템",
                "source_url": "https://example.test/statistics",
            },
        )

    # 통계표는 있지만 담당 정보가 없으면 found 상태를 유지하고 빈 목록을 반환해야 한다.
    def test_returns_empty_contacts_for_known_statistic(self) -> None:
        response = ContactService().build_response(STAT, [])

        self.assertTrue(response["found"])
        self.assertEqual(response["contact_count"], 0)
        self.assertEqual(response["contacts"], [])

    # 존재하지 않는 stat_id는 연락처가 없는 통계표와 구분해 found=false로 반환해야 한다.
    def test_returns_not_found_for_unknown_statistic(self) -> None:
        repository = MagicMock()
        repository.select_contact_data.return_value = (None, [])
        service = ContactService(repository)

        response = service.search_contacts(999999)

        self.assertFalse(response["found"])
        self.assertEqual(response["stat_id"], 999999)
        self.assertEqual(response["contact_count"], 0)
        self.assertEqual(response["contacts"], [])
        repository.select_contact_data.assert_called_once_with(999999)


if __name__ == "__main__":
    unittest.main()
