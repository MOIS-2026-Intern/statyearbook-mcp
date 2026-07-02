# -*- coding: utf-8 -*-
import json
import os
import re
from hashlib import sha1
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import CallToolResult, ResourceLink, TextContent

from app.asset_server import build_asset_url, visualization_dir
from app.db import connect
from app.tool_descriptions import VISUALIZE

ChartType = Literal[
    "auto",
    "bar",
    "grouped_bar",
    "stacked_bar",
    "line",
    "area",
    "scatter",
    "heatmap",
    "donut",
    "table",
]

VALID_CHART_TYPES = {
    "auto",
    "bar",
    "grouped_bar",
    "stacked_bar",
    "line",
    "area",
    "scatter",
    "heatmap",
    "donut",
    "table",
}
SHARE_WORDS = ("비중", "구성", "구성비", "점유", "점유율", "분포", "share", "ratio", "composition")
TREND_WORDS = ("추이", "연도별", "시계열", "변화", "trend", "yearly", "over time")
DELTA_WORDS = ("증감", "전년", "증가", "감소", "변화량", "delta", "change")
TOTAL_WORDS = ("계", "합계", "총계", "total")
MAX_SERIES = 12

TABLE_SQL = """
    SELECT s.stat_id, s.ref_id, s.year, s.title_ko, s.title_en,
           s.unit, s.base_date,
           t.seq AS table_seq, t.caption, t.n_rows, t.n_cols,
           t.body, t.table_md
    FROM statistics s
    JOIN stat_tables t ON t.stat_id = s.stat_id
    WHERE s.stat_id = %s AND t.seq = %s
"""


# 시각화 대상 통계표를 DB에서 가져온다.
def _fetch_table(stat_id: int, table_seq: int) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(TABLE_SQL, (stat_id, table_seq))
        row = cur.fetchone()

    if row and isinstance(row.get("body"), str):
        row["body"] = json.loads(row["body"])
    return row


# 표 셀 텍스트를 정리한다.
def _cell_text(cell: dict) -> str:
    return (cell.get("text") or "").replace("\n", " ").strip()


# 표 셀 병합 크기를 읽는다.
def _cell_span(cell: dict) -> tuple[int, int]:
    return cell.get("colSpan", 1) or 1, cell.get("rowSpan", 1) or 1


# 병합 셀 텍스트를 2차원 그리드에 채운다.
def _fill_grid(grid: list, row: int, col: int, col_span: int, row_span: int, text: str) -> None:
    n_rows = len(grid)
    n_cols = len(grid[0]) if grid else 0
    for dr in range(row_span):
        for dc in range(col_span):
            rr, cc = row + dr, col + dc
            if rr < n_rows and cc < n_cols:
                grid[rr][cc] = text


# JSONB 표 본문을 2차원 텍스트 그리드로 펼친다.
def _cells_to_grid(body: dict) -> list[list[str]]:
    n_rows = body.get("rows", 0) or len(body.get("cells", []))
    n_cols = body.get("cols", 0)
    if n_cols <= 0 and body.get("cells"):
        n_cols = max(len(row) for row in body["cells"])

    grid = [[None] * n_cols for _ in range(n_rows)]
    for r, row in enumerate(body.get("cells", [])):
        c = 0
        for cell in row:
            while c < n_cols and grid[r][c] is not None:
                c += 1
            if c >= n_cols:
                break

            text = _cell_text(cell)
            col_span, row_span = _cell_span(cell)
            _fill_grid(grid, r, c, col_span, row_span, text)
            c += col_span

    return [[value if value is not None else "" for value in row] for row in grid]


# 전 컬럼 병합된 캡션/단위 행을 데이터 영역에서 제외한다.
def _caption_row_indexes(body: dict) -> set[int]:
    n_cols = body.get("cols", 0)
    skip = set()
    for r, row in enumerate(body.get("cells", [])):
        if row and (row[0].get("colSpan", 1) or 1) >= n_cols:
            skip.add(r)
    return skip


# 라벨 비교에 쓰도록 공백을 정리한다.
def _clean_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


