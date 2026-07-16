# 이 파일은 관리자 서버 상태와 화면에서 사용할 선택사항 조회 API를 제공한다.
# DB DSN이나 로컬 모델 절대경로 같은 내부 설정은 응답에서 제외한다.
from fastapi import APIRouter, Depends, Request

from admin.backend.controllers.controller_dependencies import authorize_admin


router = APIRouter(prefix="/api", dependencies=[Depends(authorize_admin)])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "statyearbook-admin"}


@router.get("/options")
def options(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "targets": settings.targets(),
        "load_modes": [
            {
                "id": "reject",
                "label": "중복 연도 거부",
                "description": "같은 연도가 있으면 안전하게 중단합니다.",
            },
            {
                "id": "replace",
                "label": "해당 연도 교체",
                "description": "선택 연도의 기존 데이터만 삭제한 뒤 다시 적재합니다.",
            },
        ],
        "embedding_models": [
            {
                "id": item.id,
                "label": item.label,
                "provider": item.provider,
                "dimension": item.dimension,
                "enabled": item.enabled,
                "description": item.description,
            }
            for item in settings.embedding_models()
        ],
        "max_upload_mb": settings.max_upload_mb,
    }
