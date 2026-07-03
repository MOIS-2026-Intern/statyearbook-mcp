# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


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


def json_dumps(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, default=str)


def parse_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}

    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return parsed


def truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value

    omitted = len(value) - max_chars
    return f"{value[:max_chars]}\n\n...[truncated {omitted} chars]"


def truncate_jsonable(value: Any, max_chars: int) -> Any:
    dumped = json_dumps(value)
    if len(dumped) <= max_chars:
        return value
    return {
        "truncated": True,
        "max_chars": max_chars,
        "preview": truncate_text(dumped, max_chars),
    }


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