# 빈 헤더와 중복 헤더를 안전한 컬럼명으로 바꾼다.
def _unique_headers(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    names: list[str] = []
    for idx, value in enumerate(header, start=1):
        base = _clean_label(value) or f"column_{idx}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        names.append(base if count == 1 else f"{base} #{count}")
    return names


# 데이터 중간에 반복된 헤더 행인지 판단한다.
def _looks_like_repeated_header(row: list[str], headers: list[str]) -> bool:
    cleaned = [_clean_label(value) for value in row]
    return cleaned == headers or sum(1 for left, right in zip(cleaned, headers) if left == right) >= 2


# 행에 숫자나 연도 값이 있어 데이터 행으로 볼 수 있는지 판단한다.
def _looks_like_data_row(row: list[str]) -> bool:
    nonempty = [_clean_label(value) for value in row if _clean_label(value)]
    if not nonempty:
        return False
    numeric_like = sum(
        1 for value in nonempty
        if _parse_number(value) is not None or _parse_year(value) is not None
    )
    return numeric_like >= 1


# 여러 헤더 행을 컬럼별로 합쳐 최종 헤더를 만든다.
def _combine_header_rows(header_rows: list[list[str]], width: int) -> list[str]:
    headers: list[str] = []
    for col_idx in range(width):
        parts: list[str] = []
        for row in header_rows:
            value = _clean_label(row[col_idx]) if col_idx < len(row) else ""
            if value and value not in parts:
                parts.append(value)
        headers.append(" ".join(parts))
    return _unique_headers(headers)


# 표 그리드를 dict row 목록으로 변환한다.
def _body_to_rows(body: dict) -> tuple[list[str], list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    grid = _cells_to_grid(body)
    caption_rows = _caption_row_indexes(body)
    usable_rows = [
        row for idx, row in enumerate(grid)
        if idx not in caption_rows and any(_clean_label(cell) for cell in row)
    ]
    if not usable_rows:
        return [], [], ["표 본문에서 시각화 가능한 행을 찾지 못했습니다."]

    if body.get("hasHeader", True):
        data_start = next(
            (idx for idx, row in enumerate(usable_rows) if _looks_like_data_row(row)),
            1,
        )
        header_rows = usable_rows[:data_start] or [usable_rows[0]]
        headers = _combine_header_rows(header_rows, len(usable_rows[0]))
        data_rows = usable_rows[data_start:]
    else:
        headers = [f"column_{idx}" for idx in range(1, len(usable_rows[0]) + 1)]
        data_rows = usable_rows

    rows: list[dict[str, str]] = []
    for row in data_rows:
        if _looks_like_repeated_header(row, headers):
            continue
        record = {headers[idx]: _clean_label(row[idx]) if idx < len(row) else "" for idx in range(len(headers))}
        if any(record.values()):
            rows.append(record)

    if not rows:
        warnings.append("헤더를 제외한 데이터 행을 찾지 못했습니다.")
    return headers, rows, warnings


# 문자열 숫자 표기를 float 값으로 변환한다.
def _parse_number(value: Any) -> float | None:
    text = _clean_label(value)
    if not text or text in {"-", "－", "—", "–"}:
        return None

    normalized = (
        text.replace(",", "")
        .replace("%", "")
        .replace("−", "-")
        .replace("△", "-")
        .replace("▲", "-")
        .replace(" ", "")
    )
    if re.fullmatch(r"\([-+]?\d+(?:\.\d+)?\)", normalized):
        normalized = "-" + normalized.strip("()")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized):
        return None
    return float(normalized)


# 값 앞부분에서 연도를 추출한다.
def _parse_year(value: Any) -> int | None:
    match = re.match(r"^\s*((?:18|19|20)\d{2})", str(value or ""))
    if not match:
        return None
    return int(match.group(1))


# 헤더 문자열 안에서 연도를 추출한다.
def _parse_header_year(value: Any) -> int | None:
    match = re.search(r"((?:18|19|20)\d{2})", str(value or ""))
    if not match:
        return None
    return int(match.group(1))


# 컬럼명/질의어 비교용 키로 정규화한다.
def _normalize_key(value: Any) -> str:
    return re.sub(r"[^\w가-힣]+", "", str(value or "").lower())


# 한국어 라벨 내부의 불필요한 띄어쓰기를 줄인다.
def _compact_korean_spacing(value: Any) -> str:
    text = _clean_label(value)
    return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", text)


# 차트에 표시할 범주 라벨을 보기 좋게 다듬는다.
def _display_category_label(value: Any) -> str:
    text = _compact_korean_spacing(value)
    match = re.match(r"([가-힣･·ㆍ\s]+)", text)
    if match:
        korean = _clean_label(match.group(1))
        if len(re.sub(r"[^가-힣]", "", korean)) >= 2:
            return korean
    return text


# 각 컬럼의 숫자형/연도형 여부를 계산한다.
def _profile_columns(columns: list[str], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for column in columns:
        values = [row.get(column, "") for row in rows]
        nonempty = [value for value in values if _clean_label(value)]
        count = len(nonempty) or 1
        numeric_count = sum(1 for value in nonempty if _parse_number(value) is not None)
        year_count = sum(1 for value in nonempty if _parse_year(value) is not None)
        normalized = _normalize_key(column)
        is_year = year_count / count >= 0.6 and (
            "연도" in column or "년도" in column or "year" in normalized or year_count == len(nonempty)
        )
        is_numeric = numeric_count / count >= 0.6 and not is_year
        profiles.append({
            "name": column,
            "nonempty": len(nonempty),
            "numeric_ratio": round(numeric_count / count, 3),
            "year_ratio": round(year_count / count, 3),
            "is_numeric": is_numeric,
            "is_year": is_year,
        })
    return profiles


# 컬럼 프로필을 이름으로 빠르게 찾는 맵으로 바꾼다.
def _profile_by_name(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {profile["name"]: profile for profile in profiles}


# 요청한 별칭이 컬럼 프로필과 맞는지 확인한다.
def _matches_alias(requested: str, profile: dict[str, Any]) -> bool:
    label = _normalize_key(profile["name"])
    key = _normalize_key(requested)
    if key in {"year", "date", "연도", "년도"}:
        return profile["is_year"]
    if key in {"category", "classification", "label", "name", "구분", "분류"}:
        return not profile["is_numeric"] and not profile["is_year"]
    if key in {"total", "sum", "계", "합계"}:
        return _is_total_label(profile["name"]) or "total" in label
    return False


# 요청한 컬럼명을 실제 표 컬럼명으로 해석한다.
def _resolve_column(requested: str | None, profiles: list[dict[str, Any]]) -> str | None:
    if not requested:
        return None

    key = _normalize_key(requested)
    for profile in profiles:
        if _normalize_key(profile["name"]) == key:
            return profile["name"]
    for profile in profiles:
        label = _normalize_key(profile["name"])
        if key and (key in label or label in key):
            return profile["name"]
    for profile in profiles:
        if _matches_alias(requested, profile):
            return profile["name"]
    return None


# 라벨에서 질의 매칭에 쓸 토큰을 뽑는다.
def _label_tokens(label: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[가-힣A-Za-z0-9%]+", label)
        if len(token) >= 2
    ]


# 질의어와 가장 잘 맞는 후보 컬럼을 고른다.
def _pick_column_from_query(query: str | None, candidates: list[str]) -> str | None:
    if not query:
        return None

    query_text = query.lower()
    scored: list[tuple[int, str]] = []
    for column in candidates:
        score = sum(1 for token in _label_tokens(column) if token in query_text)
        if score:
            scored.append((score, column))

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], candidates.index(item[1])))
    return scored[0][1]


