# 이 파일은 파싱된 통계연보를 누적 적재하는 이관 가능한 PostgreSQL DML을 생성한다.
# 중복 연도 거부와 선택 연도 교체 정책을 SQL 트랜잭션으로 표현한다.
from __future__ import annotations

import json

from admin.backend.sql import sql_literal
from admin.backend.services.table_search_chunks import (
    build_note_search_chunks,
    build_table_search_chunks,
)
from utils.publication_kind import normalize_publication_kind, normalize_publication_period

YEARBOOK_LOAD_MODES = ("reject", "replace")


# 값 목록을 위치별 선택 형변환이 적용된 SQL 리터럴 목록으로 만든다.
def _values(values: list[object], casts: dict[int, str] | None = None) -> str:
    casts = casts or {}
    return ", ".join(sql_literal(value, casts.get(index)) for index, value in enumerate(values))


# 검색 청크 한 건을 표 범위 또는 통계 범위 INSERT 문으로 만든다.
# 주석 청크는 표에 속하지 않으므로 table_id 자리에 NULL을 넣는다.
def _chunk_insert(chunk: dict, table_ref: str) -> str:
    labels = json.dumps(chunk["search_labels"], ensure_ascii=False)
    search_text = sql_literal(chunk["search_text"])
    values = [
        "v_stat_id",
        table_ref,
        sql_literal(chunk["chunk_no"]),
        sql_literal(chunk["chunk_kind"]),
        sql_literal(labels, "jsonb"),
        search_text,
    ]
    return (
        "    INSERT INTO table_search_chunks "
        "(stat_id, table_id, chunk_no, chunk_kind, search_labels, search_text, search_doc) "
        "VALUES ("
        + ", ".join(values)
        + ", to_tsvector('simple', "
        + search_text
        + "));"
    )


# DML 생성에 필요한 발간물 연도·제목·통계 목록의 최소 계약을 검증한다.
# 중복 ref_id와 빈 제목은 DB 제약에 닿기 전에 여기서 막는다. SQL을 만들고 나서
# 적재에 실패하면 원인이 파서인지 DB인지 가리기 어렵다.
def validate_yearbook(data: dict) -> None:
    publication = data.get("publication") or {}
    try:
        normalize_publication_kind(publication.get("publication_kind"))
        normalize_publication_period(publication.get("publication_period"))
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    year = publication.get("year")
    if not isinstance(year, int) or not 1900 <= year <= 2200:
        raise ValueError("publication.year must be an integer between 1900 and 2200")
    if not publication.get("title"):
        raise ValueError("publication.title is required")
    statistics = data.get("statistics")
    if not isinstance(statistics, list) or not statistics:
        raise ValueError("parsed yearbook contains no statistics")

    seen: set[str] = set()
    duplicated: list[str] = []
    for unit in statistics:
        ref_id = unit.get("ref_id")
        if not ref_id:
            raise ValueError("every statistic needs a ref_id")
        if not unit.get("title_ko"):
            raise ValueError(f"statistic {ref_id} has no title_ko")
        if ref_id in seen:
            duplicated.append(ref_id)
        seen.add(ref_id)
    if duplicated:
        raise ValueError(
            "parsed yearbook contains duplicate ref_id: " + ", ".join(sorted(set(duplicated)))
        )


