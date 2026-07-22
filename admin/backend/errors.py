"""관리자 controller, service와 repository가 공유하는 업무 예외."""


class PublicationsNotFoundError(LookupError):
    # 찾지 못한 발간물 ID를 호출자가 다시 활용할 수 있도록 보존한다.
    def __init__(self, pub_ids: list[int]):
        self.pub_ids = pub_ids
        super().__init__(f"publications not found: {pub_ids}")