# 여러 요청 텍스트를 하나의 검색 문자열로 합친다.
def _query_text(*values: str | None) -> str:
    return " ".join(value for value in values if value)


# 텍스트에 지정한 키워드가 포함됐는지 확인한다.
def _contains_any(text: str | None, words: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in words)


# 요청이 추이형 차트를 의도하는지 판단한다.
def _wants_trend_chart(query: str | None, chart_type: str, x: str | None) -> bool:
    if chart_type in {"line", "area"}:
        return True
    if _normalize_key(x) in {"year", "date", "연도", "년도"}:
        return True
    return _contains_any(query, TREND_WORDS)


# 요청이 증감/변화량 차트를 의도하는지 판단한다.
def _wants_delta_chart(query: str | None) -> bool:
    return _contains_any(query, DELTA_WORDS)


# 연도가 들어간 숫자 컬럼들을 연도순으로 찾는다.
def _year_value_columns(profiles: list[dict[str, Any]]) -> list[tuple[int, str]]:
    columns = []
    for profile in profiles:
        year = _parse_header_year(profile["name"])
        if year is not None and profile["is_numeric"]:
            columns.append((year, profile["name"]))
    return sorted(columns, key=lambda item: item[0])


# 행 라벨과 질의어를 비교할 검색어 후보를 만든다.
def _label_match_terms(value: Any) -> list[str]:
    label = _compact_korean_spacing(value)
    terms = {_normalize_key(label)}
    korean = re.sub(r"[^가-힣]+", "", label)
    if len(korean) >= 2:
        terms.add(korean.lower())
    for token in re.findall(r"[A-Za-z0-9]+", label):
        if len(token) >= 2:
            terms.add(token.lower())
    return [term for term in terms if term]


# 행 라벨이 질의어와 얼마나 맞는지 점수화한다.
def _row_match_score(row_label: str, query_text: str) -> int:
    query_key = _normalize_key(query_text)
    if not query_key:
        return 0

    score = 0
    for term in _label_match_terms(row_label):
        if term and term in query_key:
            score = max(score, len(term))
    return score


# wide 연도 표에서 질의 대상이 되는 행을 고른다.
def _pick_focus_row(
    rows: list[dict[str, str]],
    category_column: str,
    query: str | None,
    x: str | None,
    y: str | None,
    group: str | None,
) -> dict[str, str] | None:
    text = _query_text(query, x, y, group)
    scored = [
        (_row_match_score(row.get(category_column, ""), text), idx, row)
        for idx, row in enumerate(rows)
    ]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None

    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][2]


# x축으로 쓸 컬럼을 연도/범주 우선순위로 고른다.
def _pick_x_column(profiles: list[dict[str, Any]], query: str | None) -> str | None:
    year_columns = [profile["name"] for profile in profiles if profile["is_year"]]
    query_match = _pick_column_from_query(query, year_columns)
    if query_match:
        return query_match
    if year_columns:
        return year_columns[0]

    categorical_columns = [
        profile["name"]
        for profile in profiles
        if not profile["is_numeric"] and not profile["is_year"]
    ]
    query_match = _pick_column_from_query(query, categorical_columns)
    if query_match:
        return query_match
    return categorical_columns[0] if categorical_columns else (profiles[0]["name"] if profiles else None)


# 라벨이 합계/총계 행인지 확인한다.
def _is_total_label(value: Any) -> bool:
    text = _clean_label(value).lower()
    return any(text == word or text.startswith(f"{word} ") for word in TOTAL_WORDS)


# 행에서 x축 값을 꺼내 축 타입에 맞게 변환한다.
def _row_x_value(row: dict[str, str], x_column: str | None, profile: dict[str, Any] | None) -> Any:
    if not x_column:
        return ""
    raw = row.get(x_column, "")
    if profile and profile["is_year"]:
        return _parse_year(raw) or raw
    parsed = _parse_number(raw) if profile and profile["is_numeric"] else None
    return parsed if parsed is not None else raw


# 너무 많은 계열은 값 합계 기준 상위 계열만 남긴다.
def _limit_series(records: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    series_names = []
    for record in records:
        series = record.get("series")
        if series is not None and series not in series_names:
            series_names.append(series)
    if len(series_names) <= MAX_SERIES:
        return records

    totals: dict[str, float] = {}
    for record in records:
        series = record.get("series")
        if series is not None:
            totals[series] = totals.get(series, 0.0) + abs(float(record["value"]))
    keep = {
        name for name, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:MAX_SERIES]
    }
    warnings.append(f"계열이 {len(series_names)}개라 상위 {MAX_SERIES}개 계열만 표시했습니다.")
    return [record for record in records if record.get("series") in keep]