# 한 통계와 표·검색 청크·주석·담당자 INSERT 문을 출력 버퍼에 순서대로 추가한다.
def _append_statistic(lines: list[str], unit: dict, year: int) -> None:
    stat_values = [
        "v_pub_id",
        sql_literal(year),
        sql_literal(unit.get("ref_id")),
        sql_literal(unit.get("ordinal")),
        sql_literal(unit.get("chapter_no")),
        sql_literal(unit.get("section_no")),
        sql_literal(unit.get("level3_no")),
        sql_literal(unit.get("level4_no")),
        sql_literal(unit.get("chapter")),
        sql_literal(unit.get("section")),
        sql_literal(unit.get("level3_title")),
        sql_literal(unit.get("level4_title")),
        sql_literal(unit.get("title_ko")),
        sql_literal(unit.get("title_en")),
        sql_literal(unit.get("unit")),
        sql_literal(unit.get("base_date")),
        sql_literal(unit.get("page_start")),
    ]
    lines.extend([
        "    INSERT INTO statistics (",
        "        pub_id, year, ref_id, ordinal, chapter_no, section_no, level3_no, level4_no,",
        "        chapter, section, level3_title, level4_title,",
        "        title_ko, title_en, unit, base_date, page_start",
        "    ) VALUES (" + ", ".join(stat_values) + ")",
        "    RETURNING stat_id INTO v_stat_id;",
    ])

    for table in unit.get("tables", []):
        values = [
            "v_stat_id",
            sql_literal(table.get("seq")),
            sql_literal(table.get("caption")),
            sql_literal(table.get("n_rows")),
            sql_literal(table.get("n_cols")),
            sql_literal(json.dumps(table.get("body"), ensure_ascii=False), "jsonb"),
            sql_literal(table.get("table_md")),
        ]
        lines.append(
            "    INSERT INTO stat_tables "
            "(stat_id, seq, caption, n_rows, n_cols, body, table_md) VALUES ("
            + ", ".join(values) + ") RETURNING table_id INTO v_table_id;"
        )
        for chunk in build_table_search_chunks(unit, table):
            lines.append(_chunk_insert(chunk, "v_table_id"))

    # 주석 청크는 통계당 한 벌이므로 표 반복 밖에서 만든다. 반복 안에서 만들면
    # 표가 여러 개인 통계에서 같은 주석이 표 수만큼 중복 저장된다.
    for chunk in build_note_search_chunks(unit):
        lines.append(_chunk_insert(chunk, "NULL"))

    for note in unit.get("footnotes", []):
        values = [
            "v_stat_id",
            sql_literal(note.get("seq")),
            sql_literal(note.get("note_no")),
            sql_literal(note.get("content")),
        ]
        lines.append(
            "    INSERT INTO footnotes (stat_id, seq, note_no, content) VALUES ("
            + ", ".join(values) + ");"
        )

    for contact in unit.get("contacts", []):
        values = [
            "v_stat_id",
            sql_literal(contact.get("dept")),
            sql_literal(contact.get("officer")),
            sql_literal(contact.get("phone")),
            sql_literal(contact.get("source_system")),
            sql_literal(contact.get("source_url")),
        ]
        lines.append(
            "    INSERT INTO contacts "
            "(stat_id, dept, officer, phone, source_system, source_url) VALUES ("
            + ", ".join(values) + ");"
        )


# 파싱 결과 전체를 재실행 가능한 단일 연도 적재 트랜잭션으로 직렬화한다.
def build_load_dml(
    data: dict,
    mode: str = "reject",
    include_transaction: bool = True,
) -> str:
    validate_yearbook(data)
    if mode not in YEARBOOK_LOAD_MODES:
        raise ValueError(f"unsupported load mode: {mode}")

    publication = data["publication"]
    publication_kind = normalize_publication_kind(publication.get("publication_kind"))
    period = normalize_publication_period(publication.get("publication_period"))
    year = int(publication["year"])
    # 같은 해에 상반기·하반기가 함께 실리므로 교체·중복 판정 범위에 반기를 포함한다.
    publication_scope = (
        f"publication_kind = {sql_literal(publication_kind)}"
        f" AND year = {year}"
        f" AND period = {sql_literal(period)}"
    )
    publication_label = f"{publication_kind}:{year}{':' + period if period else ''}"
    lines = []
    if include_transaction:
        lines.append("BEGIN;")
    lines.extend([
        "DO $statyearbook_load$",
        "DECLARE",
        "    v_pub_id BIGINT;",
        "    v_stat_id BIGINT;",
        "    v_table_id BIGINT;",
        "BEGIN",
        "    PERFORM pg_advisory_xact_lock(7824601025);",
    ])
    if mode == "replace":
        lines.extend([
            "    DELETE FROM statistics WHERE pub_id IN "
            f"(SELECT pub_id FROM publications WHERE {publication_scope});",
            f"    DELETE FROM publications WHERE {publication_scope};",
        ])
    else:
        lines.extend([
            f"    IF EXISTS (SELECT 1 FROM publications WHERE {publication_scope}) THEN",
            "        RAISE EXCEPTION "
            f"'publication {publication_label} already exists; use replace mode explicitly';",
            "    END IF;",
        ])

    pub_values = _values([
        publication_kind,
        period,
        year,
        publication.get("pub_no"),
        publication["title"],
        publication.get("page_count"),
    ])
    lines.extend([
        "    INSERT INTO publications "
        "(publication_kind, period, year, pub_no, title, page_count)",
        f"    VALUES ({pub_values}) RETURNING pub_id INTO v_pub_id;",
    ])
    for unit in data["statistics"]:
        _append_statistic(lines, unit, year)

    lines.extend([
        "    UPDATE statistics",
        "    SET search_doc = to_tsvector(",
        "        'simple',",
        "        coalesce(title_ko,'') || ' ' || coalesce(title_en,'') || ' ' ||",
        "        coalesce(chapter,'') || ' ' || coalesce(section,'') || ' ' ||",
        "        coalesce(level3_title,'') || ' ' || coalesce(level4_title,'') || ' ' ||",
        "        coalesce(ref_id,'')",
        "    )",
        "    WHERE pub_id = v_pub_id;",
        "END",
        "$statyearbook_load$;",
    ])
    if include_transaction:
        lines.append("COMMIT;")
    lines.append("")
    return "\n".join(lines)
