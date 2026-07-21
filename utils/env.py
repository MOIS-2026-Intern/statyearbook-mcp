"""서비스별 프로필 기본값과 비밀 환경변수의 우선순위를 관리한다."""
from __future__ import annotations

import os

from collections.abc import MutableMapping
from pathlib import Path

from dotenv import dotenv_values


VALID_PROFILES = frozenset({"local", "test", "main"})


# 프로세스 환경 > 서비스 .env.<profile> > 프로필 기본값 순서로 설정을 합친다.
# 선택한 프로필 이름을 검증하고 호출자가 넘긴 환경 mapping만 갱신한다.
def load_service_env(
    service_dir: Path,
    environ: MutableMapping[str, str] | None = None,
) -> str:
    """선택한 프로필 기본값을 서비스 전용 환경에 안전하게 합친다."""
    target = environ if environ is not None else os.environ
    profile = (target.get("APP_PROFILE") or "local").strip().lower()
    if profile not in VALID_PROFILES:
        allowed = ", ".join(sorted(VALID_PROFILES))
        raise RuntimeError(f"APP_PROFILE must be one of: {allowed}")

    override_path = service_dir / f".env.{profile}"
    overrides = {
        key: value
        for key, value in dotenv_values(override_path).items()
        if value is not None and key != "APP_PROFILE"
    }
    profile_path = service_dir / "profiles" / f"{profile}.env"
    if not profile_path.is_file():
        raise RuntimeError(f"service profile file not found: {profile_path}")
    defaults = {
        key: value
        for key, value in dotenv_values(profile_path).items()
        if value is not None and key != "APP_PROFILE"
    }
    for key, value in {**defaults, **overrides}.items():
        target.setdefault(key, value)
    target["APP_PROFILE"] = profile
    return profile