# 너무 많은 범주는 값 합계 기준 상위 범주만 남긴다.
def _limit_categories(
    records: list[dict[str, Any]],
    chart_type: str,
    x_is_year: bool,
    top_n: int | None,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if x_is_year or chart_type in {"line", "area", "scatter", "table"}:
        return records

    default_limit = 8 if chart_type == "donut" else 20
    limit = top_n if top_n and top_n > 0 else default_limit
    categories = []
    for record in records:
        x_value = record.get("x")
        if x_value not in categories:
            categories.append(x_value)
    if len(categories) <= limit:
        return records

    totals: dict[Any, float] = {}
    for record in records:
        totals[record["x"]] = totals.get(record["x"], 0.0) + abs(float(record["value"]))
    keep = {
        name for name, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    }
    warnings.append(f"범주가 {len(categories)}개라 상위 {limit}개 범주만 표시했습니다.")
    return [record for record in records if record["x"] in keep]


# 요청이 비중/구성비 차트를 의도하는지 판단한다.
def _wants_share_chart(query: str | None) -> bool:
    text = (query or "").lower()
    return any(word in text for word in SHARE_WORDS)


# 표 메타데이터와 선택 범주로 차트 제목을 만든다.
def _chart_title(table: dict, subtitle: str | None = None) -> str:
    title = table["title_ko"]
    if subtitle:
        title = f"{subtitle} {title}"
    if table["table_seq"] and table["table_seq"] != 1:
        title = f"{title} ({table['table_seq']})"
    return title


# 요청과 데이터 구조를 바탕으로 최종 차트 타입을 결정한다.
def _select_chart(
    requested: str,
    query: str | None,
    has_records: bool,
    x_profile: dict[str, Any] | None,
    has_group: bool,
    warnings: list[str],
) -> tuple[str, str, str]:
    requested_type = requested if requested in VALID_CHART_TYPES else "auto"
    if requested_type != requested:
        warnings.append(f"지원하지 않는 차트 타입 '{requested}' 대신 auto를 사용했습니다.")

    x_is_year = bool(x_profile and x_profile["is_year"])
    x_is_numeric = bool(x_profile and x_profile["is_numeric"])

    if not has_records:
        return "table", "server_fallback", "시각화 가능한 숫자 데이터가 없어 표 이미지로 대체했습니다."

    if requested_type == "auto":
        if _wants_share_chart(query) and not x_is_year and not has_group:
            return "donut", "server_auto", "질의가 구성비/비중을 요구하고 단일 범주-값 구조라 도넛형을 선택했습니다."
        if x_is_year:
            return "line", "server_auto", "연도 축이 있는 숫자 데이터라 추이 확인에 적합한 선그래프를 선택했습니다."
        if has_group:
            return "grouped_bar", "server_auto", "범주와 계열을 함께 비교하기 위해 그룹 막대그래프를 선택했습니다."
        return "bar", "server_auto", "범주별 숫자 비교에 적합한 막대그래프를 선택했습니다."

    if requested_type == "donut" and (x_is_year or has_group):
        fallback = "line" if x_is_year else "grouped_bar"
        return fallback, "server_fallback", "도넛형은 단일 시점의 구성비에 적합해 요청 차트를 대체했습니다."
    if requested_type == "scatter" and not x_is_numeric:
        fallback = "line" if x_is_year else "bar"
        return fallback, "server_fallback", "산점도에는 숫자형 x축이 필요해 요청 차트를 대체했습니다."
    if requested_type == "heatmap" and not has_group:
        return "bar", "server_fallback", "히트맵에는 두 개의 범주 축이 필요해 막대그래프로 대체했습니다."
    if requested_type == "bar" and has_group:
        return "grouped_bar", "server_fallback", "계열 컬럼이 있어 그룹 막대그래프로 보정했습니다."

    return requested_type, "client_spec_validated", "클라이언트가 지정한 차트 타입을 데이터 구조 검증 후 사용했습니다."


# 차트 타입에 맞게 레코드 표시 순서를 정한다.
def _sort_records(records: list[dict[str, Any]], x_is_year: bool, chart_type: str) -> list[dict[str, Any]]:
    if x_is_year or chart_type in {"line", "area", "scatter"}:
        return sorted(records, key=lambda record: (record.get("x") is None, record.get("x"), str(record.get("series", ""))))
    if chart_type in {"bar", "donut"}:
        return sorted(records, key=lambda record: abs(float(record["value"])), reverse=True)
    return records


# 행은 범주, 열은 연도인 표를 시계열 차트 spec으로 변환한다.
def _wide_year_time_series_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    columns: list[str],
    source_rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any] | None:
    requested_type = chart_type if chart_type in VALID_CHART_TYPES else "auto"
    if requested_type != chart_type:
        warnings.append(f"지원하지 않는 차트 타입 '{chart_type}' 대신 auto를 사용했습니다.")

    if not _wants_trend_chart(query, requested_type, x):
        return None

    year_columns = _year_value_columns(profiles)
    if len(year_columns) < 2:
        return None

    profile_map = _profile_by_name(profiles)
    category_columns = [
        profile["name"]
        for profile in profiles
        if not profile["is_numeric"] and not profile["is_year"]
    ]
    category_column = None
    if x and _normalize_key(x) not in {"year", "date", "연도", "년도"}:
        category_column = _resolve_column(x, profiles)
    category_column = category_column or (category_columns[0] if category_columns else None)
    if category_column is None:
        return None

    focus_row = _pick_focus_row(source_rows, category_column, query, x, y, group)
    if focus_row is None and len(source_rows) == 1:
        focus_row = source_rows[0]
    if focus_row is None:
        return None

    records: list[dict[str, Any]] = []
    for year, column in year_columns:
        value = _parse_number(focus_row.get(column))
        if value is not None:
            records.append({"x": year, "value": value, "series": None})
    if len(records) < 2:
        return None

    selected_category = _display_category_label(focus_row.get(category_column))
    selected_type = "area" if requested_type == "area" else "line"
    if requested_type == "auto":
        decision_source = "server_auto"
        reason = "행이 범주, 열이 연도인 표에서 질의 대상 행을 찾아 연도별 추이 선그래프로 변환했습니다."
    elif requested_type in {"line", "area"}:
        decision_source = "client_spec_validated"
        reason = "클라이언트가 지정한 추이 차트를 wide 연도 표 구조에 맞게 검증해 사용했습니다."
    else:
        decision_source = "server_fallback"
        reason = "질의가 특정 범주의 연도별 추이를 요구해 요청 차트를 선그래프로 대체했습니다."

    delta_records: list[dict[str, Any]] = []
    if _wants_delta_chart(query):
        for prev, cur in zip(records, records[1:]):
            delta_records.append({
                "x": cur["x"],
                "value": cur["value"] - prev["value"],
                "series": "전년 대비 증감",
            })

    chart: dict[str, Any] = {
        "type": selected_type,
        "requested_type": chart_type,
        "decision_source": decision_source,
        "reason": reason,
        "title": _chart_title(table, selected_category),
        "x": "year",
        "y": selected_category,
        "group": None,
        "unit": table["unit"],
    }
    if delta_records:
        chart["secondary"] = {
            "type": "bar",
            "x": "year",
            "y": "delta",
            "unit": table["unit"],
            "reason": "질의에 증감/전년 대비 의도가 있어 보조 막대 차트를 함께 렌더링했습니다.",
        }

    return {
        "ok": True,
        "version": "0.1",
        "library": "seaborn",
        "renderer": "matplotlib",
        "stat": {
            "stat_id": table["stat_id"],
            "ref_id": table["ref_id"],
            "year": table["year"],
            "title_ko": table["title_ko"],
            "title_en": table["title_en"],
            "unit": table["unit"],
            "base_date": table["base_date"],
            "table_seq": table["table_seq"],
            "caption": table["caption"],
        },
        "request": {
            "query": query,
            "chart_type": chart_type,
            "x": x,
            "y": y,
            "group": group,
            "top_n": top_n,
        },
        "chart": chart,
        "columns": profiles,
        "transform": {
            "type": "wide_year_row_to_time_series",
            "category_column": category_column,
            "selected_category": selected_category,
            "year_columns": [{"year": year, "column": column} for year, column in year_columns],
        },
        "data": {
            "records": records,
            "delta_records": delta_records,
            "record_count": len(records),
            "source_row_count": len(source_rows),
            "table_preview": source_rows[:20],
        },
        "warnings": warnings,
    }


