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


# match_key_sql이 지우는 문자를 파이썬에서도 같은 규칙으로 지운다.
def normalize_match_key(value: str) -> str:
    return MATCH_KEY_STRIP_PATTERN.sub("", value).lower()


ORGANIZATION_SQL = collapsed_text_sql("c.dept")
SOURCE_SYSTEM_SQL = collapsed_text_sql("c.source_system")
OFFICER_SQL = collapsed_text_sql("c.officer")
PHONE_SQL = "NULLIF(BTRIM(c.phone), '')"
SOURCE_URL_SQL = "NULLIF(BTRIM(c.source_url), '')"
