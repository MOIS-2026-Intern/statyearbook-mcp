# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.db import connect
from app.tool_descriptions import (
    ANALYZE_PUBLICATIONS,
    ANALYZE_PUBLICATIONS_FIELDS,
    VALUE_FILTER_FIELDS,
)
from app.tools._publication_sql import (
    OFFICER_SQL,
    ORGANIZATION_SQL,
    PHONE_SQL,
    SOURCE_SYSTEM_SQL,
    SOURCE_URL_SQL,
    contains_match_key_sql,
    normalize_match_key,
)


AnalysisOperation = Literal["overview", "count", "breakdown", "list"]
AnalysisSubject = Literal[
    "statistics",
    "tables",
    "chapters",
    "sections",
    "organizations",
    "source_systems",
    "publications",
    "contacts",
    "footnotes",
]
AnalysisGroup = Literal[
    "publication_year",
    "chapter",
    "section",
    "organization",
    "source_system",
]
AnalysisField = Literal[
    "publication_year",
    "publication_title",
    "publication_page_count",
    "stat_id",
    "ref_id",
    "chapter_no",
    "chapter",
    "section_no",
    "section",
    "level3_title",
    "level4_title",
    "statistic_title",
    "unit",
    "base_date",
    "page_start",
    "table_id",
    "table_seq",
    "table_caption",
    "row_count",
    "column_count",
    "contact_id",
    "department",
    "officer",
    "phone",
    "source_system",
    "source_url",
    "note_id",
    "note_seq",
    "note_no",
    "note",
]

LATEST_PUBLICATION_YEAR_SQL = "SELECT MAX(year) AS publication_year FROM publications"


@dataclass(frozen=True)
class MetricSpec:
    expression: str
    definition: str
    basis: str
    source_tables: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    requires_tables: bool = False
    requires_contacts: bool = False
    requires_footnotes: bool = False


@dataclass(frozen=True)
class GroupSpec:
    select_sql: str
    group_sql: str
    nonempty_sql: str | None
    order_sql: str
    requires_contacts: bool = False


@dataclass(frozen=True)
class FieldSpec:
    expression: str
    alias: str
    nonempty_sql: str | None = None


@dataclass(frozen=True)
class ListSpec:
    default_fields: tuple[str, ...]
    allowed_fields: frozenset[str]
    row_filter_sql: str
    definition: str
    basis: str
    filter_fields: frozenset[str] = frozenset()
    deduplicate_default: bool = False


@dataclass(frozen=True)
class QueryPlan:
    sql: str
    params: tuple[Any, ...]
    source_tables: tuple[str, ...]


@dataclass(frozen=True)
class AppliedValueFilter:
    field: str
    contains: str
    match_key: str


class ValueFilter(BaseModel):
    field: AnalysisField = Field(description=VALUE_FILTER_FIELDS["field"])
    contains: str = Field(description=VALUE_FILTER_FIELDS["contains"])