# 표 데이터와 요청값을 차트 렌더링용 spec으로 만든다.
def _build_plot_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
) -> dict[str, Any]:
    columns, source_rows, warnings = _body_to_rows(table["body"])
    profiles = _profile_columns(columns, source_rows)
    profile_map = _profile_by_name(profiles)

    wide_spec = _wide_year_time_series_spec(
        table,
        query,
        chart_type,
        x,
        y,
        group,
        top_n,
        columns,
        source_rows,
        profiles,
        warnings,
    )
    if wide_spec is not None:
        return wide_spec

    x_column = _resolve_column(x, profiles) or _pick_x_column(profiles, query)
    group_column = _resolve_column(group, profiles)

    numeric_columns = [
        profile["name"]
        for profile in profiles
        if profile["is_numeric"] and profile["name"] not in {x_column, group_column}
    ]
    y_column = _resolve_column(y, profiles)
    if y_column and not profile_map[y_column]["is_numeric"]:
        warnings.append(f"'{y_column}' 컬럼은 숫자형으로 보기 어려워 y축에서 제외했습니다.")
        y_column = None
    if y_column is None:
        y_column = _pick_column_from_query(query, numeric_columns)

    records: list[dict[str, Any]] = []
    y_source: str | None = y_column
    series_source: str | None = group_column
    x_profile = profile_map.get(x_column) if x_column else None

    if y_column:
        for row in source_rows:
            value = _parse_number(row.get(y_column))
            if value is None:
                continue
            records.append({
                "x": _row_x_value(row, x_column, x_profile),
                "value": value,
                "series": row.get(group_column) if group_column else None,
            })
    elif numeric_columns:
        y_source = "value"
        if len(source_rows) == 1 and not group_column:
            x_column = "metric"
            x_profile = None
            series_source = None
            row = source_rows[0]
            for column in numeric_columns:
                value = _parse_number(row.get(column))
                if value is not None:
                    records.append({"x": column, "value": value, "series": None})
        else:
            series_source = "metric" if not group_column else group_column
            for row in source_rows:
                x_value = _row_x_value(row, x_column, x_profile)
                for column in numeric_columns:
                    value = _parse_number(row.get(column))
                    if value is not None:
                        series = row.get(group_column) if group_column else column
                        records.append({"x": x_value, "value": value, "series": series})

    records = _limit_series(records, warnings)

    has_group = any(record.get("series") for record in records)
    selected_type, decision_source, reason = _select_chart(
        chart_type,
        query,
        bool(records),
        x_profile,
        has_group,
        warnings,
    )
    if selected_type == "donut":
        records = [record for record in records if not _is_total_label(record.get("x"))]

    x_is_year = bool(x_profile and x_profile["is_year"])
    records = _limit_categories(records, selected_type, x_is_year, top_n, warnings)
    records = _sort_records(records, x_is_year, selected_type)

    return {
        "ok": True,
        "version": "0.1",
        "library": "seaborn",
        "renderer": "matplotlib",
        "stat": {
            "stat_id": table["stat_id"],
            "ref_id": table["ref_id"],
            "year": table["year"],
            "title_ko": table["title_ko"],
            "title_en": table["title_en"],
            "unit": table["unit"],
            "base_date": table["base_date"],
            "table_seq": table["table_seq"],
            "caption": table["caption"],
        },
        "request": {
            "query": query,
            "chart_type": chart_type,
            "x": x,
            "y": y,
            "group": group,
            "top_n": top_n,
        },
        "chart": {
            "type": selected_type,
            "requested_type": chart_type,
            "decision_source": decision_source,
            "reason": reason,
            "title": _chart_title(table),
            "x": x_column,
            "y": y_source,
            "group": series_source if has_group else None,
            "unit": table["unit"],
        },
        "columns": profiles,
        "data": {
            "records": records,
            "record_count": len(records),
            "source_row_count": len(source_rows),
            "table_preview": source_rows[:20],
        },
        "warnings": warnings,
    }


