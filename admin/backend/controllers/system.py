# 이 파일은 관리자 서버 상태와 화면에서 사용할 선택사항 조회 API를 제공한다.
# DB DSN이나 로컬 모델 절대경로 같은 내부 설정은 응답에서 제외한다.
from fastapi import APIRouter, Depends, Request

from admin.backend.config import ADMIN_API_PREFIX
from admin.backend.controllers.dependencies import authorize_admin
from utils.publication_kind import (
    DEFAULT_PUBLICATION_KIND,
    FIRST_HALF_PERIOD,
    MAJOR_STATISTICS_KIND,
    SECOND_HALF_PERIOD,
)


router = APIRouter(prefix=ADMIN_API_PREFIX, dependencies=[Depends(authorize_admin)])


# 관리자 서비스의 최소 생존 상태를 외부 점검용으로 반환한다.
@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "statyearbook-admin"}


# 내부 비밀값을 제외하고 화면에서 선택 가능한 운영 옵션만 직렬화한다.
@router.get("/options")
def options(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "targets": settings.targets(),
        "publication_kinds": [
            {
                "id": DEFAULT_PUBLICATION_KIND,
                "label": "통계연보",
                "description": "행정안전통계연보 발간판입니다.",
            },
            {
                "id": MAJOR_STATISTICS_KIND,
                "label": "주요통계집",
                "description": "주요통계집 발간판입니다. 상반기·하반기를 함께 지정합니다.",
            },
        ],
        "publication_periods": [
            {"id": FIRST_HALF_PERIOD, "label": "상반기"},
            {"id": SECOND_HALF_PERIOD, "label": "하반기"},
        ],
        "load_modes": [
            {
                "id": "reject",
                "label": "중복 발간판 거부",
                "description": "같은 연도·반기의 판이 있으면 안전하게 중단합니다.",
            },
            {
                "id": "replace",
                "label": "해당 발간판 교체",
                "description": "선택한 연도·반기의 기존 데이터만 삭제한 뒤 다시 적재합니다.",
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
