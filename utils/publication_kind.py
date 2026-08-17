# -*- coding: utf-8 -*-
"""Shared publication kind and period identifiers used by ingestion and MCP tools."""
from typing import Literal


PublicationKind = Literal["yearbook", "major_statistics"]

DEFAULT_PUBLICATION_KIND: PublicationKind = "yearbook"
MAJOR_STATISTICS_KIND: PublicationKind = "major_statistics"
PUBLICATION_KINDS: tuple[PublicationKind, ...] = (
    DEFAULT_PUBLICATION_KIND,
    MAJOR_STATISTICS_KIND,
)
PUBLICATION_KIND_LABELS: dict[str, str] = {
    DEFAULT_PUBLICATION_KIND: "통계연보",
    MAJOR_STATISTICS_KIND: "주요통계집",
}

# 화면 버튼이 고르는 조회 범위다. 발간물 하나로 좁히거나 두 발간물을 함께 검색한다.
# all은 저장값이 아니므로 조회 조건으로 바로 쓰지 않고 scope_publication_kinds로 실제
# 발간물 목록을 풀어 쓴다.
PublicationScope = Literal["yearbook", "major_statistics", "all"]
ALL_PUBLICATIONS_SCOPE: PublicationScope = "all"
# 기본값은 전체다. 한 발간물로 좁혀 두면 다른 발간물에만 실린 통계를 두고도 연보에 없다고
# 답하게 되므로, 범위를 좁히는 일은 사용자가 직접 고른 경우로 남긴다.
DEFAULT_PUBLICATION_SCOPE: PublicationScope = ALL_PUBLICATIONS_SCOPE
PUBLICATION_SCOPES: tuple[PublicationScope, ...] = (
    *PUBLICATION_KINDS,
    ALL_PUBLICATIONS_SCOPE,
)

# 주요통계집은 같은 해에 상반기·하반기 두 판이 나온다. 통계연보는 해마다 한 판뿐이라
# 반기 구분이 없으며 빈 문자열로 둔다. NULL을 쓰면 (종류, 연도, 반기) 유일 색인에서
# NULL끼리 서로 다른 값으로 취급되어 같은 연보를 두 번 적재할 수 있다.
PublicationPeriod = Literal["", "H1", "H2"]
# 도구 인자로 노출하는 값이다. "반기 없음"은 값을 주지 않는 것으로 표현한다.
HalfYearPeriod = Literal["H1", "H2"]

NO_PUBLICATION_PERIOD: PublicationPeriod = ""
FIRST_HALF_PERIOD: PublicationPeriod = "H1"
SECOND_HALF_PERIOD: PublicationPeriod = "H2"
PUBLICATION_PERIODS: tuple[PublicationPeriod, ...] = (
    NO_PUBLICATION_PERIOD,
    FIRST_HALF_PERIOD,
    SECOND_HALF_PERIOD,
)
HALF_YEAR_PERIODS: tuple[PublicationPeriod, ...] = (FIRST_HALF_PERIOD, SECOND_HALF_PERIOD)

PUBLICATION_PERIOD_LABELS: dict[str, str] = {
    NO_PUBLICATION_PERIOD: "",
    FIRST_HALF_PERIOD: "상반기",
    SECOND_HALF_PERIOD: "하반기",
}
# 사용자와 모델이 쓰는 한국어 표기도 같은 값으로 받아 준다.
_PERIOD_ALIASES: dict[str, PublicationPeriod] = {
    "": NO_PUBLICATION_PERIOD,
    "none": NO_PUBLICATION_PERIOD,
    "annual": NO_PUBLICATION_PERIOD,
    "h1": FIRST_HALF_PERIOD,
    "1h": FIRST_HALF_PERIOD,
    "first_half": FIRST_HALF_PERIOD,
    "상반기": FIRST_HALF_PERIOD,
    "h2": SECOND_HALF_PERIOD,
    "2h": SECOND_HALF_PERIOD,
    "second_half": SECOND_HALF_PERIOD,
    "하반기": SECOND_HALF_PERIOD,
}


def normalize_publication_kind(value: str | None) -> PublicationKind:
    kind = (value or DEFAULT_PUBLICATION_KIND).strip()
    if kind not in PUBLICATION_KINDS:
        supported = ", ".join(PUBLICATION_KINDS)
        raise ValueError(f"unsupported publication kind: {kind}; supported: {supported}")
    return kind  # type: ignore[return-value]


# 화면에서 고른 조회 범위를 정규 값으로 바꾼다. 값을 주지 않으면 두 발간물을 모두 본다.
def normalize_publication_scope(value: str | None) -> PublicationScope:
    scope = (value or DEFAULT_PUBLICATION_SCOPE).strip()
    if scope not in PUBLICATION_SCOPES:
        supported = ", ".join(PUBLICATION_SCOPES)
        raise ValueError(f"unsupported publication scope: {scope}; supported: {supported}")
    return scope  # type: ignore[return-value]


# 조회 범위를 실제로 조회할 발간물 목록으로 푼다. 전체는 두 발간물을 모두 돈다.
def scope_publication_kinds(value: str | None) -> tuple[PublicationKind, ...]:
    scope = normalize_publication_scope(value)
    if scope == ALL_PUBLICATIONS_SCOPE:
        return PUBLICATION_KINDS
    return (scope,)  # type: ignore[return-value]


# 화면과 답변에 쓸 한국어 발간물 이름을 준다.
def publication_kind_label(value: str | None) -> str:
    return PUBLICATION_KIND_LABELS[normalize_publication_kind(value)]


# 반기 표기를 저장·조회에 쓰는 정규 값으로 바꾼다. 생략하면 반기 없음이다.
def normalize_publication_period(value: str | None) -> PublicationPeriod:
    period = (value or NO_PUBLICATION_PERIOD).strip()
    normalized = _PERIOD_ALIASES.get(period.lower())
    if normalized is None:
        supported = ", ".join(name or "(없음)" for name in PUBLICATION_PERIODS)
        raise ValueError(f"unsupported publication period: {period}; supported: {supported}")
    return normalized


# 검색·비교 인자로 들어온 반기를 정규화한다. 값을 주지 않으면 반기로 좁히지 않는다.
def normalize_publication_period_filter(value: str | None) -> PublicationPeriod | None:
    if value is None:
        return None
    return normalize_publication_period(value)


# 화면과 응답에 쓸 한국어 반기 이름을 준다. 반기가 없는 발간물은 빈 문자열이다.
def publication_period_label(value: str | None) -> str:
    return PUBLICATION_PERIOD_LABELS[normalize_publication_period(value)]


# 발간판을 최신순으로 줄 세울 때 쓰는 정렬 키다. 같은 해에서는 하반기가 뒤에 온다.
def publication_period_rank(value: str | None) -> int:
    return PUBLICATION_PERIODS.index(normalize_publication_period(value))


# 두 발간물을 함께 검색하면 수치의 출처를 판까지 밝혀야 하므로 인용용 이름을 만들어 둔다.
# 예: '2026년 통계연보', '2025년 하반기 주요통계집'.
def publication_edition_label(
    kind: str | None,
    year: int | None = None,
    period: str | None = None,
) -> str:
    parts = [
        f"{year}년" if year is not None else "",
        publication_period_label(period),
        publication_kind_label(kind),
    ]
    return " ".join(part for part in parts if part)
