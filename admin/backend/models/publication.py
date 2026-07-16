# 이 파일은 발간물 삭제 API의 선택 ID와 대상 DB 요청 형식을 정의한다.
from pydantic import BaseModel, Field


class DeletePublicationsRequest(BaseModel):
    pub_ids: list[int] = Field(min_length=1, max_length=100)
    target: str = "local"
