# 이 파일은 발간물 목록 조회와 선택 발간물 전체 삭제 관리자 API를 제공한다.
# 대상 DB 활성화 여부와 요청값을 검증한 뒤 publication service에 위임한다.
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from admin.backend.config import ADMIN_API_PREFIX
from admin.backend.controllers.dependencies import authorize_admin
from admin.backend.models.publication import DeletePublicationsRequest
from admin.backend.repositories.publications import PublicationsNotFoundError


router = APIRouter(
    prefix=f"{ADMIN_API_PREFIX}/publications",
    dependencies=[Depends(authorize_admin)],
)


@router.get("")
def select_publications(
    request: Request,
    target: str = Query(default="local"),
) -> list[dict]:
    try:
        return request.app.state.publication_service.select_publications(target)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("")
def delete_publications(
    payload: DeletePublicationsRequest,
    request: Request,
) -> dict:
    try:
        return request.app.state.publication_service.delete_publications(
            payload.target,
            payload.pub_ids,
        )
    except PublicationsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