# matplotlib, pandas, seaborn을 지연 로드한다.
def _load_plotting():
    try:
        cache_dir = Path(os.environ.get("MPLCONFIGDIR", Path(os.environ.get("TMPDIR", "/tmp")) / "statyearbook-matplotlib"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd
        import seaborn as sns
    except ModuleNotFoundError as exc:
        missing = exc.name or "시각화 라이브러리"
        raise RuntimeError(f"{missing} 패키지가 설치되어 있지 않습니다. requirements.txt 설치가 필요합니다.") from exc

    return plt, pd, sns


# 차트 테마와 한글 폰트 설정을 적용한다.
def _configure_plot(plt: Any, sns: Any) -> None:
    from matplotlib import font_manager

    sns.set_theme(style="whitegrid")
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"):
        if candidate in installed:
            plt.rcParams["font.family"] = candidate
            break
    plt.rcParams["axes.unicode_minus"] = False


# 단위 메타데이터로 y축 라벨을 만든다.
def _value_axis_label(unit: str | None) -> str:
    if unit:
        return f"{unit} 수"
    return "값"


# 선그래프 y축 범위에 여백을 더한다.
def _line_ylim(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        pad = max(abs(min_value) * 0.05, 1.0)
    else:
        pad = max((max_value - min_value) * 0.2, 1.0)
    lower = min_value - pad
    upper = max_value + pad
    if min_value >= 0:
        lower = max(0.0, lower)
    return lower, upper


# 공통 축 제목, 라벨, 눈금 회전을 적용한다.
def _finish_axes(ax: Any, title: str, unit: str | None) -> None:
    ax.set_title(title, pad=14)
    ax.set_xlabel("")
    ax.set_ylabel(unit or "value")
    labels = [label.get_text() for label in ax.get_xticklabels()]
    if len(labels) > 6 or any(len(label) > 10 for label in labels):
        ax.tick_params(axis="x", labelrotation=35)
        for label in ax.get_xticklabels():
            label.set_horizontalalignment("right")


# 표 미리보기를 PNG 표 이미지로 렌더링한다.
def _render_table_image(spec: dict[str, Any], plt: Any) -> bytes:
    rows = spec["data"]["table_preview"][:12]
    columns = [profile["name"] for profile in spec["columns"]][:6]
    cell_text = [[row.get(column, "") for column in columns] for row in rows]
    fig_height = max(3.0, 1.0 + len(cell_text) * 0.35)
    fig, ax = plt.subplots(figsize=(11, fig_height))
    ax.axis("off")
    ax.set_title(spec["chart"]["title"], pad=14)
    table = ax.table(cellText=cell_text, colLabels=columns, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)
    return _fig_to_png(fig, plt)


# 단일 시계열과 선택적 증감 보조 차트를 PNG로 렌더링한다.
def _render_single_line_image(spec: dict[str, Any], plt: Any, pd: Any) -> bytes:
    records = spec["data"]["records"]
    df = pd.DataFrame(records)
    labels = [str(value) for value in df["x"].tolist()]
    values = [float(value) for value in df["value"].tolist()]
    delta_records = spec["data"].get("delta_records") or []
    title = spec["chart"]["title"]
    unit = spec["chart"].get("unit")
    value_label = _value_axis_label(unit)

    if delta_records:
        fig, (ax1, ax2) = plt.subplots(
            2,
            1,
            figsize=(10, 7),
            gridspec_kw={"height_ratios": [3, 2]},
        )
    else:
        fig, ax1 = plt.subplots(figsize=(10, 5.5))
        ax2 = None

    positions = list(range(len(labels)))
    ax1.plot(positions, values, color="#2a78d6", linewidth=2, marker="o", markersize=6)
    ax1.set_xticks(positions)
    ax1.set_xticklabels(labels)
    ax1.set_ylim(*_line_ylim(values))
    ax1.set_title(f"{title} 연도별 {value_label}", fontsize=13, pad=12)
    ax1.set_xlabel("")
    ax1.set_ylabel(unit or "value")
    ax1.grid(axis="y", color="#e1e0d9")
    for x_value, y_value in zip(positions, values):
        label = f"{y_value:g}"
        ax1.annotate(label, (x_value, y_value), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)

    if ax2 is not None:
        delta_df = pd.DataFrame(delta_records)
        delta_labels = [str(value) for value in delta_df["x"].tolist()]
        deltas = [float(value) for value in delta_df["value"].tolist()]
        delta_positions = list(range(len(delta_labels)))
        colors = ["#e34948" if value < 0 else "#2a78d6" if value > 0 else "#9a9a9a" for value in deltas]
        ax2.bar(delta_positions, deltas, color=colors, width=0.6)
        ax2.set_xticks(delta_positions)
        ax2.set_xticklabels(delta_labels)
        ax2.axhline(0, color="#c3c2b7", linewidth=0.8)
        ax2.set_title(f"전년 대비 증감 ({unit or '값'})", fontsize=13, pad=10)
        ax2.set_xlabel("")
        ax2.set_ylabel(unit or "value")
        ax2.grid(axis="y", color="#e1e0d9")

    fig.tight_layout()
    return _fig_to_png(fig, plt)


# matplotlib figure를 PNG 바이트로 변환하고 닫는다.
def _fig_to_png(fig: Any, plt: Any) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buffer.getvalue()


# 파일명에 안전하게 넣을 수 있는 문자열로 바꾼다.
def _safe_filename_part(value: Any) -> str:
    text = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(value or "")).strip("_")
    return text[:60] or "chart"


# PNG를 서빙 디렉터리에 쓰고 HTTP URL을 만든다. 실패하면 None을 돌려준다.
def _write_png_asset(spec: dict[str, Any], png_bytes: bytes) -> dict[str, Any] | None:
    chart = spec["chart"]
    digest = sha1(png_bytes).hexdigest()[:12]
    filename = "_".join([
        "statyearbook",
        str(spec["stat"]["stat_id"]),
        str(spec["stat"]["table_seq"]),
        _safe_filename_part(chart["type"]),
        digest,
    ]) + ".png"

    try:
        path = visualization_dir() / filename
        path.write_bytes(png_bytes)
    except OSError as exc:
        spec["warnings"].append(f"PNG 파일 저장에 실패했습니다: {exc}")
        return None

    url = build_asset_url(filename)
    title = _safe_filename_part(chart["title"])
    return {
        "image_path": str(path.resolve()),
        "image_url": url,
        "mime_type": "image/png",
        "markdown": f"![{title}]({url})" if url else None,
    }


# 차트 spec을 실제 PNG 이미지로 렌더링한다.
def _render_png(spec: dict[str, Any]) -> bytes:
    plt, pd, sns = _load_plotting()
    _configure_plot(plt, sns)

    chart_type = spec["chart"]["type"]
    title = spec["chart"]["title"]
    unit = spec["chart"].get("unit")

    if chart_type == "table" or not spec["data"]["records"]:
        return _render_table_image(spec, plt)

    df = pd.DataFrame(spec["data"]["records"])
    has_series = "series" in df.columns and df["series"].notna().any()
    if chart_type == "line" and not has_series:
        return _render_single_line_image(spec, plt, pd)

    width = 11
    height = 5.5 if len(df) <= 30 else 6.5
    fig, ax = plt.subplots(figsize=(width, height))

    if chart_type in {"bar", "grouped_bar"}:
        sns.barplot(data=df, x="x", y="value", hue="series" if has_series else None, ax=ax)
        _finish_axes(ax, title, unit)
    elif chart_type == "stacked_bar":
        pivot = df.pivot_table(index="x", columns="series", values="value", aggfunc="sum", fill_value=0)
        pivot.plot(kind="bar", stacked=True, ax=ax)
        _finish_axes(ax, title, unit)
    elif chart_type == "line":
        sns.lineplot(data=df, x="x", y="value", hue="series" if has_series else None, marker="o", ax=ax)
        _finish_axes(ax, title, unit)
    elif chart_type == "area":
        if has_series:
            pivot = df.pivot_table(index="x", columns="series", values="value", aggfunc="sum", fill_value=0)
            pivot.plot.area(ax=ax)
        else:
            positions = list(range(len(df)))
            ax.plot(positions, df["value"], marker="o")
            ax.fill_between(positions, df["value"], alpha=0.25)
            ax.set_xticks(positions)
            ax.set_xticklabels(df["x"])
        _finish_axes(ax, title, unit)
    elif chart_type == "scatter":
        sns.scatterplot(data=df, x="x", y="value", hue="series" if has_series else None, s=80, ax=ax)
        _finish_axes(ax, title, unit)
    elif chart_type == "heatmap":
        pivot = df.pivot_table(index="series", columns="x", values="value", aggfunc="sum", fill_value=0)
        sns.heatmap(pivot, annot=True, fmt=".0f", cmap="Blues", ax=ax)
        ax.set_title(title, pad=14)
        ax.set_xlabel("")
        ax.set_ylabel("")
    elif chart_type == "donut":
        donut_df = df.groupby("x", as_index=False)["value"].sum()
        ax.pie(
            donut_df["value"],
            labels=donut_df["x"],
            autopct="%1.1f%%",
            startangle=90,
            wedgeprops={"width": 0.42, "edgecolor": "white"},
        )
        ax.set_title(title, pad=14)
        ax.axis("equal")
    else:
        return _render_table_image(spec, plt)

    if has_series and chart_type not in {"heatmap", "donut"}:
        ax.legend(title="")
    fig.tight_layout()
    return _fig_to_png(fig, plt)


# x축이 연도인지 판별한다(Vega 축 타입 결정용).
def _vega_x_is_year(spec: dict[str, Any]) -> bool:
    x_name = spec["chart"].get("x")
    if x_name == "year":
        return True
    for profile in spec.get("columns", []):
        if profile.get("name") == x_name:
            return bool(profile.get("is_year"))
    return False


# 내부 차트 타입을 Vega-Lite mark/encoding 뷰로 변환한다.
def _vega_view(chart: dict[str, Any], has_series: bool, x_is_year: bool) -> dict[str, Any]:
    ctype = chart["type"]
    unit = chart.get("unit") or "값"

    if ctype == "donut":
        return {
            "mark": {"type": "arc", "innerRadius": 60},
            "encoding": {
                "theta": {"field": "value", "type": "quantitative"},
                "color": {"field": "x", "type": "nominal", "title": ""},
            },
        }
    if ctype == "heatmap":
        return {
            "mark": "rect",
            "encoding": {
                "x": {"field": "x", "type": "nominal", "title": ""},
                "y": {"field": "series", "type": "nominal", "title": ""},
                "color": {"field": "value", "type": "quantitative", "title": unit},
            },
        }

    mark_map: dict[str, Any] = {
        "bar": "bar",
        "grouped_bar": "bar",
        "stacked_bar": "bar",
        "line": {"type": "line", "point": True},
        "area": "area",
        "scatter": "point",
    }
    encoding: dict[str, Any] = {
        "x": {"field": "x", "type": "ordinal" if x_is_year else "nominal", "title": ""},
        "y": {"field": "value", "type": "quantitative", "title": unit},
    }
    if has_series:
        encoding["color"] = {"field": "series", "type": "nominal", "title": ""}
        if ctype == "grouped_bar":
            encoding["xOffset"] = {"field": "series"}
    return {"mark": mark_map.get(ctype, "bar"), "encoding": encoding}


# 클라이언트가 직접 렌더링할 수 있는 표준 Vega-Lite spec을 만든다.
def _vega_lite_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    chart = spec["chart"]
    records = spec["data"]["records"]
    if not records or chart["type"] == "table":
        return None

    has_series = any(record.get("series") for record in records)
    x_is_year = _vega_x_is_year(spec)
    values = [
        {"x": record.get("x"), "value": record.get("value"), "series": record.get("series")}
        for record in records
    ]

    view = _vega_view(chart, has_series, x_is_year)
    view["data"] = {"values": values}

    root: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": chart["title"],
    }

    delta_records = spec["data"].get("delta_records") or []
    if delta_records:
        unit = chart.get("unit") or "값"
        delta_view = {
            "title": f"전년 대비 증감 ({unit})",
            "data": {"values": [{"x": r["x"], "value": r["value"]} for r in delta_records]},
            "mark": "bar",
            "encoding": {
                "x": {"field": "x", "type": "ordinal", "title": ""},
                "y": {"field": "value", "type": "quantitative", "title": unit},
                "color": {
                    "condition": {"test": "datum.value < 0", "value": "#e34948"},
                    "value": "#2a78d6",
                },
            },
        }
        root["vconcat"] = [view, delta_view]
    else:
        root.update(view)
    return root


# 도구 응답에 넣을 요약 문구를 만든다.
def _summary_text(spec: dict[str, Any]) -> str:
    chart = spec["chart"]
    lines = [
        f"{chart['title']}",
        f"차트: {chart['type']} ({chart['decision_source']})",
        f"선택 이유: {chart['reason']}",
        f"데이터 포인트: {spec['data']['record_count']}개",
    ]
    asset = spec.get("asset")
    if asset and asset.get("image_url"):
        lines.append(f"이미지 URL(클릭/임베드 가능): {asset['image_url']}")
    if spec.get("vega_lite"):
        lines.append(
            "structuredContent.vega_lite 에 표준 Vega-Lite spec이 있어 "
            "위젯 렌더가 가능한 클라이언트는 인터랙티브 차트로 그릴 수 있습니다."
        )
    if spec["warnings"]:
        lines.append("경고: " + " / ".join(spec["warnings"]))
    return "\n".join(lines)


# MCP 오류 응답 객체를 만든다.
def _error_result(message: str, stat_id: int, table_seq: int) -> CallToolResult:
    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=message)],
        structuredContent={
            "ok": False,
            "stat_id": stat_id,
            "table_seq": table_seq,
            "error": message,
        },
    )


