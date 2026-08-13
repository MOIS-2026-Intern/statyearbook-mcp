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