METRICS: dict[str, MetricSpec] = {
    "statistics": MetricSpec(
        expression="COUNT(DISTINCT s.stat_id)",
        definition="파싱되어 statistics에 저장된 논리 통계 항목 수",
        basis="선택한 발간연도의 DISTINCT statistics.stat_id",
        source_tables=("publications", "statistics"),
        limitations=(
            "목차 엔트리 원본을 별도 집계한 값이 아니라 현재 DB에 적재된 파싱 결과 기준",
        ),
    ),
    "tables": MetricSpec(
        expression="COUNT(DISTINCT t.table_id)",
        definition="DB에 저장된 물리 통계표 레코드 수",
        basis="선택한 발간연도의 DISTINCT stat_tables.table_id; 한 통계 항목이 여러 표 조각을 가질 수 있음",
        source_tables=("publications", "statistics", "stat_tables"),
        limitations=(
            "논리 통계 항목 수가 아니라 분할 저장된 물리 표 레코드 수",
        ),
        requires_tables=True,
    ),
    "chapters": MetricSpec(
        expression=(
            "COUNT(DISTINCT (s.year, s.chapter_no)) "
            "FILTER (WHERE s.chapter_no IS NOT NULL)"
        ),
        definition="통계 항목에 연결된 고유 장 수",
        basis="선택한 발간연도의 DISTINCT (year, chapter_no)",
        source_tables=("publications", "statistics"),
    ),
    "sections": MetricSpec(
        expression=(
            "COUNT(DISTINCT (s.year, s.chapter_no, s.section_no)) "
            "FILTER (WHERE s.chapter_no IS NOT NULL AND s.section_no IS NOT NULL)"
        ),
        definition="통계 항목에 연결된 고유 절 수",
        basis="선택한 발간연도의 DISTINCT (year, chapter_no, section_no)",
        source_tables=("publications", "statistics"),
    ),
    "organizations": MetricSpec(
        expression=f"COUNT(DISTINCT {ORGANIZATION_SQL})",
        definition="통계표 출처 문단에서 파싱된 고유 담당 부서 수",
        basis="contacts.dept를 공백 정규화한 DISTINCT 값; 공식 제출기관 목록이 별도 저장된 값은 아님",
        source_tables=("publications", "statistics", "contacts"),
        limitations=(
            "공식 제출기관 명부가 아니라 각 통계표 출처 문단에서 파싱한 담당 부서 기준",
        ),
        requires_contacts=True,
    ),
    "source_systems": MetricSpec(
        expression=f"COUNT(DISTINCT {SOURCE_SYSTEM_SQL})",
        definition="통계표 출처 문단에서 파싱된 고유 출처 시스템 수",
        basis="contacts.source_system을 공백 정규화한 DISTINCT 값",
        source_tables=("publications", "statistics", "contacts"),
        requires_contacts=True,
    ),
    "publications": MetricSpec(
        expression="COUNT(DISTINCT p.pub_id)",
        definition="DB에 적재된 통계연보 발간판 수",
        basis="DISTINCT publications.pub_id",
        source_tables=("publications",),
    ),
    "contacts": MetricSpec(
        expression="COUNT(DISTINCT c.contact_id)",
        definition="통계 항목에 연결된 연락처 레코드 수",
        basis="선택한 발간연도의 고유 연락처 레코드",
        source_tables=("publications", "statistics", "contacts"),
        requires_contacts=True,
    ),
    "footnotes": MetricSpec(
        expression="COUNT(DISTINCT f.note_id)",
        definition="통계 항목에 연결된 주석 레코드 수",
        basis="선택한 발간연도의 고유 주석 레코드",
        source_tables=("publications", "statistics", "footnotes"),
        requires_footnotes=True,
    ),
}

GROUPS: dict[str, GroupSpec] = {
    "publication_year": GroupSpec(
        select_sql="p.year AS publication_year",
        group_sql="p.year",
        nonempty_sql=None,
        order_sql="p.year DESC",
    ),
    "chapter": GroupSpec(
        select_sql="s.chapter_no, MIN(s.chapter) AS chapter",
        group_sql="s.chapter_no",
        nonempty_sql="s.chapter_no IS NOT NULL",
        order_sql="s.chapter_no",
    ),
    "section": GroupSpec(
        select_sql=(
            "s.chapter_no, s.section_no, MIN(s.section) AS section"
        ),
        group_sql="s.chapter_no, s.section_no",
        nonempty_sql="s.chapter_no IS NOT NULL AND s.section_no IS NOT NULL",
        order_sql="s.chapter_no, s.section_no",
    ),
    "organization": GroupSpec(
        select_sql=f"{ORGANIZATION_SQL} AS organization",
        group_sql=ORGANIZATION_SQL,
        nonempty_sql=f"{ORGANIZATION_SQL} IS NOT NULL",
        order_sql="organization",
        requires_contacts=True,
    ),
    "source_system": GroupSpec(
        select_sql=f"{SOURCE_SYSTEM_SQL} AS source_system",
        group_sql=SOURCE_SYSTEM_SQL,
        nonempty_sql=f"{SOURCE_SYSTEM_SQL} IS NOT NULL",
        order_sql="source_system",
        requires_contacts=True,
    ),
}

