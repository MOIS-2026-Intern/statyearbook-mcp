# 이 파일은 관리자 controller가 공유하는 설정 조회와 API 토큰 인증을 제공한다.
# 인증이 설정된 환경에서는 모든 관리자 API 요청을 검증한다.
import hmac

from fastapi import Header, HTTPException, Request

from admin.backend.config import AdminSettings


def admin_settings(request: Request) -> AdminSettings:
    return request.app.state.settings


def authorize_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> None:
    token = admin_settings(request).api_token
    if token and not hmac.compare_digest(x_admin_token or "", token):
        raise HTTPException(status_code=401, detail="invalid admin token")
