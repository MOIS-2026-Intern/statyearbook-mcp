# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


# SDK 객체와 파이썬 컬렉션을 JSON으로 직렬화 가능한 값으로 재귀적 변환한다.
def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)

    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)

    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_jsonable(item) for item in value]

    return str(value)


# 임의의 MCP 결과를 한글을 보존하는 JSON 문자열로 변환한다.
def json_dumps(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, default=str)


# 문자열 인자를 JSON object로 파싱하고 다른 형식은 거부한다.
def parse_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}

    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return parsed


# 긴 텍스트를 지정 길이로 잘라 생략된 문자 수를 표시한다.
def truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value

    omitted = len(value) - max_chars
    return f"{value[:max_chars]}\n\n...[truncated {omitted} chars]"


# 잘렸다고 알리는 표시 자체가 차지하는 자리로, 남길 예산을 이보다 좁히지 않는다.
_MARK_CHARS = 48

# 예산을 줄여가며 다시 시도할 횟수. 몫 계산이 남기는 오차를 흡수한다.
_SHRINK_ATTEMPTS = 3


# 값 하나가 JSON에서 차지하는 길이를 잰다.
def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


# 줄일 수 없는 값을 자리 표시로 바꾸되 얼마나 사라졌는지는 남긴다.
def _omitted(value: Any) -> dict[str, Any]:
    return {"truncated": True, "omitted_chars": _json_size(value)}


# 앞에서부터 예산에 담기는 만큼만 남기고 못 담은 개수를 알린다.
def _shrink_list(items: list, budget: int) -> list:
    kept: list = []
    used = 2
    for item in items:
        size = _json_size(item) + 1
        if used + size > budget - _MARK_CHARS:
            break
        kept.append(item)
        used += size

    omitted = len(items) - len(kept)
    if omitted:
        kept.append({"truncated": True, "omitted_items": omitted})
    return kept


# 키는 모두 남기고 예산을 작은 값부터 나눠 준다. 작은 값이 먼저 제 몫만 쓰고 남긴 여유가
# 뒤로 넘어가므로, 덩치 큰 값 하나 때문에 나머지 필드가 통째로 사라지지 않는다.
def _shrink_dict(mapping: dict, budget: int) -> dict[str, Any]:
    entries = sorted(mapping.items(), key=lambda entry: _json_size(entry[1]))
    remaining = budget - _json_size(dict.fromkeys(mapping))
    shrunk: dict[str, Any] = {}

    for position, (key, item) in enumerate(entries):
        share = remaining // (len(entries) - position)
        size = _json_size(item)
        if size <= share:
            shrunk[key] = item
            remaining -= size
            continue
        shrunk[key] = _shrink(item, max(share, _MARK_CHARS))
        remaining -= _json_size(shrunk[key])

    return {key: shrunk[key] for key in mapping}


# 값의 종류에 맞는 방법으로 예산 안에 들어오도록 줄인다.
def _shrink(value: Any, budget: int) -> Any:
    if _json_size(value) <= budget:
        return value
    if isinstance(value, str):
        return truncate_text(value, max(budget - _MARK_CHARS, 0))
    if isinstance(value, list):
        return _shrink_list(value, budget)
    if isinstance(value, dict):
        return _shrink_dict(value, budget)
    return _omitted(value)


# JSON 표현이 크기 한도를 넘으면 바깥 구조는 남기고 큰 값부터 줄인다.
# 통째로 미리보기 문자열로 바꾸면 프런트엔드가 trace에서 읽어야 할 필드까지 사라진다.
def truncate_jsonable(value: Any, max_chars: int) -> Any:
    payload = to_jsonable(value)
    if max_chars <= 0 or _json_size(payload) <= max_chars:
        return payload

    budget = max_chars
    for _ in range(_SHRINK_ATTEMPTS):
        shrunk = _shrink(payload, budget)
        if _json_size(shrunk) <= max_chars:
            return shrunk
        budget = budget * 3 // 4

    return {
        "truncated": True,
        "max_chars": max_chars,
        "preview": truncate_text(json_dumps(payload), max_chars),
    }


# MCP 결과를 JSON으로 바꾸고 인라인 이미지 바이트를 trace에서 제거한다.
def sanitize_mcp_result(value: Any) -> dict[str, Any]:
    payload = to_jsonable(value)
    if not isinstance(payload, dict):
        return {"content": payload}

    content = payload.get("content") or []
    sanitized_content: list[Any] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "image":
            sanitized_content.append(
                {
                    "type": "image",
                    "mimeType": item.get("mimeType") or item.get("mime_type") or "image/png",
                    "omitted": True,
                    "reason": "inline image bytes are omitted from REST trace and model context",
                }
            )
        else:
            sanitized_content.append(item)

    payload["content"] = sanitized_content
    return payload
