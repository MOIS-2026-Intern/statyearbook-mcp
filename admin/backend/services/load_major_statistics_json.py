# -*- coding: utf-8 -*-
"""Convert the parsed major-statistics JSON package into the shared load format."""
from __future__ import annotations

import json
import re

from pathlib import Path
from typing import Any

from admin.backend.services.load_parser import (
    check_units,
    markdown_row,
    records_to_markdown,
)
from utils.publication_kind import MAJOR_STATISTICS_KIND, normalize_publication_kind


RE_PHONE = re.compile(r"0\d{1,2}[-)]\s?\d{3,4}[-]\d{4}")
RE_ITEM_ID = re.compile(r"^(?P<chapter>\d+)-(?P<item>\d+)$")
RE_REFERENCE_ID = re.compile(r"^참고-(?P<item>\d+)$")
RE_TWO_DIGIT_DATE = re.compile(r"^\(?['’]?(?P<year>\d{2})\.(?P<month>\d{1,2})\.(?P<day>\d{1,2})\.?\)?$")
CONTACT_PREFIXES = ("•", "*")
CONTACT_ROLE_WORDS = (
    "과장",
    "팀장",
    "사무관",
    "서기관",
    "주무관",
    "전문관",
    "연구관",
    "연구사",
)
SKIP_PARAGRAPH_PREFIXES = ("(단위", "단위")


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _item_number(item_id: str) -> int | None:
    match = RE_ITEM_ID.match(item_id)
    if match:
        return int(match.group("item"))
    match = RE_REFERENCE_ID.match(item_id)
    if match:
        return int(match.group("item"))
    return None


def _normalize_base_date(value: object, publication_year: int) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    match = RE_TWO_DIGIT_DATE.match(text)
    if not match:
        return text.strip("()")
    year = int(match.group("year"))
    century = publication_year // 100 * 100
    full_year = century + year
    return f"{full_year}.{int(match.group('month'))}.{int(match.group('day'))}."


def _normalize_phone(value: str) -> str:
    return re.sub(r"-+", "-", value.replace(")", "-").replace(" ", "")).strip("-")


def _department_from_prefix(prefix: str) -> str | None:
    tokens = prefix.split()
    if not tokens:
        return None
    role_indexes = [
        index for index, token in enumerate(tokens)
        if any(role in token for role in CONTACT_ROLE_WORDS)
    ]
    if role_indexes and role_indexes[0] > 0:
        return " ".join(tokens[: role_indexes[0]])
    return tokens[0]


def _parse_contacts(text: str) -> list[dict]:
    body = text.lstrip("".join(CONTACT_PREFIXES)).strip()
    phones = list(RE_PHONE.finditer(body))
    if not phones:
        return []
    dept = _department_from_prefix(body[: phones[0].start()].strip())
    contacts = []
    previous_end = 0
    for phone_match in phones:
        officer = body[previous_end: phone_match.start()].strip(" (),;·")
        if dept and officer.startswith(dept):
            officer = officer[len(dept):].strip(" (),;·")
        contacts.append({
            "dept": dept,
            "officer": officer or None,
            "phone": _normalize_phone(phone_match.group(0)),
            "source_system": None,
            "source_url": None,
        })
        previous_end = phone_match.end()
    return contacts