# visualize MCP 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    # 통계표를 PNG 이미지, HTTP 링크, Vega-Lite spec으로 반환한다.
    @mcp.tool(description=VISUALIZE)
    def visualize(
        stat_id: int,
        table_seq: int = 1,
        query: str | None = None,
        chart_type: ChartType = "auto",
        x: str | None = None,
        y: str | None = None,
        group: str | None = None,
        top_n: int | None = None,
        include_image: bool = True,
    ) -> CallToolResult:
        table = _fetch_table(stat_id, table_seq)
        if table is None:
            return _error_result("해당 stat_id/table_seq 통계표를 찾지 못했습니다.", stat_id, table_seq)

        spec = _build_plot_spec(table, query, chart_type, x, y, group, top_n)
        try:
            png_bytes = _render_png(spec)
        except RuntimeError as exc:
            return _error_result(str(exc), stat_id, table_seq)

        spec["asset"] = _write_png_asset(spec, png_bytes)
        spec["vega_lite"] = _vega_lite_spec(spec)
        asset = spec["asset"]

        content: list[Any] = []
        # 컨텍스트가 작은 클라이언트(sLLM)를 위해 인라인 이미지는 선택적으로 넣는다.
        if include_image:
            content.append(Image(data=png_bytes, format="png").to_image_content())
        content.append(TextContent(type="text", text=_summary_text(spec)))

        if asset and asset.get("image_url"):
            content.append(
                ResourceLink(
                    type="resource_link",
                    name=Path(asset["image_path"]).name,
                    title=spec["chart"]["title"],
                    uri=asset["image_url"],
                    description="렌더링된 통계 시각화 PNG (HTTP)",
                    mimeType="image/png",
                    size=len(png_bytes),
                )
            )

        return CallToolResult(
            content=content,
            structuredContent=spec,
        )
