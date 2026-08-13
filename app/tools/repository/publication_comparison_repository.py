# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.db import connect
from app.tools.repository.publication_repository import (
    ORGANIZATION_SQL,
    SOURCE_SYSTEM_SQL,
    match_key_sql,
    simple_key_sql,
)
from utils.publication_kind import DEFAULT_PUBLICATION_KIND, normalize_publication_kind


CompareOperation = Literal[
    "summary",
    "only_in_base",
    "only_in_target",
    "in_both",
    "changed",
]
CompareSubject = Literal[
    "statistics",
    "chapters",
    "sections",
    "organizations",
    "source_systems",
]
CompareMatchBy = Literal["title", "title_and_unit", "number"]
CompareField = Literal[
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
    "organization",
    "source_system",
]

PUBLICATION_YEARS_SQL = (
    "SELECT year FROM publications WHERE publication_kind = %s ORDER BY year DESC"
)
SET_OPERATIONS = frozenset({"only_in_base", "only_in_target", "in_both", "changed"})
PAIRED_OPERATIONS = frozenset({"in_both", "changed"})


@dataclass(frozen=True)
class ItemColumn:
    expression: str
    # 두 발간판의 값을 맞대어 변경을 판정할 수 있는 필드인지 나타낸다.
    # stat_id처럼 발간판마다 새로 부여되는 식별자와 페이지 번호는 비교 대상이 아니다.
    comparable: bool = True


@dataclass(frozen=True)
class CompareSubjectSpec:
    join_sql: str
    match_keys: dict[str, str]
    columns: dict[str, ItemColumn]
    default_fields: tuple[str, ...]
    dedupe_order_sql: str
    order_columns: tuple[str, ...]
    unit_label: str
    definition: str
    source_tables: tuple[str, ...]
    record_count_note: str = ""


@dataclass(frozen=True)
class QueryPlan:
    sql: str
    params: tuple[Any, ...]


STATISTICS_JOIN_SQL = "JOIN statistics s ON s.pub_id = p.pub_id"
CONTACTS_JOIN_SQL = f"{STATISTICS_JOIN_SQL}\n    JOIN contacts c ON c.stat_id = s.stat_id"
TITLE_KEY_SQL = match_key_sql("s.title_ko")
UNIT_KEY_SQL = match_key_sql("s.unit")

SUBJECTS: dict[str, CompareSubjectSpec] = {
    "statistics": CompareSubjectSpec(
        join_sql=STATISTICS_JOIN_SQL,
        match_keys={
            "title": TITLE_KEY_SQL,
            "title_and_unit": f"{TITLE_KEY_SQL} || '|' || COALESCE({UNIT_KEY_SQL}, '')",
            "number": simple_key_sql("s.ref_id"),
        },
        columns={
            "stat_id": ItemColumn("s.stat_id", comparable=False),
            "ref_id": ItemColumn("s.ref_id"),
            "chapter_no": ItemColumn("s.chapter_no"),
            "chapter": ItemColumn("s.chapter"),
            "section_no": ItemColumn("s.section_no"),
            "section": ItemColumn("s.section"),
            "level3_title": ItemColumn("s.level3_title"),
            "level4_title": ItemColumn("s.level4_title"),
            "statistic_title": ItemColumn("s.title_ko"),
            "unit": ItemColumn("s.unit"),
            "base_date": ItemColumn("s.base_date"),
            "page_start": ItemColumn("s.page_start", comparable=False),
        },
        default_fields=(
            "stat_id",
            "ref_id",
            "chapter",
            "statistic_title",
            "unit",
            "page_start",
        ),
        dedupe_order_sql="stat_id",
        order_columns=("page_start", "stat_id"),
        unit_label="통계 항목",
        definition="통계연보에 수록된 논리 통계 항목",
        source_tables=("publications", "statistics"),
        record_count_note=(
            "한 발간판에서 같은 match_key를 가진 통계 항목 수. 1보다 크면 이름이 같은 "
            "별개 통계가 한 항목으로 합쳐졌다는 뜻이다"
        ),
    ),
    "chapters": CompareSubjectSpec(
        join_sql=STATISTICS_JOIN_SQL,
        match_keys={
            "title": match_key_sql("s.chapter"),
            "number": simple_key_sql("s.chapter_no::text"),
        },
        columns={
            "chapter_no": ItemColumn("s.chapter_no"),
            "chapter": ItemColumn("s.chapter"),
        },
        default_fields=("chapter_no", "chapter"),
        dedupe_order_sql="chapter_no, chapter",
        order_columns=("chapter_no",),
        unit_label="장",
        definition="통계 항목에 연결된 장",
        source_tables=("publications", "statistics"),
        record_count_note="그 장에 속한 통계 항목 수",
    ),
    "sections": CompareSubjectSpec(
        join_sql=STATISTICS_JOIN_SQL,
        match_keys={
            "title": match_key_sql("s.section"),
            "number": "s.chapter_no::text || '-' || s.section_no::text",
        },
        columns={
            "chapter_no": ItemColumn("s.chapter_no"),
            "chapter": ItemColumn("s.chapter"),
            "section_no": ItemColumn("s.section_no"),
            "section": ItemColumn("s.section"),
        },
        default_fields=("chapter_no", "section_no", "section"),
        dedupe_order_sql="chapter_no, section_no, section, chapter",
        order_columns=("chapter_no", "section_no"),
        unit_label="절",
        definition="통계 항목에 연결된 절",
        source_tables=("publications", "statistics"),
        record_count_note="그 절에 속한 통계 항목 수",
    ),
    "organizations": CompareSubjectSpec(
        join_sql=CONTACTS_JOIN_SQL,
        match_keys={"title": match_key_sql("c.dept")},
        columns={"organization": ItemColumn(ORGANIZATION_SQL)},
        default_fields=("organization",),
        dedupe_order_sql="organization",
        order_columns=("organization",),
        unit_label="담당 부서",
        definition="통계표 출처 문단에서 파싱된 담당 부서",
        source_tables=("publications", "statistics", "contacts"),
        record_count_note="그 부서가 담당하는 것으로 기재된 연락처 레코드 수",
    ),
    "source_systems": CompareSubjectSpec(
        join_sql=CONTACTS_JOIN_SQL,
        match_keys={"title": match_key_sql("c.source_system")},
        columns={"source_system": ItemColumn(SOURCE_SYSTEM_SQL)},
        default_fields=("source_system",),
        dedupe_order_sql="source_system",
        order_columns=("source_system",),
        unit_label="출처 시스템",
        definition="통계표 출처 문단에서 파싱된 출처 시스템",
        source_tables=("publications", "statistics", "contacts"),
        record_count_note="그 출처 시스템이 기재된 연락처 레코드 수",
    ),
}

