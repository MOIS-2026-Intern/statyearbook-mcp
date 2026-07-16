# 이 파일은 파싱된 통계연보를 누적 적재하는 이관 가능한 PostgreSQL DML을 생성한다.
# 중복 연도 거부와 선택 연도 교체 정책을 SQL 트랜잭션으로 표현한다.
from __future__ import annotations

import json

YEARBOOK_LOAD_MODES = ("reject", "replace")


def sql_literal(value, cast: str | None = None) -> str:
    if value is None:
        literal = "NULL"
    elif isinstance(value, bool):
        literal = "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        literal = str(value)
    else:
        literal = "'" + str(value).replace("'", "''") + "'"
    return f"{literal}::{cast}" if cast and value is not None else literal


def _values(values: list[object], casts: dict[int, str] | None = None) -> str:
    casts = casts or {}
    return ", ".join(sql_literal(value, casts.get(index)) for index, value in enumerate(values))


def validate_yearbook(data: dict) -> None:
    publication = data.get("publication") or {}
    year = publication.get("year")
    if not isinstance(year, int) or not 1900 <= year <= 2200:
        raise ValueError("publication.year must be an integer between 1900 and 2200")
    if not publication.get("title"):
        raise ValueError("publication.title is required")
    statistics = data.get("statistics")
    if not isinstance(statistics, list) or not statistics:
        raise ValueError("parsed yearbook contains no statistics")


def _append_statistic(lines: list[str], unit: dict, year: int) -> None:
    stat_values = [
        "v_pub_id",
        sql_literal(year),
        sql_literal(unit.get("ref_id")),
        sql_literal(unit.get("chapter_no")),
        sql_literal(unit.get("section_no")),
        sql_literal(unit.get("chapter")),
        sql_literal(unit.get("section")),
        sql_literal(unit.get("title_ko")),
        sql_literal(unit.get("title_en")),
        sql_literal(unit.get("unit")),
        sql_literal(unit.get("base_date")),
        sql_literal(unit.get("page_start")),
    ]
    lines.extend([
        "    INSERT INTO statistics (",
        "        pub_id, year, ref_id, chapter_no, section_no, chapter, section,",
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
            + ", ".join(values) + ");"
        )

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

    for image in unit.get("images", []):
        values = [
            "v_stat_id",
            sql_literal(image.get("filename")),
            sql_literal(image.get("page")),
            sql_literal(image.get("uri")),
            sql_literal(image.get("caption")),
        ]
        lines.append(
            "    INSERT INTO statistic_images "
            "(stat_id, filename, page, uri, caption) VALUES ("
            + ", ".join(values) + ");"
        )


def build_load_dml(
    data: dict,
    mode: str = "reject",
    include_transaction: bool = True,
) -> str:
    validate_yearbook(data)
    if mode not in YEARBOOK_LOAD_MODES:
        raise ValueError(f"unsupported load mode: {mode}")

    publication = data["publication"]
    year = int(publication["year"])
    lines = []
    if include_transaction:
        lines.append("BEGIN;")
    lines.extend([
        "DO $statyearbook_load$",
        "DECLARE",
        "    v_pub_id BIGINT;",
        "    v_stat_id BIGINT;",
        "BEGIN",
        "    PERFORM pg_advisory_xact_lock(7824601025);",
    ])
    if mode == "replace":
        lines.extend([
            f"    DELETE FROM statistics WHERE pub_id IN (SELECT pub_id FROM publications WHERE year = {year});",
            f"    DELETE FROM publications WHERE year = {year};",
        ])
    else:
        lines.extend([
            f"    IF EXISTS (SELECT 1 FROM publications WHERE year = {year}) THEN",
            f"        RAISE EXCEPTION 'publication year {year} already exists; use replace mode explicitly';",
            "    END IF;",
        ])

    pub_values = _values([
        year,
        publication.get("pub_no"),
        publication["title"],
        publication.get("page_count"),
    ])
    lines.extend([
        "    INSERT INTO publications (year, pub_no, title, page_count)",
        f"    VALUES ({pub_values}) RETURNING pub_id INTO v_pub_id;",
    ])
    for unit in data["statistics"]:
        _append_statistic(lines, unit, year)

    lines.extend([
        "    UPDATE statistics",
        "    SET search_doc = to_tsvector(",
        "        'simple',",
        "        coalesce(title_ko,'') || ' ' || coalesce(title_en,'') || ' ' ||",
        "        coalesce(chapter,'') || ' ' || coalesce(ref_id,'')",
        "    )",
        "    WHERE pub_id = v_pub_id;",
        "END",
        "$statyearbook_load$;",
    ])
    if include_transaction:
        lines.append("COMMIT;")
    lines.append("")
    return "\n".join(lines)