def _is_contact_paragraph(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(CONTACT_PREFIXES) and bool(RE_PHONE.search(stripped))


def _is_date_paragraph(text: str) -> bool:
    return bool(RE_TWO_DIGIT_DATE.match(_clean_text(text)))


def _is_unit_paragraph(text: str) -> bool:
    stripped = _clean_text(text).lstrip("(")
    return stripped.startswith(SKIP_PARAGRAPH_PREFIXES)


def _footnotes_from_paragraphs(paragraphs: list[object]) -> list[dict]:
    notes = []
    for paragraph in paragraphs:
        text = _clean_text(paragraph)
        if not text or _is_date_paragraph(text) or _is_unit_paragraph(text):
            continue
        if _is_contact_paragraph(text):
            continue
        notes.append({
            "seq": len(notes) + 1,
            "note_no": None,
            "content": text,
        })
    return notes


def _contacts_from_paragraphs(paragraphs: list[object]) -> list[dict]:
    contacts = []
    seen: set[tuple[object, ...]] = set()
    for paragraph in paragraphs:
        text = _clean_text(paragraph)
        if not _is_contact_paragraph(text):
            continue
        for contact in _parse_contacts(text):
            signature = (
                contact.get("dept"),
                contact.get("officer"),
                contact.get("phone"),
            )
            if signature in seen:
                continue
            contacts.append(contact)
            seen.add(signature)
    return contacts


def _table_columns(table: dict) -> list[str]:
    columns = table.get("compact_headers") or table.get("headers") or []
    if not columns and table.get("records"):
        first = table["records"][0]
        if isinstance(first, dict):
            columns = list(first)
    if not columns and table.get("matrix"):
        columns = [f"column_{index + 1}" for index in range(len(table["matrix"][0]))]
    return [str(column) for column in columns]


def _table_records(table: dict, columns: list[str]) -> list[dict[str, str]]:
    records = table.get("compact_records") or table.get("records") or []
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            continue
        normalized.append({
            column: str(record.get(column, ""))
            for column in columns
        })
    return normalized


def _matrix_to_markdown(matrix: list[list[object]]) -> str:
    rows = [
        [str(cell or "") for cell in row]
        for row in matrix
        if any(_clean_text(cell) for cell in row)
    ]
    if not rows:
        return ""
    lines = [markdown_row(rows[0]), markdown_row(["---"] * len(rows[0]))]
    for row in rows[1:]:
        lines.append(markdown_row(row))
    return "\n".join(lines)


def _table_body(table: dict, columns: list[str], records: list[dict[str, str]]) -> dict:
    matrix = table.get("matrix") or []
    return {
        "rows": table.get("row_count"),
        "cols": table.get("column_count"),
        "columns": columns,
        "records": records,
        "grid": matrix,
        "text": table.get("text"),
        "source_table_attributes": table.get("source_table_attributes") or {},
    }


def _table_record(table: dict, seq: int) -> dict:
    columns = _table_columns(table)
    records = _table_records(table, columns)
    matrix = table.get("matrix") or []
    table_md = records_to_markdown(columns, records) or _matrix_to_markdown(matrix)
    body = _table_body(table, columns, records)
    return {
        "seq": seq,
        "caption": table.get("table_title"),
        "n_rows": table.get("row_count"),
        "n_cols": table.get("column_count"),
        "body": body,
        "table_md": table_md,
    }


def _unit_from_item(item: dict, ordinal: int, publication_year: int) -> dict:
    item_id = str(item.get("item_id") or "").strip()
    if not item_id:
        raise ValueError(f"semantic item at ordinal {ordinal} has no item_id")
    chapter_no = _int_or_none(item.get("chapter_number"))
    title = _clean_text(item.get("title")) or item_id
    tables = [
        _table_record(table, index)
        for index, table in enumerate(item.get("tables") or [], start=1)
        if isinstance(table, dict)
    ]
    item_unit = item.get("unit") or next(
        (
            table.get("unit")
            for table in item.get("tables") or []
            if isinstance(table, dict) and table.get("unit")
        ),
        None,
    )
    paragraphs = item.get("paragraphs") or []
    return {
        "ref_id": item_id,
        "ordinal": ordinal,
        "chapter_no": chapter_no,
        "section_no": None,
        "level3_no": _item_number(item_id),
        "level4_no": None,
        "chapter": _clean_text(item.get("chapter_title")) or None,
        "section": None,
        "level3_title": title,
        "level3_title_en": None,
        "level4_title": None,
        "level4_title_en": None,
        "title_ko": title,
        "title_en": None,
        "unit": _clean_text(item_unit) or None,
        "base_date": _normalize_base_date(item.get("date_text"), publication_year),
        "page_start": None,
        "tables": tables,
        "footnotes": _footnotes_from_paragraphs(paragraphs),
        "contacts": _contacts_from_paragraphs(paragraphs),
    }


def _source_title(data: dict, publication_year: int) -> str:
    source = data.get("source") or {}
    filename = _clean_text(source.get("filename"))
    if filename:
        stem = Path(filename).stem.lstrip("★").strip()
        return stem or f"{publication_year} 주요통계집"
    return f"{publication_year} 주요통계집"


def convert_major_statistics_json(
    json_path: str | Path,
    *,
    publication_year: int,
    publication_title: str | None = None,
    publication_no: str | None = None,
    publication_kind: str | None = MAJOR_STATISTICS_KIND,
) -> dict[str, Any]:
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    semantic_index = data.get("semantic_index") or {}
    items = semantic_index.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValueError("major statistics JSON has no semantic_index.items")

    units = [
        _unit_from_item(item, ordinal, publication_year)
        for ordinal, item in enumerate(items, start=1)
        if isinstance(item, dict)
    ]
    source = data.get("source") or {}
    publication = {
        "publication_kind": normalize_publication_kind(publication_kind),
        "year": publication_year,
        "pub_no": publication_no or None,
        "title": publication_title or _source_title(data, publication_year),
        "page_count": None,
    }
    return {
        "publication": publication,
        "metadata": {
            "source": str(path.resolve()),
            "parser": "admin/backend/services/load_major_statistics_json.py",
            "source_filename": source.get("filename"),
            "source_sha256": source.get("sha256"),
            "method": (
                "semantic_index.items를 현재 공통 적재 포맷의 statistics 항목으로 변환하고, "
                "각 item.tables의 compact_headers/compact_records를 stat_tables.body의 "
                "columns/records로 저장한다."
            ),
            "warnings": [],
            "validation": data.get("validation") or {},
        },
        "checks": check_units(units),
        "toc_reconciliation": {
            "toc_ref_mismatch": [],
            "toc_only_entries": [],
            "body_only_entries": [],
        },
        "statistics": units,
    }