MATCH_KEY_DEFINITIONS: dict[str, str] = {
    "title": "이름에서 공백·가운뎃점·대소문자 차이를 지운 값",
    "title_and_unit": "이름과 단위에서 공백·가운뎃점·대소문자 차이를 지워 이어 붙인 값",
    "number": "발간판 안의 목차 번호",
}
MATCH_KEY_LIMITATIONS: dict[str, tuple[str, ...]] = {
    "title": (
        "이름이 바뀐 항목은 같은 항목이어도 양쪽 목록에 각각 나타난다",
    ),
    "title_and_unit": (
        "단위 표기가 발간판마다 달라지면 같은 항목이어도 양쪽 목록에 각각 나타난다",
    ),
    "number": (
        "목차 번호는 발간판마다 다시 매겨지므로, 번호가 밀린 항목은 이름이 같아도 "
        "양쪽 목록에 각각 나타난다",
    ),
}
DUPLICATE_TITLE_LIMITATION = (
    "이름이 같고 단위가 다른 별개 통계는 한 항목으로 합쳐지므로, duplicate_key_count나 "
    "record_count가 1보다 크면 match_by=title_and_unit으로 다시 비교한다"
)


# 적재된 발간연도를 최신순으로 조회한다.
def _publication_years(publication_kind: str = DEFAULT_PUBLICATION_KIND) -> list[int]:
    publication_kind = normalize_publication_kind(publication_kind)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(PUBLICATION_YEARS_SQL, (publication_kind,))
        return [int(row["year"]) for row in cur.fetchall()]


# 허용된 operation/subject/match_by/필드 조합과 페이지 인자를 검증한다.
def _validate_request(
    operation: str,
    subject: str,
    match_by: str,
    fields: list[str] | None,
    limit: int,
    offset: int,
) -> None:
    if operation not in {"summary", *SET_OPERATIONS}:
        raise ValueError(f"unsupported operation: {operation}")
    if subject not in SUBJECTS:
        raise ValueError(f"unsupported subject: {subject}")
    spec = SUBJECTS[subject]
    if match_by not in spec.match_keys:
        supported = ", ".join(sorted(spec.match_keys))
        raise ValueError(
            f"unsupported match_by for subject={subject}: {match_by}; "
            f"supported: {supported}"
        )
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if offset < 0:
        raise ValueError("offset must be zero or greater")
    if operation == "summary" and offset:
        raise ValueError("offset can only be used with list operations")
    if fields == []:
        raise ValueError("fields must contain at least one field")
    unsupported_fields = set(fields or ()) - set(spec.columns)
    if unsupported_fields:
        unsupported = ", ".join(sorted(unsupported_fields))
        raise ValueError(f"unsupported fields for subject={subject}: {unsupported}")
    if operation == "changed" and not _comparable_fields(spec, fields):
        raise ValueError(
            "changed requires at least one comparable field in fields; "
            "stat_id and page_start are not compared between publications"
        )