FIELDS: dict[str, FieldSpec] = {
    "publication_year": FieldSpec("p.year", "publication_year"),
    "publication_title": FieldSpec("p.title", "publication_title"),
    "publication_page_count": FieldSpec(
        "p.page_count",
        "publication_page_count",
        "p.page_count IS NOT NULL",
    ),
    "stat_id": FieldSpec("s.stat_id", "stat_id", "s.stat_id IS NOT NULL"),
    "ref_id": FieldSpec("s.ref_id", "ref_id", "NULLIF(BTRIM(s.ref_id), '') IS NOT NULL"),
    "chapter_no": FieldSpec(
        "s.chapter_no",
        "chapter_no",
        "s.chapter_no IS NOT NULL",
    ),
    "chapter": FieldSpec(
        "s.chapter",
        "chapter",
        "NULLIF(BTRIM(s.chapter), '') IS NOT NULL",
    ),
    "section_no": FieldSpec(
        "s.section_no",
        "section_no",
        "s.section_no IS NOT NULL",
    ),
    "section": FieldSpec(
        "s.section",
        "section",
        "NULLIF(BTRIM(s.section), '') IS NOT NULL",
    ),
    "level3_title": FieldSpec(
        "s.level3_title",
        "level3_title",
        "NULLIF(BTRIM(s.level3_title), '') IS NOT NULL",
    ),
    "level4_title": FieldSpec(
        "s.level4_title",
        "level4_title",
        "NULLIF(BTRIM(s.level4_title), '') IS NOT NULL",
    ),
    "statistic_title": FieldSpec("s.title_ko", "statistic_title"),
    "unit": FieldSpec("s.unit", "unit", "NULLIF(BTRIM(s.unit), '') IS NOT NULL"),
    "base_date": FieldSpec(
        "s.base_date",
        "base_date",
        "NULLIF(BTRIM(s.base_date), '') IS NOT NULL",
    ),
    "page_start": FieldSpec(
        "s.page_start",
        "page_start",
        "s.page_start IS NOT NULL",
    ),
    "table_id": FieldSpec("t.table_id", "table_id", "t.table_id IS NOT NULL"),
    "table_seq": FieldSpec("t.seq", "table_seq", "t.seq IS NOT NULL"),
    "table_caption": FieldSpec(
        "t.caption",
        "table_caption",
        "NULLIF(BTRIM(t.caption), '') IS NOT NULL",
    ),
    "row_count": FieldSpec("t.n_rows", "row_count", "t.n_rows IS NOT NULL"),
    "column_count": FieldSpec(
        "t.n_cols",
        "column_count",
        "t.n_cols IS NOT NULL",
    ),
    "contact_id": FieldSpec(
        "c.contact_id",
        "contact_id",
        "c.contact_id IS NOT NULL",
    ),
    "department": FieldSpec(ORGANIZATION_SQL, "department", f"{ORGANIZATION_SQL} IS NOT NULL"),
    "officer": FieldSpec(OFFICER_SQL, "officer", f"{OFFICER_SQL} IS NOT NULL"),
    "phone": FieldSpec(PHONE_SQL, "phone", f"{PHONE_SQL} IS NOT NULL"),
    "source_system": FieldSpec(
        SOURCE_SYSTEM_SQL,
        "source_system",
        f"{SOURCE_SYSTEM_SQL} IS NOT NULL",
    ),
    "source_url": FieldSpec(
        SOURCE_URL_SQL,
        "source_url",
        f"{SOURCE_URL_SQL} IS NOT NULL",
    ),
    "note_id": FieldSpec("f.note_id", "note_id", "f.note_id IS NOT NULL"),
    "note_seq": FieldSpec("f.seq", "note_seq", "f.seq IS NOT NULL"),
    "note_no": FieldSpec(
        "f.note_no",
        "note_no",
        "NULLIF(BTRIM(f.note_no), '') IS NOT NULL",
    ),
    "note": FieldSpec(
        "f.content",
        "note",
        "NULLIF(BTRIM(f.content), '') IS NOT NULL",
    ),
}

