# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.db import connect
from app.tool_descriptions import (
    ANALYZE_PUBLICATIONS,
    ANALYZE_PUBLICATIONS_FIELDS,
)


AnalysisOperation = Literal["overview", "count", "breakdown"]
AnalysisSubject = Literal[
    "statistics",
    "tables",
    "chapters",
    "sections",
    "organizations",
    "source_systems",
    "publications",
]
AnalysisGroup = Literal[
    "publication_year",
    "chapter",
    "section",
    "organization",
    "source_system",
]

LATEST_PUBLICATION_YEAR_SQL = "SELECT MAX(year) AS publication_year FROM publications"
ORGANIZATION_SQL = (
    "NULLIF(regexp_replace(BTRIM(c.dept), '\\s+', ' ', 'g'), '')"
)
SOURCE_SYSTEM_SQL = (
    "NULLIF(regexp_replace(BTRIM(c.source_system), '\\s+', ' ', 'g'), '')"
)


@dataclass(frozen=True)
class MetricSpec:
    expression: str
    definition: str
    basis: str
    source_tables: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    requires_tables: bool = False
    requires_contacts: bool = False


@dataclass(frozen=True)
class GroupSpec:
    select_sql: str
    group_sql: str
    nonempty_sql: str | None
    order_sql: str
    requires_contacts: bool = False


@dataclass(frozen=True)
class QueryPlan:
    sql: str
    params: tuple[Any, ...]
    source_tables: tuple[str, ...]


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
    publication_year: int | None,
    all_publication_years: bool,
    chapter_no: int | None,
    section_no: int | None,
    limit: int,
) -> None:
    if operation not in {"overview", "count", "breakdown"}:
        raise ValueError(f"unsupported operation: {operation}")
    if subject not in METRICS:
        raise ValueError(f"unsupported subject: {subject}")
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
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    if operation == "overview" and group_by is not None:
        raise ValueError("overview does not accept group_by")
    if operation == "count" and group_by is not None:
        raise ValueError("count does not accept group_by; use breakdown")
    if operation == "breakdown" and group_by is None:
        raise ValueError("breakdown requires group_by")
    if subject == "publications" and group_by not in {None, "publication_year"}:
        raise ValueError(
            "publications can only be counted without grouping or by publication_year"
        )


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
    return "\n".join(parts)


# 검증된 overview/count/breakdown 템플릿 중 하나로 SQL 계획을 만든다.
def build_query_plan(
    *,
    operation: AnalysisOperation,
    subject: AnalysisSubject,
    group_by: AnalysisGroup | None,
    applied_publication_year: int | None,
    chapter_no: int | None,
    section_no: int | None,
    limit: int,
) -> QueryPlan:
    metric = METRICS[subject]
    group = GROUPS[group_by] if group_by is not None else None
    clauses, params = _where_parts(
        applied_publication_year,
        chapter_no,
        section_no,
        group,
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
    if operation == "count":
        sql = "\n".join(
            part
            for part in (
                (
                    "SELECT COUNT(DISTINCT p.pub_id) AS matched_publications, "
                    f"{metric.expression} AS count"
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
            f"SELECT {group.select_sql}, {metric.expression} AS count",
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


# 현재 스키마 위에서 연보 단위 기초통계를 계산한다.
def analyze_publications_data(
    *,
    operation: AnalysisOperation,
    subject: AnalysisSubject = "statistics",
    group_by: AnalysisGroup | None = None,
    publication_year: int | None = None,
    all_publication_years: bool = False,
    chapter_no: int | None = None,
    section_no: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    _validate_request(
        operation,
        subject,
        group_by,
        publication_year,
        all_publication_years,
        chapter_no,
        section_no,
        limit,
    )
    applied_publication_year, publication_year_defaulted = (
        _resolve_publication_scope(publication_year, all_publication_years)
    )
    plan = build_query_plan(
        operation=operation,
        subject=subject,
        group_by=group_by,
        applied_publication_year=applied_publication_year,
        chapter_no=chapter_no,
        section_no=section_no,
        limit=limit,
    )
    rows = _execute_plan(plan)
    metric = METRICS[subject]
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
    else:
        response_subject = subject
        definition = metric.definition
        basis = metric.basis
        limitations = metric.limitations

    response: dict[str, Any] = {
        "ok": True,
        "operation": operation,
        "subject": response_subject,
        "group_by": group_by,
        "requested_publication_year": publication_year,
        "applied_publication_year": applied_publication_year,
        "publication_year_defaulted": publication_year_defaulted,
        "all_publication_years": all_publication_years,
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
    return response


# 연보 단위 집계 도구를 MCP에 등록한다.
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
                le=200,
            ),
        ] = 50,
    ) -> dict[str, Any]:
        return analyze_publications_data(
            operation=operation,
            subject=subject,
            group_by=group_by,
            publication_year=publication_year,
            all_publication_years=all_publication_years,
            chapter_no=chapter_no,
            section_no=section_no,
            limit=limit,
        )
