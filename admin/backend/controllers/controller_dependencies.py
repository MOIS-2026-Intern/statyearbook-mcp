# -*- coding: utf-8 -*-
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