PUBLICATION_FIELDS = frozenset(
    {"publication_year", "publication_title", "publication_page_count"}
)
STATISTIC_FIELDS = frozenset(
    {
        "publication_year",
        "stat_id",
        "ref_id",
        "chapter_no",
        "chapter",
        "section_no",
        "section",
        "level3_title",
        "level4_title",
        "statistic_title",
        "unit",
        "base_date",
        "page_start",
    }
)
TABLE_FIELDS = frozenset(
    {
        "publication_year",
        "stat_id",
        "ref_id",
        "statistic_title",
        "table_id",
        "table_seq",
        "table_caption",
        "row_count",
        "column_count",
    }
)
CONTACT_FIELDS = frozenset(
    {
        "publication_year",
        "stat_id",
        "ref_id",
        "statistic_title",
        "contact_id",
        "department",
        "officer",
        "phone",
        "source_system",
        "source_url",
    }
)
FOOTNOTE_FIELDS = frozenset(
    {
        "publication_year",
        "stat_id",
        "ref_id",
        "statistic_title",
        "note_id",
        "note_seq",
        "note_no",
        "note",
    }
)

LISTS: dict[str, ListSpec] = {
    "publications": ListSpec(
        default_fields=(
            "publication_year",
            "publication_title",
            "publication_page_count",
        ),
        allowed_fields=PUBLICATION_FIELDS,
        row_filter_sql="p.pub_id IS NOT NULL",
        definition="통계연보 발간판 목록",
        basis="발간판 메타데이터를 조회",
        deduplicate_default=True,
    ),
    "statistics": ListSpec(
        default_fields=("stat_id", "ref_id", "statistic_title", "page_start"),
        allowed_fields=STATISTIC_FIELDS,
        row_filter_sql="s.stat_id IS NOT NULL",
        definition="통계연보에 수록된 논리 통계 항목 목록",
        basis="통계 항목 메타데이터를 조회",
    ),
    "tables": ListSpec(
        default_fields=(
            "stat_id",
            "statistic_title",
            "table_seq",
            "table_caption",
            "row_count",
            "column_count",
        ),
        allowed_fields=TABLE_FIELDS,
        row_filter_sql="t.table_id IS NOT NULL",
        definition="통계연보에 저장된 물리 통계표 목록",
        basis="통계표 레코드의 제목·순번·크기 메타데이터를 조회",
    ),
    "chapters": ListSpec(
        default_fields=("chapter_no", "chapter"),
        allowed_fields=frozenset({"publication_year", "chapter_no", "chapter"}),
        row_filter_sql="s.chapter_no IS NOT NULL",
        definition="통계연보의 장 목록",
        basis="장 번호와 장 제목을 조회",
        deduplicate_default=True,
    ),
    "sections": ListSpec(
        default_fields=("chapter_no", "section_no", "section"),
        allowed_fields=frozenset(
            {
                "publication_year",
                "chapter_no",
                "chapter",
                "section_no",
                "section",
            }
        ),
        row_filter_sql="s.chapter_no IS NOT NULL AND s.section_no IS NOT NULL",
        definition="통계연보의 절 목록",
        basis="장·절 번호와 절 제목을 조회",
        deduplicate_default=True,
    ),
    "organizations": ListSpec(
        default_fields=("department",),
        allowed_fields=frozenset({"publication_year", "department"}),
        row_filter_sql=f"{ORGANIZATION_SQL} IS NOT NULL",
        definition="각 통계표에 기재된 담당 부서 목록",
        basis="담당 부서명을 정규화해 조회",
        filter_fields=frozenset({"department"}),
        deduplicate_default=True,
    ),
    "source_systems": ListSpec(
        default_fields=("source_system",),
        allowed_fields=frozenset({"publication_year", "source_system"}),
        row_filter_sql=f"{SOURCE_SYSTEM_SQL} IS NOT NULL",
        definition="각 통계표에 기재된 출처 시스템 목록",
        basis="출처 시스템명을 정규화해 조회",
        filter_fields=frozenset({"source_system"}),
        deduplicate_default=True,
    ),
    "contacts": ListSpec(
        default_fields=(
            "statistic_title",
            "department",
            "officer",
            "phone",
            "source_system",
            "source_url",
        ),
        allowed_fields=CONTACT_FIELDS,
        row_filter_sql="c.contact_id IS NOT NULL",
        definition="통계연보 전체 통계 항목의 연락처·출처 목록",
        basis="각 통계 항목에 연결된 연락처·출처 레코드를 조회",
        filter_fields=frozenset(
            {"department", "officer", "phone", "source_system", "source_url"}
        ),
    ),
    "footnotes": ListSpec(
        default_fields=("statistic_title", "note_no", "note"),
        allowed_fields=FOOTNOTE_FIELDS,
        row_filter_sql="f.note_id IS NOT NULL",
        definition="통계연보 전체 통계 항목의 주석 목록",
        basis="각 통계 항목에 연결된 주석 레코드를 조회",
        filter_fields=frozenset({"note_no", "note"}),
    ),
}

