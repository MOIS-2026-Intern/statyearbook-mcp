"""관리자 controller, service와 repository가 공유하는 업무 예외."""


class PublicationsNotFoundError(LookupError):
    def __init__(self, pub_ids: list[int]):
        self.pub_ids = pub_ids
        super().__init__(f"publications not found: {pub_ids}")
