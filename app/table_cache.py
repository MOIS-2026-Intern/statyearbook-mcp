# -*- coding: utf-8 -*-
from collections import OrderedDict
from copy import deepcopy
from uuid import uuid4


MAX_CACHED_TABLES = 128
_TABLES: OrderedDict[str, dict] = OrderedDict()


# 현재 MCP 프로세스에서 다시 사용할 수 있도록 원본 표를 캐시한다.
def cache_table(table: dict) -> str:
    handle = f"table_{table['stat_id']}_{table['table_seq']}_{uuid4().hex}"
    _TABLES[handle] = deepcopy(table)
    _TABLES.move_to_end(handle)
    while len(_TABLES) > MAX_CACHED_TABLES:
        _TABLES.popitem(last=False)
    return handle


# 캐시된 표를 호출자가 변경하지 못하도록 복사해 반환한다.
def get_cached_table(handle: str) -> dict | None:
    table = _TABLES.get(handle)
    if table is None:
        return None
    _TABLES.move_to_end(handle)
    return deepcopy(table)


# 테스트에서 프로세스 전역 캐시 상태를 격리한다.
def clear_table_cache() -> None:
    _TABLES.clear()
