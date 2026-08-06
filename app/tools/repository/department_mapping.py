# -*- coding: utf-8 -*-
"""담당 부서의 약칭·옛 이름을 현재 이름으로 잇는 대조표를 담당한다."""
from __future__ import annotations

from app.tools.repository.publication_repository import normalize_match_key


# 부서 약칭은 관행이라 이름에서 규칙으로 끌어낼 수 없다. '국정자원'은 음절을 골라 줄인
# 것이고 '정부통합전산센터'는 개편 전 이름이라, 어느 쪽도 현재 이름의 부분 문자열이 아니다.
# 그래서 기관마다 사용자가 부를 법한 이름을 적어 둔다.
# 현재 이름에 그대로 들어 있는 표현은 적지 않는다. '인재개발원'은 '지방자치인재개발원'의
# 부분 문자열이라 조건을 늘리지 않아도 이미 찾힌다.
# 과·담당관실은 약칭 없이 온전한 이름으로 부르므로 소속기관만 적는다.
# 개편으로 이름이 바뀌면 키를 현재 이름으로 옮기고 옛 이름을 값으로 내린다.
DEPARTMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "국가기록원": ("정부기록보존소",),
    "국가재난안전교육원": ("국가민방위재난안전교육원", "민방위교육원", "재난교육원",),
    "국가정보자원관리원": ("국정자원", "정부통합전산센터"),
    "국립과학수사연구원": ("국과수", "국립과학수사연구소", "과수사",),
    "국립재난안전연구원": ("국립방재연구원", "국립방재연구소", "재난안전연구원", "재난연구원",),
    "정부청사관리본부": ("정부청사관리소", "관리본부", "청사관리본부",),
    "주민등록번호변경위원회": ("주민번호변경위원회", "주민번호변경위", ),
    "지방자치인재개발원": ("지방행정연수원", "인재개발원",),
}
# 약칭을 비교 키로 바로 찾도록 뒤집어 둔다. 나중에 DB 테이블로 옮기더라도 이 사전을 채우는
# 방법만 바뀌고 아래 조회는 그대로 쓴다.
DEPARTMENT_ALIAS_KEYS: dict[str, str] = {
    normalize_match_key(alias): normalize_match_key(name)
    for name, aliases in DEPARTMENT_ALIASES.items()
    for alias in aliases
}


# 부서 검색어를 원본 키와, 약칭이면 그 기관의 현재 이름 키로 만든다.
# 원본 키를 남겨야 저장값이 약칭을 그대로 담고 있는 경우도 계속 맞는다.
# 적어 두지 않은 이름은 원본 키만 남아 적기 전과 같은 결과가 된다.
def department_match_keys(value: str) -> tuple[str, ...]:
    key = normalize_match_key(value)
    if not key:
        return ()
    full_name_key = DEPARTMENT_ALIAS_KEYS.get(key)
    if not full_name_key or full_name_key == key:
        return (key,)
    return (key, full_name_key)
