# 이 파일은 publication 관리 service의 대상 DB 선택, ID 정규화와 삭제 위임을 검증한다.
import unittest

from admin.backend.services.publications import PublicationService


class FakeSettings:
    def __init__(self):
        self.targets = []

    def target_dsn(self, target: str) -> str:
        self.targets.append(target)
        return f"postgresql:///{target}"


class FakePublicationRepository:
    def __init__(self):
        self.selected_dsns = []
        self.deleted = []

    def select_publications(self, dsn: str) -> list[dict]:
        self.selected_dsns.append(dsn)
        return [{"pub_id": 1, "year": 2026, "pub_no": None, "title": "2026 연보"}]

    def delete_publications(self, dsn: str, pub_ids: list[int]) -> dict:
        self.deleted.append((dsn, pub_ids))
        return {"deleted_publications": pub_ids, "deleted_counts": {"publications": len(pub_ids)}}


class PublicationServiceTests(unittest.TestCase):
    def test_select_publications_uses_selected_database_target(self) -> None:
        settings = FakeSettings()
        repository = FakePublicationRepository()
        service = PublicationService(settings, repository)

        publications = service.select_publications("local")

        self.assertEqual(publications[0]["pub_id"], 1)
        self.assertEqual(settings.targets, ["local"])
        self.assertEqual(repository.selected_dsns, ["postgresql:///local"])

    def test_delete_publications_deduplicates_and_sorts_ids(self) -> None:
        settings = FakeSettings()
        repository = FakePublicationRepository()
        service = PublicationService(settings, repository)

        service.delete_publications("production", [3, 1, 3])

        self.assertEqual(
            repository.deleted,
            [("postgresql:///production", [1, 3])],
        )

    def test_delete_publications_rejects_non_positive_ids(self) -> None:
        service = PublicationService(FakeSettings(), FakePublicationRepository())

        with self.assertRaises(ValueError):
            service.delete_publications("local", [0])


if __name__ == "__main__":
    unittest.main()