OVERVIEW_SQL = f"""
    SELECT
        p.year AS publication_year,
        p.title AS publication_title,
        p.page_count,
        COUNT(DISTINCT s.stat_id) AS statistics_count,
        COUNT(DISTINCT t.table_id) AS tables_count,
        COUNT(DISTINCT (s.year, s.chapter_no))
            FILTER (WHERE s.chapter_no IS NOT NULL) AS chapters_count,
        COUNT(DISTINCT (s.year, s.chapter_no, s.section_no))
            FILTER (
                WHERE s.chapter_no IS NOT NULL AND s.section_no IS NOT NULL
            ) AS sections_count,
        COUNT(DISTINCT {ORGANIZATION_SQL}) AS organizations_count,
        COUNT(DISTINCT {SOURCE_SYSTEM_SQL}) AS source_systems_count
    FROM publications p
    LEFT JOIN statistics s ON s.pub_id = p.pub_id
    LEFT JOIN stat_tables t ON t.stat_id = s.stat_id
    LEFT JOIN contacts c ON c.stat_id = s.stat_id
""".strip()


# 최신 발간연도 기본값을 publications 테이블에서 조회한다.
def _latest_publication_year() -> int | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(LATEST_PUBLICATION_YEAR_SQL)
        row = cur.fetchone()
    if not row or row.get("publication_year") is None:
        return None
    return int(row["publication_year"])


