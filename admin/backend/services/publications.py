# 이 파일은 관리자 발간물 조회·삭제 요청을 대상 DB와 repository에 연결한다.
# 중복 ID와 잘못된 ID를 차단하고 삭제 결과를 API용 payload로 반환한다.
from admin.backend.config import AdminSettings
from admin.backend.repositories.publications import PublicationRepository


class PublicationService:
    def __init__(
        self,
        settings: AdminSettings,
        repository: PublicationRepository | None = None,
    ):
        self.settings = settings
        self.repository = repository or PublicationRepository()

    def select_publications(self, target: str) -> list[dict]:
        return self.repository.select_publications(self.settings.target_dsn(target))

    def delete_publications(self, target: str, pub_ids: list[int]) -> dict:
        selected_ids = sorted(set(pub_ids))
        if not selected_ids or any(pub_id <= 0 for pub_id in selected_ids):
            raise ValueError("pub_ids must contain positive integers")
        return self.repository.delete_publications(
            self.settings.target_dsn(target),
            selected_ids,
        )
