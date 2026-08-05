# -*- coding: utf-8 -*-
"""발간판 도구들이 공유하는 SQL 정규화와 조회 표현을 담당한다."""
from __future__ import annotations

import re


# 비교 키에서 지울 문자 집합. 두 표현은 같은 문자를 지워야 하므로 항상 함께 고친다.
MATCH_KEY_STRIP_CLASS = "[[:space:]·･‧・_/-]"
MATCH_KEY_STRIP_PATTERN = re.compile(r"[\s·･‧・_/-]")


# 앞뒤 공백을 없애고 내부 공백을 하나로 줄여 빈 문자열을 NULL로 만든다.
def collapsed_text_sql(expression: str) -> str:
    return f"NULLIF(regexp_replace(BTRIM({expression}), '\\s+', ' ', 'g'), '')"


# 대소문자만 정규화한 비교 키를 만든다. 번호처럼 구분 기호가 의미를 갖는 값에 쓴다.
def simple_key_sql(expression: str) -> str:
    return f"NULLIF(LOWER(BTRIM({expression})), '')"


# 공백과 구분 기호, 대소문자 차이를 지워 발간판 사이에서 같은 항목을 잇는 키를 만든다.
# 발간판마다 띄어쓰기와 가운뎃점 표기가 달라지므로 이름 비교는 이 키를 기준으로 한다.
def match_key_sql(expression: str) -> str:
    return (
        "NULLIF(LOWER(regexp_replace("
        f"COALESCE({expression}, ''), '{MATCH_KEY_STRIP_CLASS}', '', 'g')), '')"
    )


# 검색어를 같은 비교 키로 바꿔 부분 일치를 판정한다. 값은 %s 파라미터로 받는다.
# LIKE가 아니라 strpos를 쓰므로 검색어의 %와 _를 별도로 이스케이프할 필요가 없다.
def contains_match_key_sql(expression: str) -> str:
    return f"strpos({match_key_sql(expression)}, %s) > 0"


# 검색어 후보 중 하나라도 포함되면 일치로 본다. 같은 검색어를 여러 형태로 풀어 쓸 때 사용한다.
def contains_any_match_key_sql(expression: str, key_count: int) -> str:
    if key_count < 1:
        raise ValueError("key_count must be at least 1")
    condition = " OR ".join([contains_match_key_sql(expression)] * key_count)
    return condition if key_count == 1 else f"({condition})"


# match_key_sql이 지우는 문자를 파이썬에서도 같은 규칙으로 지운다.
def normalize_match_key(value: str) -> str:
    return MATCH_KEY_STRIP_PATTERN.sub("", value).lower()


# 담당자 값은 '주무관 홍길동'처럼 직급이 이름 앞에 붙는다. 사용자는 '홍길동 주무관',
# '홍길동주무관', '홍길동 주무관님', '홍길동씨'처럼 순서를 바꾸거나 경칭을 붙여 부르므로,
# 검색어에서 직급과 경칭을 떼어 이름만으로도 맞춰 본다. 저장값은 그대로 두므로 '주무관'처럼
# 직급 자체로 찾는 질의는 영향을 받지 않는다.
# 부서 이름에도 들어가는 '담당관'은 떼지 않는다. 부서까지 넣어 부른 검색어가 깨진다.
OFFICER_RANK_WORDS = (
    "행정실무원",
    "주무관",
    "사무관",
    "서기관",
    "전문관",
    "연구관",
    "연구사",
    "담당자",
)
OFFICER_HONORIFICS = ("님", "씨")
OFFICER_RANK_PATTERN = re.compile(
    "(?:" + "|".join(OFFICER_RANK_WORDS) + ")(?:" + "|".join(OFFICER_HONORIFICS) + ")?"
)
OFFICER_HONORIFIC_PATTERN = re.compile(
    "(?:" + "|".join(OFFICER_HONORIFICS) + r")\s*$"
)


# 담당자 검색어를 원본 키와 직급·경칭을 뗀 키로 모두 만든다.
# 원본 키를 남겨야 '행정기획과주무관 안지현'처럼 저장값을 그대로 넣은 질의도 계속 맞는다.
def officer_match_keys(value: str) -> tuple[str, ...]:
    keys = [normalize_match_key(value)]
    stripped = OFFICER_HONORIFIC_PATTERN.sub("", OFFICER_RANK_PATTERN.sub(" ", value))
    stripped_key = normalize_match_key(stripped)
    if stripped_key and stripped_key not in keys:
        keys.append(stripped_key)
    return tuple(key for key in keys if key)


ORGANIZATION_SQL = collapsed_text_sql("c.dept")
SOURCE_SYSTEM_SQL = collapsed_text_sql("c.source_system")
OFFICER_SQL = collapsed_text_sql("c.officer")
PHONE_SQL = "NULLIF(BTRIM(c.phone), '')"
SOURCE_URL_SQL = "NULLIF(BTRIM(c.source_url), '')"
