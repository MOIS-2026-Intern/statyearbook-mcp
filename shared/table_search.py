# -*- coding: utf-8 -*-
"""표 머리글과 비수치 분류값을 검색 가능한 작은 문서로 정규화한다."""
from __future__ import annotations

import re


DEFAULT_CHUNK_MAX_CHARS = 800
_LETTER_RE = re.compile(r"[A-Za-z가-힣]")
_SPACE_RE = re.compile(r"\s+")


def normalize_search_label(value: object) -> str:
    """HWPX 셀의 줄바꿈과 반복 공백을 검색에 적합한 한 줄로 만든다."""
    if value is None:
        return ""
    return _SPACE_RE.sub(" ", str(value)).strip()


def _unique_labels(values: list[object]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for value in values:
        label = normalize_search_label(value)
        key = label.casefold()
        if label and key not in seen:
            labels.append(label)
            seen.add(key)
    return labels


def _context_text(statistic: dict) -> str:
    parts = _unique_labels([
        statistic.get("chapter"),
        statistic.get("section"),
        statistic.get("level3_title"),
        statistic.get("level4_title"),
        statistic.get("title_ko"),
        statistic.get("title_en"),
    ])
    return " ".join(parts)


def _column_labels(table: dict) -> list[str]:
    body = table.get("body") or {}
    columns = body.get("columns") or []
    if not columns:
        records = body.get("records") or []
        if records and isinstance(records[0], dict):
            columns = list(records[0])
    return _unique_labels(list(columns))


def _categorical_labels(table: dict, columns: list[str]) -> list[str]:
    """순수 숫자·날짜는 버리고 문자가 포함된 행/분류값만 남긴다."""
    body = table.get("body") or {}
    values: list[object] = []
    for record in body.get("records") or []:
        if not isinstance(record, dict):
            continue
        values.extend(record.values())
    column_keys = {label.casefold() for label in columns}
    return [
        label
        for label in _unique_labels(values)
        if _LETTER_RE.search(label) and label.casefold() not in column_keys
    ]


def _chunk_labels(labels: list[str], max_chars: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for label in labels:
        extra = len(label) + (3 if current else 0)
        if current and current_chars + extra > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(label)
        current_chars += len(label) + (3 if len(current) > 1 else 0)
    if current:
        chunks.append(current)
    return chunks


def build_table_search_chunks(
    statistic: dict,
    table: dict,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
) -> list[dict]:
    """한 원자료 표를 머리글 1개와 분류값 N개의 검색 청크로 만든다."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    context = _context_text(statistic)
    columns = _column_labels(table)
    chunks: list[dict] = []
    if columns:
        header_text = "컬럼: " + " | ".join(columns)
        chunks.append({
            "chunk_no": 1,
            "chunk_kind": "headers",
            "search_labels": columns,
            "search_text": f"{context} {header_text}".strip(),
        })

    categorical = _categorical_labels(table, columns)
    for index, labels in enumerate(_chunk_labels(categorical, max_chars), start=1):
        label_text = "항목: " + " | ".join(labels)
        chunks.append({
            "chunk_no": index,
            "chunk_kind": "labels",
            "search_labels": labels,
            "search_text": f"{context} {label_text}".strip(),
        })
    return chunks