# 두 발간판의 값을 맞대어 변경을 판정할 수 있는 필드만 남긴다.
def _comparable_fields(
    spec: CompareSubjectSpec,
    fields: list[str] | None,
) -> tuple[str, ...]:
    selected = _selected_fields(spec, fields)
    return tuple(name for name in selected if spec.columns[name].comparable)


# 대응 기준과 subject가 함께 만드는 한계를 응답에 실을 문장으로 모은다.
def _limitations(subject: str, match_by: str) -> list[str]:
    limitations = list(MATCH_KEY_LIMITATIONS[match_by])
    if subject == "statistics" and match_by == "title":
        limitations.append(DUPLICATE_TITLE_LIMITATION)
    return limitations


# 요청 필드를 중복 없이 정리하고, 생략하면 subject 기본 필드를 쓴다.
def _selected_fields(
    spec: CompareSubjectSpec,
    fields: list[str] | None,
) -> tuple[str, ...]:
    return tuple(dict.fromkeys(fields if fields is not None else spec.default_fields))


# 비교할 두 발간연도를 결정한다. 생략하면 가장 최근 두 발간판을 비교한다.
def _resolve_publication_years(
    base_publication_year: int | None,
    target_publication_year: int | None,
    available_years: list[int],
) -> tuple[int, int, bool]:
    if not available_years:
        raise ValueError("no publication is loaded")
    known = ", ".join(str(year) for year in available_years)
    for year in (base_publication_year, target_publication_year):
        if year is not None and year not in available_years:
            raise ValueError(
                f"publication_year {year} is not loaded; available: {known}"
            )
    if base_publication_year is not None and target_publication_year is not None:
        if base_publication_year == target_publication_year:
            raise ValueError(
                "base_publication_year and target_publication_year must differ"
            )
        return base_publication_year, target_publication_year, False
    if base_publication_year is not None:
        later = [year for year in available_years if year > base_publication_year]
        if not later:
            raise ValueError(
                f"no publication is newer than {base_publication_year}; available: {known}"
            )
        return base_publication_year, min(later), True
    if target_publication_year is not None:
        earlier = [year for year in available_years if year < target_publication_year]
        if not earlier:
            raise ValueError(
                f"no publication is older than {target_publication_year}; "
                f"available: {known}"
            )
        return max(earlier), target_publication_year, True
    if len(available_years) < 2:
        raise ValueError(
            f"comparison requires two publications; available: {known}"
        )
    return available_years[1], available_years[0], True


# 한 발간판의 비교 항목을 match_key마다 한 행으로 접는 CTE를 만든다.
# record_count는 접히기 전 원본 행 수이므로 같은 키가 여러 항목을 덮었는지 드러낸다.
def _items_cte_sql(name: str, spec: CompareSubjectSpec, key_sql: str) -> str:
    columns_sql = ",\n                   ".join(
        f"{column.expression} AS {alias}" for alias, column in spec.columns.items()
    )
    return "\n".join(
        (
            f"    {name} AS (",
            "        SELECT DISTINCT ON (match_key) * FROM (",
            f"            SELECT {key_sql} AS match_key,",
            f"                   {columns_sql},",
            f"                   COUNT(*) OVER (PARTITION BY {key_sql}) AS record_count",
            "            FROM publications p",
            f"            {spec.join_sql}",
            f"            WHERE p.publication_kind = %s AND p.year = %s AND {key_sql} IS NOT NULL",
            f"        ) matched ORDER BY match_key, {spec.dedupe_order_sql}",
            "    )",
        )
    )


# 선택한 필드가 두 발간판 사이에서 달라졌는지 판정하는 SQL 조각을 만든다.
def _changed_fields_sql(spec: CompareSubjectSpec, compared: tuple[str, ...]) -> str:
    cases = ", ".join(
        f"CASE WHEN b.{alias} IS DISTINCT FROM t.{alias} THEN '{alias}' END"
        for alias in compared
    )
    return f"ARRAY_REMOVE(ARRAY[{cases}], NULL)"


