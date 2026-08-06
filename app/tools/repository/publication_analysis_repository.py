# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.db import connect
from app.tools.repository.publication_repository import (
    OFFICER_SQL,
    ORGANIZATION_SQL,
    PHONE_SQL,
    SOURCE_SYSTEM_SQL,
    SOURCE_URL_SQL,
    contains_any_match_key_sql,
    normalize_match_key,
    officer_match_keys,
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
AnalysisValueFilterField = Literal[
    "department",
    "officer",
    "phone",
    "source_system",
    "source_url",
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
    match_keys: tuple[str, ...]


# 필드마다 검색어를 비교 키로 푸는 방법이 다르다. 지정하지 않은 필드는 공백·기호만 지운다.
VALUE_FILTER_MATCH_KEYS: dict[str, Callable[[str], tuple[str, ...]]] = {
    "officer": officer_match_keys,
}


# 필드에 맞는 비교 키 목록을 만든다.
def _value_filter_match_keys(field_name: str, contains: str) -> tuple[str, ...]:
    resolver = VALUE_FILTER_MATCH_KEYS.get(field_name)
    if resolver is not None:
        return resolver(contains)
    key = normalize_match_key(contains)
    return (key,) if key else ()


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


# 거절한 조건 필드를 어느 subject에서 쓸 수 있는지 알려 준다.
def _value_filter_hint(
    field_name: str | None,
    supported_fields: frozenset[str],
) -> str:
    usable_subjects = sorted(
        name for name, spec in LISTS.items() if field_name in spec.filter_fields
    )
    if usable_subjects:
        return f"use subject={' or subject='.join(usable_subjects)} for this field"
    supported = ", ".join(sorted(supported_fields))
    if supported:
        return f"supported fields: {supported}"
    return "this subject accepts no value_filters"


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
            hint = _value_filter_hint(field_name, supported_fields)
            raise ValueError(
                f"unsupported value_filters field for subject={subject}: "
                f"{field_name}; {hint}"
            )
        match_keys = _value_filter_match_keys(field_name, contains)
        if not match_keys:
            raise ValueError(
                f"value_filters contains must not be empty: field={field_name}"
            )
        resolved.setdefault(
            (field_name, match_keys),
            AppliedValueFilter(
                field=field_name,
                contains=contains,
                match_keys=match_keys,
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
    # 담당자처럼 검색어를 여러 형태로 푸는 필드는 그중 하나만 맞아도 일치로 본다.
    for value_filter in value_filters:
        clauses.append(
            contains_any_match_key_sql(
                FIELDS[value_filter.field].expression,
                len(value_filter.match_keys),
            )
        )
        params.extend(value_filter.match_keys)
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
