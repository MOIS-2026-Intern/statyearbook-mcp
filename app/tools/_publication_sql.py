# -*- coding: utf-8 -*-
"""발간판을 다루는 도구들이 공유하는 SQL 정규화 조각."""
from __future__ import annotations


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
        f"COALESCE({expression}, ''), '[[:space:]·･‧・_/-]', '', 'g')), '')"
    )


ORGANIZATION_SQL = collapsed_text_sql("c.dept")
SOURCE_SYSTEM_SQL = collapsed_text_sql("c.source_system")
OFFICER_SQL = collapsed_text_sql("c.officer")
PHONE_SQL = "NULLIF(BTRIM(c.phone), '')"
SOURCE_URL_SQL = "NULLIF(BTRIM(c.source_url), '')"