# 허용된 operation/subject/group 조합을 검증한다.
def _validate_request(
    operation: str,
    subject: str,
    group_by: str | None,
    distinct_field: str | None,
    fields: list[str] | None,
    required_fields: list[str] | None,
    deduplicate: bool | None,
    publication_year: int | None,
    all_publication_years: bool,
    chapter_no: int | None,
    section_no: int | None,
    limit: int,
    offset: int,
) -> None:
    if operation not in {"overview", "count", "breakdown", "list"}:
        raise ValueError(f"unsupported operation: {operation}")
    if subject not in METRICS:
        raise ValueError(f"unsupported subject: {subject}")
    if distinct_field is not None:
        if operation not in {"count", "breakdown"}:
            raise ValueError("distinct_field can only be used with count or breakdown")
        if distinct_field not in LISTS[subject].allowed_fields:
            raise ValueError(
                f"unsupported distinct_field for subject={subject}: {distinct_field}"
            )
    if group_by is not None and group_by not in GROUPS:
        raise ValueError(f"unsupported group_by: {group_by}")
    if all_publication_years and publication_year is not None:
        raise ValueError(
            "publication_year and all_publication_years=true cannot be used together"
        )
    if chapter_no is not None and chapter_no < 1:
        raise ValueError("chapter_no must be greater than zero")
    if section_no is not None and section_no < 1:
        raise ValueError("section_no must be greater than zero")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must be zero or greater")
    if operation == "overview" and group_by is not None:
        raise ValueError("overview does not accept group_by")
    if operation == "count" and group_by is not None:
        raise ValueError("count does not accept group_by; use breakdown")
    if operation == "breakdown" and group_by is None:
        raise ValueError("breakdown requires group_by")
    if operation == "list" and group_by is not None:
        raise ValueError("list does not accept group_by")
    if operation != "list" and fields is not None:
        raise ValueError("fields can only be used with list")
    if operation != "list" and required_fields is not None:
        raise ValueError("required_fields can only be used with list")
    if operation != "list" and deduplicate is not None:
        raise ValueError("deduplicate can only be used with list")
    if operation != "list" and offset:
        raise ValueError("offset can only be used with list")
    if operation == "list":
        if fields == []:
            raise ValueError("fields must contain at least one field")
        list_spec = LISTS[subject]
        unsupported_fields = set(fields or ()) - list_spec.allowed_fields
        if unsupported_fields:
            unsupported = ", ".join(sorted(unsupported_fields))
            raise ValueError(
                f"unsupported fields for subject={subject}: {unsupported}"
            )
        selected_fields = set(fields or list_spec.default_fields)
        unsupported_required_fields = (
            set(required_fields or ()) - list_spec.filter_fields
        )
        if unsupported_required_fields:
            unsupported = ", ".join(sorted(unsupported_required_fields))
            raise ValueError(
                f"unsupported required_fields for subject={subject}: {unsupported}"
            )
        unselected_required_fields = set(required_fields or ()) - selected_fields
        if unselected_required_fields:
            unselected = ", ".join(sorted(unselected_required_fields))
            raise ValueError(
                f"required_fields must also be selected in fields: {unselected}"
            )
    if subject == "publications" and group_by not in {None, "publication_year"}:
        raise ValueError(
            "publications can only be counted without grouping or by publication_year"
        )


# 값 조건을 검증하고 SQL에서 쓸 비교 키까지 붙인 형태로 바꾼다.
def _resolve_value_filters(
    operation: str,
    subject: str,
    value_filters: list[dict[str, str]] | None,
) -> tuple[AppliedValueFilter, ...]:
    if not value_filters:
        return ()
    if operation == "overview":
        raise ValueError(
            "value_filters can only be used with count, breakdown, or list"
        )
    supported_fields = LISTS[subject].filter_fields
    resolved: dict[tuple[str, str], AppliedValueFilter] = {}
    for value_filter in value_filters:
        field_name = value_filter.get("field")
        contains = value_filter.get("contains") or ""
        if field_name not in supported_fields:
            supported = ", ".join(sorted(supported_fields)) or "없음"
            raise ValueError(
                f"unsupported value_filters field for subject={subject}: "
                f"{field_name}; supported fields: {supported}"
            )
        match_key = normalize_match_key(contains)
        if not match_key:
            raise ValueError(
                f"value_filters contains must not be empty: field={field_name}"
            )
        resolved.setdefault(
            (field_name, match_key),
            AppliedValueFilter(
                field=field_name,
                contains=contains,
                match_key=match_key,
            ),
        )
    return tuple(resolved.values())


# 연도 범위를 최신·특정·전체 중 하나로 결정한다.
def _resolve_publication_scope(
    publication_year: int | None,
    all_publication_years: bool,
) -> tuple[int | None, bool]:
    if all_publication_years:
        return None, False
    if publication_year is not None:
        return publication_year, False
    latest = _latest_publication_year()
    return latest, latest is not None


