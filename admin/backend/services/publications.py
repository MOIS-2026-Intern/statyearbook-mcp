# 이 파일은 관리자 발간물 조회·삭제 요청을 대상 DB와 repository에 연결한다.
# 중복 ID와 잘못된 ID를 차단하고 삭제 결과를 API용 payload로 반환한다.
from admin.backend.config import AdminSettings
from admin.backend.repositories.publications import PublicationRepository


class PublicationService:
    # 프로필별 연결 제약과 발간물 영속성 구현을 결합한다.
    def __init__(
        self,
        settings: AdminSettings,
        repository: PublicationRepository | None = None,
    ):
        self.settings = settings
        self.repository = repository or PublicationRepository()

    # 허용된 DB 대상의 발간물 목록 조회를 저장소에 위임한다.
    def select_publications(self, target: str) -> list[dict]:
        return self.repository.select_publications(self.settings.target_dsn(target))

    # 중복을 제거한 양의 ID만 발간물 단위 삭제 트랜잭션에 전달한다.
    def delete_publications(self, target: str, pub_ids: list[int]) -> dict:
        selected_ids = sorted(set(pub_ids))
        if not selected_ids or any(pub_id <= 0 for pub_id in selected_ids):
            raise ValueError("pub_ids must contain positive integers")
        return self.repository.delete_publications(
            self.settings.target_dsn(target),
            selected_ids,
        )
