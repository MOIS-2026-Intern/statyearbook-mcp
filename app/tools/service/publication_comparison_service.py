# -*- coding: utf-8 -*-
"""발간판 비교 결과 해석과 응답 구성을 담당한다."""
from typing import Any

from app.tools.repository.publication_comparison_repository import (
    CompareField,
    CompareMatchBy,
    CompareOperation,
    CompareSubject,
    CompareSubjectSpec,
    MATCH_KEY_DEFINITIONS,
    SUBJECTS,
    _comparison_fields,
    _execute_plan,
    _limitations,
    _publication_years,
    _resolve_publication_years,
    _selected_fields,
    _source_tables,
    _validate_request,
    build_query_plan,
)


# 목록 응답에서 내부 집계 컬럼을 떼어내고 전체 건수를 회수한다.
def _split_total_count(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if not rows:
        return [], 0
    total_count = int(rows[0].get("_total_count", len(rows)))
    trimmed = [
        {key: value for key, value in row.items() if key != "_total_count"}
        for row in rows
    ]
    return trimmed, total_count


# 두 발간판의 수록 항목을 비교해 한쪽에만 있는 항목, 공통 항목과 변경 항목을 찾는다.
def compare_publications_data(
    *,
    operation: CompareOperation,
    subject: CompareSubject = "statistics",
    match_by: CompareMatchBy = "title",
    base_publication_year: int | None = None,
    target_publication_year: int | None = None,
    fields: list[CompareField] | None = None,
    compare_fields: list[CompareField] | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    _validate_request(
        operation,
        subject,
        match_by,
        fields,
        compare_fields,
        limit,
        offset,
    )
    available_years = _publication_years()
    base_year, target_year, publication_years_defaulted = _resolve_publication_years(
        base_publication_year,
        target_publication_year,
        available_years,
    )
    spec = SUBJECTS[subject]
    plan = build_query_plan(
        operation=operation,
        subject=subject,
        match_by=match_by,
        base_publication_year=base_year,
        target_publication_year=target_year,
        fields=fields,
        compare_fields=compare_fields,
        limit=limit,
        offset=offset,
    )
    rows = _execute_plan(plan)
    selected = _selected_fields(spec, fields)
    compared = _comparison_fields(spec, fields, compare_fields)

    response: dict[str, Any] = {
        "ok": True,
        "operation": operation,
        "subject": subject,
        "match_by": match_by,
        "match_key_definition": (
            f"{spec.definition}을(를) {MATCH_KEY_DEFINITIONS[match_by]}으로 잇는다"
        ),
        "requested_base_publication_year": base_publication_year,
        "requested_target_publication_year": target_publication_year,
        "base_publication_year": base_year,
        "target_publication_year": target_year,
        "publication_years_defaulted": publication_years_defaulted,
        "available_publication_years": available_years,
        "selected_fields": list(selected),
        "compared_fields": list(compared),
        "definition": _definition(operation, spec, base_year, target_year),
        "basis": (
            f"{base_year}년판과 {target_year}년판의 {spec.unit_label}을(를) "
            f"{MATCH_KEY_DEFINITIONS[match_by]} 기준으로 대응시킨 뒤 집합을 비교"
        ),
        "record_count_meaning": spec.record_count_note,
        "limitations": _limitations(subject, match_by, fields, compare_fields),
        "source_tables": list(_source_tables(spec, fields, compare_fields)),
    }

    if operation == "summary":
        summary = rows[0] if rows else {}
        response["result_count"] = 1 if rows else 0
        response["results"] = rows
        response["base"] = {
            "publication_year": base_year,
            "item_count": int(summary.get("base_item_count", 0)),
            "record_count": int(summary.get("base_record_count", 0)),
            "duplicate_key_count": int(summary.get("base_duplicate_key_count", 0)),
        }
        response["target"] = {
            "publication_year": target_year,
            "item_count": int(summary.get("target_item_count", 0)),
            "record_count": int(summary.get("target_record_count", 0)),
            "duplicate_key_count": int(summary.get("target_duplicate_key_count", 0)),
        }
        for key in (
            "only_in_base_count",
            "only_in_target_count",
            "in_both_count",
            "changed_count",
        ):
            response[key] = int(summary.get(key, 0))
        return response

    rows, total_count = _split_total_count(rows)
    response["result_count"] = len(rows)
    response["results"] = rows
    response["total_count"] = total_count
    response["offset"] = offset
    response["limit"] = limit
    response["truncated"] = offset + len(rows) < total_count
    response["next_offset"] = offset + len(rows) if response["truncated"] else None
    return response


# 응답에 담을 operation 설명을 두 발간연도로 채운다.
def _definition(
    operation: str,
    spec: CompareSubjectSpec,
    base_year: int,
    target_year: int,
) -> str:
    subject_label = f"{spec.definition}({spec.unit_label})"
    if operation == "summary":
        return f"{base_year}년판과 {target_year}년판의 {subject_label} 비교 요약"
    if operation == "only_in_base":
        return f"{base_year}년판에만 있고 {target_year}년판에는 없는 {subject_label}"
    if operation == "only_in_target":
        return f"{target_year}년판에만 있고 {base_year}년판에는 없는 {subject_label}"
    if operation == "changed":
        return (
            f"{base_year}년판과 {target_year}년판에 모두 있으나 "
            f"비교 필드 값이 달라진 {subject_label}"
        )
    return f"{base_year}년판과 {target_year}년판에 모두 있는 {subject_label}"