# 공통 연도·장·절 필터를 parameterized WHERE 절로 만든다.
def _where_parts(
    applied_publication_year: int | None,
    chapter_no: int | None,
    section_no: int | None,
    group: GroupSpec | None,
    value_filters: tuple[AppliedValueFilter, ...] = (),
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if applied_publication_year is not None:
        clauses.append("p.year = %s")
        params.append(applied_publication_year)
    if chapter_no is not None:
        clauses.append("s.chapter_no = %s")
        params.append(chapter_no)
    if section_no is not None:
        clauses.append("s.section_no = %s")
        params.append(section_no)
    # 공백·가운뎃점·대소문자를 지운 비교 키로 부분 일치를 판정한다.
    for value_filter in value_filters:
        clauses.append(
            contains_match_key_sql(FIELDS[value_filter.field].expression)
        )
        params.append(value_filter.match_key)
    if group is not None and group.nonempty_sql:
        clauses.append(group.nonempty_sql)
    return clauses, params


# subject와 group이 요구하는 테이블만 안전한 고정 JOIN으로 추가한다.
def _from_sql(metric: MetricSpec, group: GroupSpec | None) -> str:
    parts = [
        "FROM publications p",
        "LEFT JOIN statistics s ON s.pub_id = p.pub_id",
    ]
    if metric.requires_tables:
        parts.append("LEFT JOIN stat_tables t ON t.stat_id = s.stat_id")
    if metric.requires_contacts or (group is not None and group.requires_contacts):
        parts.append("LEFT JOIN contacts c ON c.stat_id = s.stat_id")
    if metric.requires_footnotes:
        parts.append("LEFT JOIN footnotes f ON f.stat_id = s.stat_id")
    return "\n".join(parts)


# 한 필드의 값 종류를 세는 COUNT 식을 만든다. 빈 값은 집계에서 제외한다.
def _distinct_field_expression(field_name: str) -> str:
    field = FIELDS[field_name]
    expression = f"COUNT(DISTINCT {field.expression})"
    if field.nonempty_sql:
        expression = f"{expression} FILTER (WHERE {field.nonempty_sql})"
    return expression


# 검증된 overview/count/breakdown/list 템플릿 중 하나로 SQL 계획을 만든다.
def build_query_plan(
    *,
    operation: AnalysisOperation,
    subject: AnalysisSubject,
    group_by: AnalysisGroup | None,
    distinct_field: AnalysisField | None,
    applied_publication_year: int | None,
    chapter_no: int | None,
    section_no: int | None,
    limit: int,
    fields: list[AnalysisField] | None = None,
    required_fields: list[AnalysisField] | None = None,
    deduplicate: bool | None = None,
    offset: int = 0,
    value_filters: tuple[AppliedValueFilter, ...] = (),
) -> QueryPlan:
    metric = METRICS[subject]
    group = GROUPS[group_by] if group_by is not None else None
    clauses, params = _where_parts(
        applied_publication_year,
        chapter_no,
        section_no,
        group,
        value_filters,
    )
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if operation == "overview":
        sql = "\n".join(
            part
            for part in (
                OVERVIEW_SQL,
                where_sql,
                "GROUP BY p.year, p.title, p.page_count",
                "ORDER BY p.year DESC",
            )
            if part
        )
        return QueryPlan(
            sql=sql,
            params=tuple(params),
            source_tables=("publications", "statistics", "stat_tables", "contacts"),
        )

    from_sql = _from_sql(metric, group)
    if operation == "list":
        list_spec = LISTS[subject]
        selected_fields = tuple(
            dict.fromkeys(fields if fields is not None else list_spec.default_fields)
        )
        list_clauses = [*clauses, list_spec.row_filter_sql]
        for field_name in dict.fromkeys(required_fields or ()):
            nonempty_sql = FIELDS[field_name].nonempty_sql
            if nonempty_sql:
                list_clauses.append(nonempty_sql)
        list_where_sql = f"WHERE {' AND '.join(list_clauses)}"
        distinct_sql = (
            "DISTINCT "
            if (
                list_spec.deduplicate_default
                if deduplicate is None
                else deduplicate
            )
            else ""
        )
        select_sql = ", ".join(
            f"{FIELDS[field_name].expression} AS {FIELDS[field_name].alias}"
            for field_name in selected_fields
        )
        order_sql = ", ".join(
            (
                f"{FIELDS[field_name].alias} DESC"
                if FIELDS[field_name].alias == "publication_year"
                else FIELDS[field_name].alias
            )
            for field_name in selected_fields
        )
        sql = "\n".join(
            (
                "WITH listed AS (",
                f"    SELECT {distinct_sql}{select_sql}",
                f"    {from_sql}",
                f"    {list_where_sql}",
                ")",
                "SELECT listed.*, COUNT(*) OVER () AS _total_count",
                "FROM listed",
                f"ORDER BY {order_sql}",
                "LIMIT %s OFFSET %s",
            )
        )
        return QueryPlan(
            sql=sql,
            params=tuple([*params, limit, offset]),
            source_tables=metric.source_tables,
        )

    count_expression = (
        _distinct_field_expression(distinct_field)
        if distinct_field is not None
        else metric.expression
    )
    if operation == "count":
        sql = "\n".join(
            part
            for part in (
                (
                    "SELECT COUNT(DISTINCT p.pub_id) AS matched_publications, "
                    f"{count_expression} AS count"
                ),
                from_sql,
                where_sql,
            )
            if part
        )
        return QueryPlan(sql=sql, params=tuple(params), source_tables=metric.source_tables)

    if group is None:
        raise ValueError("breakdown requires group_by")
    sql = "\n".join(
        part
        for part in (
            f"SELECT {group.select_sql}, {count_expression} AS count",
            from_sql,
            where_sql,
            f"GROUP BY {group.group_sql}",
            f"ORDER BY {group.order_sql}",
            "LIMIT %s",
        )
        if part
    )
    source_tables = tuple(
        dict.fromkeys(
            (*metric.source_tables, "contacts" if group.requires_contacts else "")
        )
    )
    source_tables = tuple(name for name in source_tables if name)
    return QueryPlan(
        sql=sql,
        params=tuple([*params, limit]),
        source_tables=source_tables,
    )


# SQL 계획을 실행해 dict 행 목록을 반환한다.
def _execute_plan(plan: QueryPlan) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(plan.sql, plan.params)
        return list(cur.fetchall())


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
    if applied_value_filters:
        conditions = ", ".join(
            f"{FIELDS[item.field].alias}에 '{item.contains}' 포함"
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


# 연보 단위 집계·목록 도구를 MCP에 등록한다.
def register(mcp: FastMCP) -> None:
    @mcp.tool(description=ANALYZE_PUBLICATIONS)
    def analyze_publications(
        operation: Annotated[
            AnalysisOperation,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["operation"]),
        ],
        subject: Annotated[
            AnalysisSubject,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["subject"]),
        ] = "statistics",
        group_by: Annotated[
            AnalysisGroup | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["group_by"]),
        ] = None,
        distinct_field: Annotated[
            AnalysisField | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["distinct_field"]),
        ] = None,
        fields: Annotated[
            list[AnalysisField] | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["fields"]),
        ] = None,
        required_fields: Annotated[
            list[AnalysisField] | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["required_fields"]),
        ] = None,
        value_filters: Annotated[
            list[ValueFilter] | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["value_filters"]),
        ] = None,
        deduplicate: Annotated[
            bool | None,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["deduplicate"]),
        ] = None,
        publication_year: Annotated[
            int | None,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["publication_year"],
                ge=1900,
                le=2200,
            ),
        ] = None,
        all_publication_years: Annotated[
            bool,
            Field(description=ANALYZE_PUBLICATIONS_FIELDS["all_publication_years"]),
        ] = False,
        chapter_no: Annotated[
            int | None,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["chapter_no"],
                ge=1,
            ),
        ] = None,
        section_no: Annotated[
            int | None,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["section_no"],
                ge=1,
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["limit"],
                ge=1,
                le=500,
            ),
        ] = 500,
        offset: Annotated[
            int,
            Field(
                description=ANALYZE_PUBLICATIONS_FIELDS["offset"],
                ge=0,
            ),
        ] = 0,
    ) -> dict[str, Any]:
        return analyze_publications_data(
            operation=operation,
            subject=subject,
            group_by=group_by,
            distinct_field=distinct_field,
            fields=fields,
            required_fields=required_fields,
            value_filters=(
                [item.model_dump() for item in value_filters]
                if value_filters is not None
                else None
            ),
            deduplicate=deduplicate,
            publication_year=publication_year,
            all_publication_years=all_publication_years,
            chapter_no=chapter_no,
            section_no=section_no,
            limit=limit,
            offset=offset,
        )