# 두 발간판의 항목 집합을 비교하는 SQL 계획을 만든다.
def build_query_plan(
    *,
    operation: CompareOperation,
    subject: CompareSubject,
    match_by: CompareMatchBy,
    base_publication_year: int,
    target_publication_year: int,
    publication_kind: str = DEFAULT_PUBLICATION_KIND,
    fields: list[CompareField] | None = None,
    limit: int = 500,
    offset: int = 0,
) -> QueryPlan:
    spec = SUBJECTS[subject]
    publication_kind = normalize_publication_kind(publication_kind)
    key_sql = spec.match_keys[match_by]
    selected = _selected_fields(spec, fields)
    compared = _comparable_fields(spec, fields)
    cte_sql = "\n".join(
        (
            "WITH",
            f"{_items_cte_sql('base_items', spec, key_sql)},",
            _items_cte_sql("target_items", spec, key_sql),
        )
    )
    years = (
        publication_kind,
        base_publication_year,
        publication_kind,
        target_publication_year,
    )

    if operation == "summary":
        changed_sql = (
            " OR ".join(f"b.{alias} IS DISTINCT FROM t.{alias}" for alias in compared)
            if compared
            else "FALSE"
        )
        sql = "\n".join(
            (
                cte_sql,
                "SELECT",
                "    COUNT(*) FILTER (WHERE b.match_key IS NOT NULL)",
                "        AS base_item_count,",
                "    COALESCE(SUM(b.record_count), 0) AS base_record_count,",
                "    COUNT(*) FILTER (WHERE b.record_count > 1)",
                "        AS base_duplicate_key_count,",
                "    COUNT(*) FILTER (WHERE t.match_key IS NOT NULL)",
                "        AS target_item_count,",
                "    COALESCE(SUM(t.record_count), 0) AS target_record_count,",
                "    COUNT(*) FILTER (WHERE t.record_count > 1)",
                "        AS target_duplicate_key_count,",
                "    COUNT(*) FILTER (",
                "        WHERE b.match_key IS NOT NULL AND t.match_key IS NULL",
                "    ) AS only_in_base_count,",
                "    COUNT(*) FILTER (",
                "        WHERE b.match_key IS NULL AND t.match_key IS NOT NULL",
                "    ) AS only_in_target_count,",
                "    COUNT(*) FILTER (",
                "        WHERE b.match_key IS NOT NULL AND t.match_key IS NOT NULL",
                "    ) AS in_both_count,",
                "    COUNT(*) FILTER (",
                "        WHERE b.match_key IS NOT NULL AND t.match_key IS NOT NULL",
                f"          AND ({changed_sql})",
                "    ) AS changed_count",
                "FROM base_items b",
                "FULL OUTER JOIN target_items t ON t.match_key = b.match_key",
            )
        )
        return QueryPlan(sql=sql, params=years)

    if operation in PAIRED_OPERATIONS:
        select_sql = ",\n    ".join(
            (
                "b.match_key",
                *(
                    f"b.{alias} AS base_{alias},\n    t.{alias} AS target_{alias}"
                    for alias in selected
                ),
                "b.record_count AS base_record_count",
                "t.record_count AS target_record_count",
                f"{_changed_fields_sql(spec, compared)} AS changed_fields",
                "COUNT(*) OVER () AS _total_count",
            )
        )
        where_sql = (
            "WHERE "
            + " OR ".join(
                f"b.{alias} IS DISTINCT FROM t.{alias}" for alias in compared
            )
            if operation == "changed"
            else ""
        )
        order_sql = ", ".join(
            f"b.{alias} NULLS LAST" for alias in spec.order_columns
        )
        sql = "\n".join(
            part
            for part in (
                cte_sql,
                f"SELECT {select_sql}",
                "FROM base_items b",
                "JOIN target_items t ON t.match_key = b.match_key",
                where_sql,
                f"ORDER BY {order_sql}",
                "LIMIT %s OFFSET %s",
            )
            if part
        )
        return QueryPlan(sql=sql, params=(*years, limit, offset))

    kept, dropped = (
        ("b", "t") if operation == "only_in_base" else ("t", "b")
    )
    select_sql = ",\n    ".join(
        (
            f"{kept}.match_key",
            *(f"{kept}.{alias}" for alias in selected),
            f"{kept}.record_count",
            "COUNT(*) OVER () AS _total_count",
        )
    )
    order_sql = ", ".join(
        f"{kept}.{alias} NULLS LAST" for alias in spec.order_columns
    )
    sql = "\n".join(
        (
            cte_sql,
            f"SELECT {select_sql}",
            f"FROM {'base_items b' if kept == 'b' else 'target_items t'}",
            f"LEFT JOIN {'target_items t' if kept == 'b' else 'base_items b'}"
            f" ON t.match_key = b.match_key",
            f"WHERE {dropped}.match_key IS NULL",
            f"ORDER BY {order_sql}",
            "LIMIT %s OFFSET %s",
        )
    )
    return QueryPlan(sql=sql, params=(*years, limit, offset))


# SQL 계획을 실행해 dict 행 목록을 반환한다.
def _execute_plan(plan: QueryPlan) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(plan.sql, plan.params)
        return list(cur.fetchall())
