# -*- coding: utf-8 -*-
"""통계연보 집계 결과 해석과 응답 구성을 담당한다."""
from typing import Any

from app.tools.repository.publication_analysis_repository import (
    AnalysisField,
    AnalysisGroup,
    AnalysisOperation,
    AnalysisSubject,
    FIELDS,
    LISTS,
    METRICS,
    _execute_plan,
    _resolve_publication_scope,
    _resolve_value_filters,
    _validate_request,
    build_query_plan,
)

# 결과가 비었는지 판정한다. count는 행이 아니라 집계값이 0인지를 본다.
def _is_empty_result(operation: str, rows: list[dict[str, Any]]) -> bool:
    if operation == "count":
        return not rows or not int(rows[0].get("count") or 0)
    return not rows


# 전체 발간판으로 넓혀 다시 조회할 수 있는 호출인지 판단한다.
# 담당자와 담당 부서는 발간판마다 바뀌므로 최신판에만 없는 이름을 구판에서 찾아준다.
def _can_relax_publication_year(
    applied_publication_year: int | None,
    all_publication_years: bool,
    offset: int,
) -> bool:
    if applied_publication_year is None or all_publication_years:
        return False
    # 페이지를 넘기는 중이면 앞 페이지와 범위가 달라지므로 넓히지 않는다.
    return offset == 0


# 넓혀 조회한 결과의 발간판을 답변에서 밝힐 수 있도록 발간연도를 목록에 넣는다.
def _fields_with_publication_year(
    subject: str,
    fields: list[AnalysisField] | None,
) -> list[AnalysisField]:
    selected = list(fields if fields is not None else LISTS[subject].default_fields)
    if "publication_year" in selected:
        return selected
    return ["publication_year", *selected]


# 적용한 발간판 범위를 모델이 그대로 인용할 수 있는 안내 문구로 만든다.
def _publication_scope_message(
    attempted_publication_year: int | None,
    publication_year_defaulted: bool,
    filter_relaxed: bool,
) -> str | None:
    if attempted_publication_year is None:
        return None
    source = (
        f"발간연도를 지정하지 않아 최신 발간판인 {attempted_publication_year}년판을 먼저 조회했으나"
        if publication_year_defaulted
        else f"{attempted_publication_year}년 발간판에는"
    )
    if filter_relaxed:
        return (
            f"{source} 결과가 없어 전체 발간판에서 다시 조회했습니다. "
            "각 결과의 publication_year가 실제 발간판입니다."
        )
    return (
        f"{source} 결과가 없었고, 전체 발간판을 다시 조회해도 결과가 없습니다."
    )


