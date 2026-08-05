# -*- coding: utf-8 -*-
"""통계표 담당 정보 조회와 응답 구성을 담당한다."""
from app.tools.repository.contact_repository import ContactRepository


class ContactService:
    def __init__(
        self,
        repository: ContactRepository | None = None,
    ):
        self._repository = repository or ContactRepository()

    # DB 행을 도구들이 공유하는 담당 정보 형태로 변환한다.
    @staticmethod
    def contact_result(row: dict) -> dict:
        return {
            "department": row["dept"],
            "officer": row["officer"],
            "phone": row["phone"],
            "source_system": row["source_system"],
            "source_url": row["source_url"],
        }

    # 통계표 문맥과 담당 정보로 search_contacts 성공 응답을 만든다.
    @staticmethod
    def build_response(stat: dict, contacts: list[dict]) -> dict:
        return {
            "found": True,
            "stat_id": stat["stat_id"],
            "publication_year": stat["publication_year"],
            "ref_id": stat["ref_id"],
            "level3_title": stat["level3_title"],
            "level4_title": stat["level4_title"],
            "title_ko": stat["title_ko"],
            "contact_count": len(contacts),
            "contacts": contacts,
        }

    # stat_id에 해당하는 통계표와 담당 정보를 하나의 결과로 조회한다.
    def search_contacts(self, stat_id: int) -> dict:
        stat, rows = self._repository.select_contact_data(stat_id)
        if stat is None:
            return {
                "found": False,
                "stat_id": stat_id,
                "contact_count": 0,
                "contacts": [],
            }
        contacts = [self.contact_result(row) for row in rows]
        return self.build_response(stat, contacts)
