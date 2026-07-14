import re
from typing import Any, Literal


TotalMode = Literal["auto", "include", "exclude"]

TREND_WORDS = ("추이", "연도별", "시계열", "변화", "trend", "yearly", "over time")
DELTA_WORDS = ("증감", "전년", "증가", "감소", "변화량", "delta", "change")
TOTAL_WORDS = ("계", "합계", "소계", "총계", "total", "subtotal")
MISSING_VALUES = {"", "-", "－", "—", "–"}


# 표 셀 텍스트를 정리한다.
def clean_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


# 표에서 값 없음으로 사용하는 기호인지 확인한다.
def is_missing_value(value: Any) -> bool:
    return clean_label(value) in MISSING_VALUES


# 표 셀의 텍스트를 읽는다.
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


# 빈 헤더와 중복 헤더를 안전한 컬럼명으로 바꾼다.
def _unique_headers(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    names: list[str] = []
    for idx, value in enumerate(header, start=1):
        base = clean_label(value) or f"column_{idx}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        names.append(base if count == 1 else f"{base} #{count}")
    return names


# 데이터 중간에 반복된 헤더 행인지 판단한다.
def _looks_like_repeated_header(row: list[str], headers: list[str]) -> bool:
    cleaned = [clean_label(value) for value in row]
    return cleaned == headers or sum(1 for left, right in zip(cleaned, headers) if left == right) >= 2


# 행에 숫자나 연도 값이 있어 데이터 행으로 볼 수 있는지 판단한다.
def _looks_like_data_row(row: list[str]) -> bool:
    nonempty = [clean_label(value) for value in row if clean_label(value)]
    if not nonempty:
        return False
    numeric_like = sum(
        1 for value in nonempty
        if parse_number(value) is not None or parse_year(value) is not None
    )
    return numeric_like >= 1


# 여러 헤더 행을 컬럼별로 합쳐 최종 헤더를 만든다.
def _combine_header_rows(header_rows: list[list[str]], width: int) -> list[str]:
    headers: list[str] = []
    for col_idx in range(width):
        parts: list[str] = []
        for row in header_rows:
            value = clean_label(row[col_idx]) if col_idx < len(row) else ""
            if value and value not in parts:
                parts.append(value)
        headers.append("_".join(parts))
    return _unique_headers(headers)


# 표 그리드를 dict row 목록으로 변환한다.
def body_to_rows(body: dict) -> tuple[list[str], list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    columns = body.get("columns") or []
    records = body.get("records") or []
    if columns and records:
        source_rows = [
            {column: clean_label(row.get(column, "")) for column in columns}
            for row in records
        ]
        return columns, source_rows, warnings

    grid = _cells_to_grid(body)
    caption_rows = _caption_row_indexes(body)
    usable_rows = [
        row for idx, row in enumerate(grid)
        if idx not in caption_rows and any(clean_label(cell) for cell in row)
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
        record = {headers[idx]: clean_label(row[idx]) if idx < len(row) else "" for idx in range(len(headers))}
        if any(record.values()):
            rows.append(record)

    if not rows:
        warnings.append("헤더를 제외한 데이터 행을 찾지 못했습니다.")
    return headers, rows, warnings


# 문자열 숫자 표기를 float 값으로 변환한다.
def parse_number(value: Any) -> float | None:
    text = clean_label(value)
    if is_missing_value(text):
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
def parse_year(value: Any) -> int | None:
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
def normalize_key(value: Any) -> str:
    return re.sub(r"[^\w가-힣]+", "", str(value or "").lower())


# 한국어 라벨 내부의 불필요한 띄어쓰기를 줄인다.
def _compact_korean_spacing(value: Any) -> str:
    text = clean_label(value)
    return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", text)


# 차트에 표시할 범주 라벨을 보기 좋게 다듬는다.
def display_category_label(value: Any) -> str:
    text = _compact_korean_spacing(value)
    match = re.match(r"([가-힣･·ㆍ\s]+)", text)
    if match:
        korean = clean_label(match.group(1))
        if len(re.sub(r"[^가-힣]", "", korean)) >= 2:
            return korean
    return text


# 각 컬럼의 숫자형/연도형 여부를 계산한다.
def profile_columns(columns: list[str], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for column in columns:
        values = [row.get(column, "") for row in rows]
        nonempty = [value for value in values if not is_missing_value(value)]
        count = len(nonempty) or 1
        numeric_count = sum(1 for value in nonempty if parse_number(value) is not None)
        year_count = sum(1 for value in nonempty if parse_year(value) is not None)
        normalized = normalize_key(column)
        is_year = year_count / count >= 0.6 and (
            "연도" in column or "년도" in column or "year" in normalized or year_count == len(nonempty)
        )
        is_numeric = numeric_count / count >= 0.6 and not is_year
        is_missing_only = not nonempty
        is_categorical = bool(nonempty) and not is_numeric and not is_year
        profiles.append({
            "name": column,
            "nonempty": len(nonempty),
            "numeric_ratio": round(numeric_count / count, 3),
            "year_ratio": round(year_count / count, 3),
            "is_numeric": is_numeric,
            "is_year": is_year,
            "is_categorical": is_categorical,
            "is_missing_only": is_missing_only,
        })
    return profiles


# 컬럼 프로필을 이름으로 빠르게 찾는 맵으로 바꾼다.
def profile_by_name(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {profile["name"]: profile for profile in profiles}


# 요청한 별칭이 컬럼 프로필과 맞는지 확인한다.
def _matches_alias(requested: str, profile: dict[str, Any]) -> bool:
    label = normalize_key(profile["name"])
    key = normalize_key(requested)
    if key in {"year", "date", "연도", "년도"}:
        return profile["is_year"]
    if key in {"category", "classification", "label", "name", "구분", "분류"}:
        return profile.get("is_categorical", False)
    if key in {"total", "sum", "계", "합계"}:
        return is_total_label(profile["name"]) or "total" in label
    return False


# 요청한 컬럼명을 실제 표 컬럼명으로 해석한다.
def resolve_column(requested: str | None, profiles: list[dict[str, Any]]) -> str | None:
    if not requested:
        return None

    key = normalize_key(requested)
    for profile in profiles:
        if normalize_key(profile["name"]) == key:
            return profile["name"]
    for profile in profiles:
        label = normalize_key(profile["name"])
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
def pick_column_from_query(query: str | None, candidates: list[str]) -> str | None:
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
def wants_trend_chart(query: str | None, chart_type: str, x: str | None) -> bool:
    if chart_type in {"line", "area"}:
        return True
    if normalize_key(x) in {"year", "date", "연도", "년도"}:
        return True
    return _contains_any(query, TREND_WORDS)


# 요청이 증감/변화량 차트를 의도하는지 판단한다.
def wants_delta_chart(query: str | None) -> bool:
    return _contains_any(query, DELTA_WORDS)


# 질의에 명시된 단일 연도를 찾는다.
def query_year(query: str | None) -> int | None:
    years = {_parse_header_year(match) for match in re.findall(r"(?:18|19|20)\d{2}", query or "")}
    years.discard(None)
    return next(iter(years)) if len(years) == 1 else None


# LLM이 명시적으로 추출한 연도를 우선하고 자연어 질의의 연도를 보조값으로 쓴다.
def requested_year(year: int | None, query: str | None) -> int | None:
    return year if year is not None else query_year(query)


# 명시된 연도·도시와 질의에 포함된 행 라벨을 원본 표 행에 적용한다.
def select_source_rows(
    rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    year: int | None,
    city: str | None,
    query: str | None,
) -> tuple[list[dict[str, str]], dict[str, Any], list[str]]:
    selected = list(rows)
    warnings: list[str] = []
    selection: dict[str, Any] = {
        "requested_year": year,
        "requested_city": city,
        "year_column": None,
        "city_column": None,
        "city_value": None,
        "query_row_value": None,
    }

    year_profile = next((profile for profile in profiles if profile["is_year"]), None)
    if year is not None and year_profile is not None:
        year_column = year_profile["name"]
        matches = [row for row in selected if parse_year(row.get(year_column)) == year]
        selection["year_column"] = year_column
        if not matches:
            warnings.append(f"표의 '{year_column}' 컬럼에서 {year}년 행을 찾지 못했습니다.")
            return [], selection, warnings
        selected = matches

    categorical_columns = [
        profile["name"] for profile in profiles if profile.get("is_categorical", False)
    ]
    if city:
        city_key = normalize_key(city)
        exact: list[tuple[str, str, dict[str, str]]] = []
        partial: list[tuple[str, str, dict[str, str]]] = []
        for row in selected:
            for column in categorical_columns:
                value = row.get(column, "")
                value_key = normalize_key(value)
                if not value_key:
                    continue
                item = (column, value, row)
                if value_key == city_key:
                    exact.append(item)
                elif city_key and (city_key in value_key or value_key in city_key):
                    partial.append(item)
        matches = exact or partial
        if not matches:
            warnings.append(f"표에서 도시·지역 '{city}'에 해당하는 행을 찾지 못했습니다.")
            return [], selection, warnings
        distinct_matches = {(column, value) for column, value, _ in matches}
        if not exact and len(distinct_matches) > 1:
            labels = ", ".join(sorted({value for _, value in distinct_matches}))
            warnings.append(f"도시·지역 '{city}'가 여러 행({labels})과 일치해 하나를 선택하지 않았습니다.")
            return [], selection, warnings
        matched_column, matched_value, _ = matches[0]
        selected = [row for row in selected if row.get(matched_column) == matched_value]
        selection["city_column"] = matched_column
        selection["city_value"] = matched_value
    elif query:
        query_key = normalize_key(query)
        candidates: list[tuple[int, str, str]] = []
        for column in categorical_columns:
            for row in selected:
                value = row.get(column, "")
                value_key = normalize_key(value)
                if len(value_key) >= 2 and value_key in query_key:
                    candidates.append((len(value_key), column, value))
        if candidates:
            candidates.sort(key=lambda item: -item[0])
            _, matched_column, matched_value = candidates[0]
            selected = [row for row in selected if row.get(matched_column) == matched_value]
            selection["query_row_value"] = matched_value

    selection["selected_row_count"] = len(selected)
    return selected, selection, warnings


# LLM이 원본 표에서 고른 행 조건을 실제 컬럼명과 셀 값에 엄격하게 대조한다.
def apply_exact_filters(
    rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    filters: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[str]]:
    selected = list(rows)
    columns = {profile["name"] for profile in profiles}
    applied: list[dict[str, Any]] = []
    errors: list[str] = []

    for item in filters:
        column = clean_label(item.get("column"))
        value = clean_label(item.get("value"))
        if column not in columns:
            errors.append(f"선택 조건의 컬럼 '{column}'이 원본 표에 없습니다.")
            continue
        if not value:
            errors.append(f"선택 조건 '{column}'의 값이 비어 있습니다.")
            continue

        matches = [row for row in selected if clean_label(row.get(column)) == value]
        applied.append({"column": column, "value": value, "matched_row_count": len(matches)})
        if not matches:
            errors.append(f"원본 표의 '{column}' 컬럼에서 값 '{value}'을 찾지 못했습니다.")
            selected = []
            continue
        selected = matches

    return ([] if errors else selected), applied, errors


# 평탄화된 헤더를 첫 '_' 앞의 최상위 헤더별 컬럼군으로 묶는다.
def column_family_groups(profiles: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for profile in profiles:
        name = profile["name"]
        if "_" not in name:
            continue
        if not profile["is_numeric"] and not profile.get("is_missing_only", False):
            continue
        prefix = clean_label(name.split("_", 1)[0])
        groups.setdefault(prefix, []).append(name)
    return {prefix: columns for prefix, columns in groups.items() if len(columns) >= 2}


# 평탄화된 다중 헤더에서 요청한 상위 헤더에 속하는 숫자 컬럼들을 찾는다.
def column_family(requested: str | None, profiles: list[dict[str, Any]]) -> list[str]:
    if not requested:
        return []
    key = normalize_key(requested)
    if not key:
        return []
    groups = column_family_groups(profiles)
    exact = [columns for prefix, columns in groups.items() if normalize_key(prefix) == key]
    if exact:
        return exact[0]
    matches = [
        columns
        for prefix, columns in groups.items()
        if key in normalize_key(prefix) or normalize_key(prefix) in key
    ]
    return matches[0] if len(matches) == 1 else []


# 상위 헤더를 제거해 차트에 표시할 하위 범주 라벨을 만든다.
def family_category_label(column: str) -> str:
    def part_label(part: str) -> str:
        cleaned = clean_label(part)
        bilingual = re.match(r"^(.+?)\s+(?=[A-Za-z]+(?:\s|$)|\d+s\b)", cleaned)
        if bilingual:
            return clean_label(bilingual.group(1))
        if re.fullmatch(r"[0-9가-힣･·ㆍ\s]+", cleaned) and re.search(r"[가-힣]", cleaned):
            return cleaned
        korean = re.match(r"([가-힣･·ㆍ\s]+)", cleaned)
        if korean and len(re.sub(r"[^가-힣]", "", korean.group(1))) >= 2:
            return clean_label(korean.group(1))
        return display_category_label(part)

    parts = column.split("_")[1:]
    return " / ".join(part_label(part) for part in parts) if parts else display_category_label(column)


# 합계 컬럼인지 컬럼명과 하위 범주 라벨을 기준으로 판별한다.
def is_total_column(column: str) -> bool:
    return is_total_label(column.rsplit("_", 1)[-1])


# 요청 파라미터를 우선하되 auto일 때 질의의 명시적 포함/제외 표현을 반영한다.
def resolve_total_mode(total_mode: TotalMode, query: str | None) -> TotalMode:
    if total_mode != "auto":
        return total_mode
    text = (query or "").lower()
    if _contains_any(text, ("합계 포함", "계 포함", "소계 포함", "총계 포함", "include total")):
        return "include"
    if _contains_any(text, ("합계 제외", "계 제외", "소계 제외", "총계 제외", "exclude total")):
        return "exclude"
    return "auto"


# 연도가 들어간 숫자 컬럼들을 연도순으로 찾는다.
def year_value_columns(profiles: list[dict[str, Any]]) -> list[tuple[int, str]]:
    columns = []
    for profile in profiles:
        year = _parse_header_year(profile["name"])
        if year is not None and profile["is_numeric"]:
            columns.append((year, profile["name"]))
    return sorted(columns, key=lambda item: item[0])


# 행 라벨과 질의어를 비교할 검색어 후보를 만든다.
def _label_match_terms(value: Any) -> list[str]:
    label = _compact_korean_spacing(value)
    terms = {normalize_key(label)}
    korean = re.sub(r"[^가-힣]+", "", label)
    if len(korean) >= 2:
        terms.add(korean.lower())
    for token in re.findall(r"[A-Za-z0-9]+", label):
        if len(token) >= 2:
            terms.add(token.lower())
    return [term for term in terms if term]


# 행 라벨이 질의어와 얼마나 맞는지 점수화한다.
def _row_match_score(row_label: str, query_text: str) -> int:
    query_key = normalize_key(query_text)
    if not query_key:
        return 0

    score = 0
    for term in _label_match_terms(row_label):
        if term and term in query_key:
            score = max(score, len(term))
    return score


# wide 연도 표에서 질의 대상이 되는 행을 고른다.
def pick_focus_row(
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
def pick_x_column(profiles: list[dict[str, Any]], query: str | None) -> str | None:
    year_columns = [profile["name"] for profile in profiles if profile["is_year"]]
    query_match = pick_column_from_query(query, year_columns)
    if query_match:
        return query_match
    if year_columns:
        return year_columns[0]

    categorical_columns = [
        profile["name"]
        for profile in profiles
        if profile.get("is_categorical", False)
    ]
    query_match = pick_column_from_query(query, categorical_columns)
    if query_match:
        return query_match
    return categorical_columns[0] if categorical_columns else (profiles[0]["name"] if profiles else None)


# 라벨이 합계/총계 행인지 확인한다.
def is_total_label(value: Any) -> bool:
    text = clean_label(value).lower()
    tokens = set(re.findall(r"[가-힣A-Za-z]+", text))
    return bool(tokens.intersection(TOTAL_WORDS))


# 차트 종류와 방향에 관계없이 합계·연도·지역 필터를 적용한다.
def filter_chart_records(
    records: list[dict[str, Any]],
    query: str | None,
    total_mode: TotalMode,
    target_year: int | None = None,
    apply_query_filters: bool = True,
) -> list[dict[str, Any]]:
    resolved_total_mode = resolve_total_mode(total_mode, query)
    filtered = records
    if resolved_total_mode != "include":
        filtered = [
            record for record in filtered
            if not is_total_label(record.get("x"))
            and not is_total_label(record.get("series"))
        ]

    target_year = target_year if target_year is not None else query_year(query)
    if target_year is not None:
        year_matches = [record for record in filtered if parse_year(record.get("x")) == target_year]
        if year_matches:
            filtered = year_matches

    query_key = normalize_key(query) if apply_query_filters else ""
    if query_key:
        for field in ("x", "series"):
            category_values = []
            for record in filtered:
                value = record.get(field)
                if value is not None and value not in category_values and parse_year(value) is None:
                    category_values.append(value)
            matched_values = {
                value for value in category_values
                if (key := normalize_key(value)) and len(key) >= 2 and key in query_key
            }
            if matched_values:
                filtered = [record for record in filtered if record.get(field) in matched_values]

    return filtered


# 행에서 x축 값을 꺼내 축 타입에 맞게 변환한다.
def row_x_value(row: dict[str, str], x_column: str | None, profile: dict[str, Any] | None) -> Any:
    if not x_column:
        return ""
    raw = row.get(x_column, "")
    if profile and profile["is_year"]:
        return parse_year(raw) or raw
    parsed = parse_number(raw) if profile and profile["is_numeric"] else None
    return parsed if parsed is not None else raw