# 현재 스키마 위에서 연보 단위 기초통계 또는 전체 메타데이터 목록을 조회한다.
def analyze_publications_data(
    *,
    operation: AnalysisOperation,
    subject: AnalysisSubject = "statistics",
    group_by: AnalysisGroup | None = None,
    distinct_field: AnalysisField | None = None,
    fields: list[AnalysisField] | None = None,
    required_fields: list[AnalysisField] | None = None,
    value_filters: list[dict[str, str]] | None = None,
    deduplicate: bool | None = None,
    publication_year: int | None = None,
    all_publication_years: bool = False,
    chapter_no: int | None = None,
    section_no: int | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    _validate_request(
        operation,
        subject,
        group_by,
        distinct_field,
        fields,
        required_fields,
        deduplicate,
        publication_year,
        all_publication_years,
        chapter_no,
        section_no,
        limit,
        offset,
    )
    applied_value_filters = _resolve_value_filters(operation, subject, value_filters)
    applied_publication_year, publication_year_defaulted = (
        _resolve_publication_scope(publication_year, all_publication_years)
    )
    applied_fields = fields
    plan = build_query_plan(
        operation=operation,
        subject=subject,
        group_by=group_by,
        distinct_field=distinct_field,
        applied_publication_year=applied_publication_year,
        chapter_no=chapter_no,
        section_no=section_no,
        limit=limit,
        fields=applied_fields,
        required_fields=required_fields,
        deduplicate=deduplicate,
        offset=offset,
        value_filters=applied_value_filters,
    )
    rows = _execute_plan(plan)

    # 한 발간판에서 결과가 없으면 전체 발간판으로 넓혀 한 번만 다시 조회한다.
    attempted_publication_year = applied_publication_year
    publication_year_filter_relaxed = False
    scope_message: str | None = None
    if _is_empty_result(operation, rows) and _can_relax_publication_year(
        applied_publication_year,
        all_publication_years,
        offset,
    ):
        relaxed_fields = (
            _fields_with_publication_year(subject, fields)
            if operation == "list"
            else applied_fields
        )
        relaxed_plan = build_query_plan(
            operation=operation,
            subject=subject,
            group_by=group_by,
            distinct_field=distinct_field,
            applied_publication_year=None,
            chapter_no=chapter_no,
            section_no=section_no,
            limit=limit,
            fields=relaxed_fields,
            required_fields=required_fields,
            deduplicate=deduplicate,
            offset=offset,
            value_filters=applied_value_filters,
        )
        relaxed_rows = _execute_plan(relaxed_plan)
        publication_year_filter_relaxed = not _is_empty_result(operation, relaxed_rows)
        # 넓혀도 결과가 없으면 원래 발간판 기준 응답을 그대로 둔다.
        if publication_year_filter_relaxed:
            plan = relaxed_plan
            rows = relaxed_rows
            applied_fields = relaxed_fields
            applied_publication_year = None
        scope_message = _publication_scope_message(
            attempted_publication_year,
            publication_year_defaulted,
            publication_year_filter_relaxed,
        )

    metric = METRICS[subject]
    selected_fields: list[str] | None = None
    applied_required_fields: list[str] | None = None
    deduplicated: bool | None = None
    total_count: int | None = None
    if operation == "list":
        list_spec = LISTS[subject]
        selected_fields = list(
            dict.fromkeys(
                applied_fields if applied_fields is not None else list_spec.default_fields
            )
        )
        applied_required_fields = list(dict.fromkeys(required_fields or ()))
        deduplicated = (
            list_spec.deduplicate_default
            if deduplicate is None
            else deduplicate
        )
        total_count = int(rows[0].get("_total_count", len(rows))) if rows else 0
        rows = [
            {key: value for key, value in row.items() if key != "_total_count"}
            for row in rows
        ]
    filters = {
        key: value
        for key, value in {
            "publication_year": applied_publication_year,
            "chapter_no": chapter_no,
            "section_no": section_no,
        }.items()
        if value is not None
    }
    if operation == "overview":
        response_subject: str | None = None
        definition = "발간판 메타데이터와 현재 DB 스키마에서 계산 가능한 주요 기초통계"
        basis = (
            "publications를 기준으로 statistics.stat_id, stat_tables.table_id, 장·절 번호, "
            "contacts.dept와 contacts.source_system을 각각 DISTINCT 집계"
        )
        limitations = (
            "통계 수는 목차 원본이 아니라 현재 DB에 적재된 파싱 결과 기준",
            "tables_count는 논리 통계 수가 아니라 물리 표 레코드 수",
            "organizations_count는 공식 제출기관이 아니라 contacts.dept 담당 부서 수",
        )
    elif operation == "list":
        response_subject = subject
        definition = LISTS[subject].definition
        duplicate_basis = (
            "선택한 필드 조합의 중복을 제거"
            if deduplicated
            else "연결된 레코드를 중복 제거하지 않고 유지"
        )
        basis = f"{LISTS[subject].basis}; {duplicate_basis}"
        limitations = metric.limitations
    elif distinct_field is not None:
        alias = FIELDS[distinct_field].alias
        response_subject = subject
        if group_by is None:
            definition = f"{subject} 범위에서 {alias} 필드의 중복 없는 값 종류 수"
            basis = (
                f"선택한 발간연도의 {subject}에 연결된 DISTINCT {alias}; "
                "값이 비어 있는 행은 제외하며 레코드 수가 아니라 값의 가짓수"
            )
            limitations = metric.limitations
        else:
            definition = f"{group_by}별 {alias} 필드의 중복 없는 값 종류 수"
            basis = (
                f"선택한 발간연도의 {subject}를 {group_by} 기준으로 묶고 그룹마다 "
                f"DISTINCT {alias}를 집계; 값이 비어 있는 행은 제외"
            )
            limitations = (
                *metric.limitations,
                f"같은 {alias} 값이 여러 그룹에 걸쳐 있으면 그룹마다 각각 세므로 "
                "그룹 count의 합은 전체 값 종류 수보다 클 수 있다",
            )
    else:
        response_subject = subject
        definition = metric.definition
        basis = metric.basis
        limitations = metric.limitations

    # 값 조건은 어떤 operation이든 산출 근거에 함께 드러낸다.
    # 담당자처럼 검색어를 여러 형태로 푼 조건은 저장값이 검색어를 그대로 담고 있지 않으므로,
    # 무엇을 무시하고 맞췄는지까지 밝혀야 모델이 근거를 정확히 인용한다.
    if applied_value_filters:
        conditions = ", ".join(
            f"{FIELDS[item.field].alias}에 '{item.contains}' 포함"
            + ("(직급·경칭 표기는 무시)" if len(item.match_keys) > 1 else "")
            for item in applied_value_filters
        )
        basis = f"{basis}; {conditions} 조건을 만족하는 행만 대상으로 한다"
    if publication_year_filter_relaxed:
        basis = (
            f"{basis}; {attempted_publication_year}년 발간판에 결과가 없어 "
            "전체 발간판을 대상으로 다시 조회했다"
        )

    response: dict[str, Any] = {
        "ok": True,
        "operation": operation,
        "subject": response_subject,
        "group_by": group_by,
        "distinct_field": distinct_field,
        "selected_fields": selected_fields,
        "required_fields": applied_required_fields,
        "value_filters": [
            {"field": item.field, "contains": item.contains}
            for item in applied_value_filters
        ],
        "deduplicated": deduplicated,
        "requested_publication_year": publication_year,
        "applied_publication_year": applied_publication_year,
        "publication_year_defaulted": publication_year_defaulted,
        "publication_year_filter_relaxed": publication_year_filter_relaxed,
        "all_publication_years": all_publication_years,
        "message": scope_message,
        "filters": filters,
        "definition": definition,
        "basis": basis,
        "limitations": list(limitations),
        "source_tables": list(plan.source_tables),
        "result_count": len(rows),
        "results": rows,
    }
    if operation == "count":
        response["count"] = int(rows[0]["count"]) if rows else 0
        response["matched_publications"] = (
            int(rows[0]["matched_publications"]) if rows else 0
        )
    if operation == "list":
        response["total_count"] = total_count
        response["offset"] = offset
        response["limit"] = limit
        response["truncated"] = offset + len(rows) < (total_count or 0)
        response["next_offset"] = (
            offset + len(rows) if response["truncated"] else None
        )
    return response
