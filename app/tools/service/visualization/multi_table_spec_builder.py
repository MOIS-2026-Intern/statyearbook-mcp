# -*- coding: utf-8 -*-
"""서로 다른 통계표에서 고른 지표를 공통 기준 항목으로 맞춰 하나의 시각화 명세로 만든다."""
import re
from typing import Any, Literal

from .chart_spec_builder import (
    GAP_WORDS,
    RANK_WORDS,
    SAME_UNIT_SPLIT_RATIO,
    VALID_CHART_TYPES,
    apply_display_title,
    axis_title,
    mark_scatter_labels,
    limit_categories,
    metric_unit,
    ordered_categories,
    resolve_sort_order,
    stat_block,
    wants_relation_chart,
    wants_words,
)
from . import derived_metric
from .table_interpreter import (
    TotalMode,
    apply_exact_filters,
    body_to_rows,
    clean_label,
    display_category_label,
    is_total_label,
    normalize_key,
    parse_number,
    parse_year,
    pick_column_from_query,
    pick_focus_row,
    profile_by_name,
    profile_columns,
    resolve_column,
    resolve_total_mode,
    select_source_rows,
    year_value_columns,
)


MAX_SOURCES = 5
MAX_JOINED_ROWS = 60
# 두 계열의 크기 차이가 이보다 크면 한 축에 그렸을 때 작은 계열이 보이지 않는다.
DUAL_AXIS_SCALE_RATIO = 20
RATIO_WORDS = ("비율", "구성비", "증감률", "rate", "ratio", "percent", "%")
# 지역·연도 축에서 개별 항목과 나란히 두면 축을 압도하는 전체 집계 라벨이다.
AGGREGATE_KEY_WORDS = ("전국", "전체", "평균", "nationwide", "average")
REGION_SUFFIX_PATTERN = re.compile(r"(특별자치시|특별자치도|특별시|광역시|자치시|자치도)$")
REGION_SHORT_NAMES = frozenset({
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
})
# 같은 시도를 표마다 다르게 적는 정식 명칭을 짧은 이름으로 모은다.
REGION_FULL_NAMES = {
    "경기도": "경기",
    "강원도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주도": "제주",
}

# 표마다 표기가 달라도 같은 항목이 한 키로 모이도록 라벨을 정규화한다.
def canonical_key(value: Any, key_is_year: bool) -> str:
    label = display_category_label(value)
    if key_is_year:
        year = parse_year(label)
        if year is not None:
            return str(year)
    key = normalize_key(label)
    if key in REGION_FULL_NAMES:
        return REGION_FULL_NAMES[key]
    trimmed = REGION_SUFFIX_PATTERN.sub("", key)
    if trimmed in REGION_SHORT_NAMES:
        return trimmed
    return key


# 차트 축에 표시할 기준 항목 값을 만든다.
def _key_axis_value(value: Any, key_is_year: bool) -> Any:
    if key_is_year:
        year = parse_year(display_category_label(value))
        if year is not None:
            return year
    return display_category_label(value)


# 합계·전국처럼 개별 항목을 이미 포함한 행인지 판단한다.
def _is_aggregate_key(value: Any) -> bool:
    if is_total_label(value):
        return True
    key = normalize_key(display_category_label(value))
    return any(word in key for word in AGGREGATE_KEY_WORDS)


# 단위가 여러 개인 표에서는 컬럼 이름을 보고 그 계열의 단위만 남긴다.
def source_unit(column: str, table_unit: str | None) -> str:
    return derived_metric.column_unit(column, table_unit, metric_unit(column, table_unit))


# 비율 컬럼은 여러 행을 더하면 값이 망가지므로 따로 구분한다.
def _is_ratio_column(column: str) -> bool:
    lowered = column.lower()
    return any(word in lowered for word in RATIO_WORDS)


# 상위 헤더든 하위 헤더든 합계 자리인 컬럼인지 확인한다.
def _looks_total_column(column: str) -> bool:
    return any(is_total_label(part) for part in column.split("_"))


# 조인 기준으로 쓸 수 있는 컬럼 후보를 연도, 범주 순으로 모은다.
def _candidate_key_columns(profiles: list[dict[str, Any]]) -> list[str]:
    years = [profile["name"] for profile in profiles if profile["is_year"]]
    categories = [profile["name"] for profile in profiles if profile.get("is_categorical")]
    return years + categories


# 컬럼 하나가 만들어 내는 조인 키 집합을 구한다.
def _column_keys(rows: list[dict[str, str]], column: str, key_is_year: bool) -> set[str]:
    keys = set()
    for row in rows:
        raw = row.get(column, "")
        if not clean_label(raw) or _is_aggregate_key(raw):
            continue
        key = canonical_key(raw, key_is_year)
        if key:
            keys.add(key)
    return keys


# 요청 텍스트를 하나의 검색 문자열로 합친다.
def _hint_text(*values: str | None) -> str:
    return " ".join(value for value in values if value)


# 행이 범주, 열이 연도인 표에서 다른 표와 맞댈 기준 행 하나를 고른다.
def _wide_year_focus_row(
    rows: list[dict[str, str]],
    category_column: str,
    query: str | None,
) -> dict[str, str] | None:
    if len(rows) == 1:
        return rows[0]
    matched = pick_focus_row(rows, category_column, query, None, None, None)
    if matched is not None:
        return matched
    # 어느 행을 볼지 질의에 없으면 표 전체를 대표하는 합계 행으로 맞댄다.
    totals = [row for row in rows if is_total_label(row.get(category_column))]
    return totals[0] if len(totals) == 1 else None


# 열이 연도인 표를 연도-값 두 컬럼짜리 표로 편다. 다른 표에 연도 컬럼이 있어도 이 표에는
# 맞댈 연도 컬럼이 없어, 펴 두지 않으면 두 표를 이을 기준 자체가 생기지 않는다.
def _flatten_wide_year_table(
    columns: list[str],
    rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    query: str | None,
    label: str,
    warnings: list[str],
) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]] | None:
    if any(profile["is_year"] for profile in profiles):
        return None
    year_columns = year_value_columns(profiles)
    if len(year_columns) < 2:
        return None
    category_column = next(
        (profile["name"] for profile in profiles if profile.get("is_categorical")), None,
    )
    if category_column is None:
        return None

    focus = _wide_year_focus_row(rows, category_column, query)
    if focus is None:
        return None

    focus_label = display_category_label(focus.get(category_column)) or "값"
    flattened = [
        {"연도": str(year), focus_label: focus.get(column, "")}
        for year, column in year_columns
    ]
    if len(rows) > 1:
        warnings.append(
            f"[{label}] 열이 연도인 표라 '{focus_label}' 행을 연도별 값으로 펴서 맞췄습니다."
        )
    flat_columns = ["연도", focus_label]
    return flat_columns, flattened, profile_columns(flat_columns, flattened)


# 표 본문을 읽고 연도·필터 조건을 적용한 원본 행을 준비한다.
def _prepare_source(
    index: int,
    source: dict[str, Any],
    default_year: int | None,
    query: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    table = source["table"]
    request = dict(source.get("request") or {})
    label = clean_label(request.get("label")) or clean_label(table["title_ko"])
    columns, rows, table_warnings = body_to_rows(table["body"])
    warnings.extend(f"[{label}] {warning}" for warning in table_warnings)

    profiles = profile_columns(columns, rows)
    year = request.get("year") if request.get("year") is not None else default_year
    rows, selection, selection_warnings = select_source_rows(
        rows, profiles, year, request.get("city"), None,
    )
    warnings.extend(f"[{label}] {warning}" for warning in selection_warnings)

    filters = request.get("filters")
    applied_filters: list[dict[str, Any]] = []
    if filters:
        rows, applied_filters, filter_errors = apply_exact_filters(rows, profiles, filters)
        warnings.extend(f"[{label}] {error}" for error in filter_errors)

    # 행을 좁힌 뒤에 펴야, 사용자가 고른 행이 그대로 기준 행이 된다.
    flattened = _flatten_wide_year_table(columns, rows, profiles, query, label, warnings)
    if flattened is not None:
        columns, rows, profiles = flattened

    return {
        "index": index,
        "table": table,
        "request": request,
        "label": label,
        "columns": columns,
        "rows": rows,
        "profiles": profiles,
        "profile_map": profile_by_name(profiles),
        "selection": {**selection, "filters": applied_filters, "resolved_year": year},
    }


# 표마다 값이 가장 많이 겹치는 컬럼 조합을 찾아 조인 기준을 정한다.
def _choose_key_columns(
    prepared: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[list[str], bool] | None:
    candidate_lists: list[list[str]] = []
    for source in prepared:
        requested = source["request"].get("key")
        resolved = resolve_column(requested, source["profiles"]) if requested else None
        if requested and resolved is None:
            warnings.append(
                f"[{source['label']}] 요청한 기준 컬럼 '{requested}'을 표에서 찾지 못해 서버가 다시 골랐습니다."
            )
        candidate_lists.append([resolved] if resolved else _candidate_key_columns(source["profiles"]))

    best: tuple[int, list[str], bool] | None = None
    for first_column in candidate_lists[0]:
        first_is_year = prepared[0]["profile_map"][first_column]["is_year"]
        shared = _column_keys(prepared[0]["rows"], first_column, first_is_year)
        if not shared:
            continue

        chosen = [first_column]
        for source, candidates in zip(prepared[1:], candidate_lists[1:]):
            scored = [
                (len(shared & _column_keys(source["rows"], column, first_is_year)), -position, column)
                for position, column in enumerate(candidates)
            ]
            scored.sort(reverse=True)
            if not scored or scored[0][0] == 0:
                chosen = []
                break
            chosen.append(scored[0][2])
            shared &= _column_keys(source["rows"], scored[0][2], first_is_year)

        if not chosen:
            continue
        if best is None or len(shared) > best[0]:
            best = (len(shared), chosen, first_is_year)

    if best is None:
        return None
    return best[1], best[2]


# 표에서 계열 값으로 읽을 숫자 컬럼을 정한다.
def _pick_value_column(
    source: dict[str, Any],
    key_column: str,
    query: str | None,
    default_year: int | None,
    warnings: list[str],
) -> str | None:
    profiles = source["profiles"]
    profile_map = source["profile_map"]
    label = source["label"]

    requested = source["request"].get("value")
    if requested:
        column = resolve_column(requested, profiles)
        if column and profile_map[column]["is_numeric"]:
            return column
        warnings.append(
            f"[{label}] 요청한 값 컬럼 '{requested}'을 숫자 컬럼으로 확인하지 못해 서버가 다시 골랐습니다."
        )

    candidates = [
        profile["name"]
        for profile in profiles
        if profile["is_numeric"] and profile["name"] != key_column
    ]
    if not candidates:
        warnings.append(f"[{label}] 표에서 시각화할 숫자 컬럼을 찾지 못했습니다.")
        return None
    if len(candidates) == 1:
        return candidates[0]

    hint = pick_column_from_query(
        _hint_text(source["request"].get("label"), query), candidates,
    )
    if hint:
        return hint

    year_columns = [(year, column) for year, column in year_value_columns(profiles) if column in candidates]
    if year_columns:
        target_year = source["request"].get("year") or default_year
        matched = next((column for year, column in year_columns if year == target_year), None)
        chosen = matched or year_columns[-1][1]
    else:
        total_columns = [column for column in candidates if _looks_total_column(column)]
        chosen = total_columns[0] if total_columns else candidates[0]
    warnings.append(
        f"[{label}] 숫자 컬럼이 여러 개라 '{chosen}' 값을 사용했습니다. 다른 값이 필요하면 value로 컬럼명을 지정하세요."
    )
    return chosen


# 같은 기준 항목이 여러 행에 나뉘어 있으면 하나의 값으로 모은다.
def _aggregate_values(values: list[float], ratio_column: bool) -> float:
    if len(values) == 1:
        return values[0]
    return sum(values) / len(values) if ratio_column else sum(values)


# 한 표에서 기준 항목별 값을 뽑아 계열 하나를 만든다.
def _series_points(
    source: dict[str, Any],
    key_column: str,
    key_is_year: bool,
    value_column: str,
    include_totals: bool,
    warnings: list[str],
) -> dict[str, Any]:
    grouped: dict[str, list[float]] = {}
    axis_values: dict[str, Any] = {}
    for row in source["rows"]:
        raw = row.get(key_column, "")
        if not clean_label(raw):
            continue
        if not include_totals and _is_aggregate_key(raw):
            continue
        value = parse_number(row.get(value_column))
        if value is None:
            continue
        key = canonical_key(raw, key_is_year)
        if not key:
            continue
        grouped.setdefault(key, []).append(value)
        axis_values.setdefault(key, _key_axis_value(raw, key_is_year))

    ratio_column = _is_ratio_column(value_column)
    merged = {key: _aggregate_values(values, ratio_column) for key, values in grouped.items()}
    if any(len(values) > 1 for values in grouped.values()):
        how = "평균" if ratio_column else "합계"
        warnings.append(
            f"[{source['label']}] 한 항목이 여러 행에 나뉘어 있어 {how}로 집계했습니다."
        )
    return {"values": merged, "axis_values": axis_values, "order": list(merged)}


# 계열 이름이 겹치면 값 컬럼으로 구분한다.
def _unique_labels(series: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for item in series:
        seen[item["label"]] = seen.get(item["label"], 0) + 1
    used: dict[str, int] = {}
    for item in series:
        if seen[item["label"]] == 1:
            continue
        used[item["label"]] = used.get(item["label"], 0) + 1
        suffix = display_category_label(item["value_column"].split("_")[-1]) or str(used[item["label"]])
        item["label"] = f"{item['label']} ({suffix})"


# 표별 계열을 파생 계산이 읽는 피연산자로 옮긴다. 계열 값은 _series_points가 항목별 집계를
# 이미 끝낸 값이라, 여기서 나누면 합계끼리 나눈 값이 된다.
def _derive_series(
    series: list[dict[str, Any]],
    derive: dict[str, Any],
    query: str | None,
    warnings: list[str],
) -> dict[str, Any] | None:
    operands = [
        derived_metric.Operand(
            label=item["label"],
            unit=item["unit"],
            values=item["points"]["values"],
            axis_labels=item["points"]["axis_values"],
            base_date=item["source"]["table"].get("base_date"),
            order=item["points"]["order"],
        )
        for item in series
    ]
    result = derived_metric.build(derive, operands, query, warnings)
    if result is None:
        return None

    numerator = series[result.numerator_index]
    denominator = series[result.denominator_index]
    return {
        "source": numerator["source"],
        "label": result.label,
        "key_column": numerator["key_column"],
        "value_column": numerator["value_column"],
        "unit": result.unit,
        "points": {
            "values": result.values,
            "axis_values": result.axis_labels,
            "order": result.order,
        },
        "derived": {
            **result.detail,
            # 어느 표의 어느 컬럼을 썼는지는 표를 아는 이 경로에서만 채울 수 있다.
            "numerator": {
                **result.detail["numerator"],
                "stat_id": numerator["source"]["table"]["stat_id"],
                "column": numerator["value_column"],
            },
            "denominator": {
                **result.detail["denominator"],
                "stat_id": denominator["source"]["table"]["stat_id"],
                "column": denominator["value_column"],
            },
        },
    }


# 계열들이 같은 단위를 쓰는지 확인한다.
def _same_unit(series: list[dict[str, Any]]) -> bool:
    units = {clean_label(item.get("unit")) for item in series}
    return len(units) == 1 and bool(next(iter(units)))


# 요청과 계열 구조를 바탕으로 여러 표를 함께 그릴 차트 타입을 결정한다.
def _select_multi_chart(
    requested: str,
    query: str | None,
    key_is_year: bool,
    series: list[dict[str, Any]],
    axis_labels: list[Any],
    warnings: list[str],
    derived: bool = False,
) -> tuple[str, str, str]:
    requested_type = requested if requested in VALID_CHART_TYPES else "auto"
    if requested_type != requested:
        warnings.append(f"지원하지 않는 차트 타입 '{requested}' 대신 auto를 사용했습니다.")
    series_count = len(series)

    if requested_type == "scatter" or (
        requested_type == "auto" and series_count == 2 and not key_is_year and wants_relation_chart(query)
    ):
        if series_count == 2:
            return (
                "scatter",
                "server_multi_source" if requested_type == "auto" else "client_spec_validated",
                "두 표의 지표를 항목별로 짝지어 관계를 보는 산점도로 구성했습니다.",
            )
        warnings.append("산점도는 두 개의 지표가 필요해 다른 차트로 대체했습니다.")
        requested_type = "auto"

    if requested_type == "donut":
        warnings.append("도넛형은 한 표의 구성비에 적합해 여러 표 비교에는 사용하지 않았습니다.")
        requested_type = "auto"
    if requested_type in {"line", "area", "slope", "bump"} and not key_is_year and not ordered_categories(axis_labels):
        warnings.append(
            "선을 잇는 차트는 시간처럼 순서가 있는 축에서 추이를 보여줄 때 적합해 막대그래프로 바꿨습니다."
        )
        requested_type = "auto"
    if requested_type == "dumbbell" and (series_count != 2 or not _same_unit(series)):
        warnings.append("아령 차트는 단위가 같은 지표 두 개가 필요해 다른 차트로 대체했습니다.")
        requested_type = "auto"

    if requested_type == "auto":
        if derived:
            # 파생 지표는 계열이 하나뿐이라 표별 비교가 아니라 항목별 크기 비교가 된다.
            if key_is_year:
                return "line", "server_derived_metric", "표끼리 계산한 값을 연도 축에 이어 추이를 보여 줍니다."
            return "bar", "server_derived_metric", "표끼리 계산한 값을 항목마다 견주는 막대그래프를 선택했습니다."
        if key_is_year and _same_unit(series) and wants_words(query, RANK_WORDS):
            return "bump", "server_multi_source", "순위 변화를 묻는 요청이라 시점마다 순위를 매겨 잇는 그래프를 선택했습니다."
        if key_is_year:
            return "line", "server_multi_source", "연도를 공통 축으로 맞춰 표별 추이를 선그래프로 겹쳤습니다."
        if series_count == 2 and _same_unit(series) and wants_words(query, GAP_WORDS):
            return "dumbbell", "server_multi_source", "두 지표의 격차를 묻는 요청이라 항목마다 두 값을 이어 벌어진 폭을 보여주는 아령 차트를 선택했습니다."
        if series_count > 1:
            return "grouped_bar", "server_multi_source", "같은 기준 항목을 두고 지표별 막대를 나란히 놓아 크기를 바로 견주게 했습니다."
        return "bar", "server_multi_source", "공통 항목을 축으로 표별 값을 비교하는 막대그래프를 선택했습니다."

    if requested_type == "bar" and series_count > 1:
        return "grouped_bar", "server_fallback", "표가 둘 이상이라 그룹 막대그래프로 보정했습니다."
    return requested_type, "client_spec_validated", "클라이언트가 지정한 차트 타입을 여러 표 구조에서 검증해 사용했습니다."


# 두 계열의 최댓값이 몇 배나 벌어져 있는지 잰다.
def _scale_ratio(series: list[dict[str, Any]]) -> float:
    scales = []
    for item in series:
        values = [abs(value) for value in item["points"]["values"].values() if value]
        scales.append(max(values) if values else 0.0)
    if len(scales) != 2 or min(scales) <= 0:
        return 1.0
    return max(scales) / min(scales)


# 단위가 다른 두 계열은 축을 나눠야 작은 계열이 보인다.
# 단위가 같으면 규모가 벌어져도 한 축에 두는 편이 옳다. 축을 나누면 눈금이 달라져
# 막대 높이를 그대로 견주는 읽기가 어긋나기 때문이다. 다만 규모가 백 배를 넘으면
# 작은 쪽 막대가 몇 픽셀도 되지 않아 아예 보이지 않으므로 그때는 나눈다.
def _needs_dual_axis(chart_type: str, series: list[dict[str, Any]]) -> bool:
    if chart_type not in {"bar", "grouped_bar", "line", "area", "combo"} or len(series) != 2:
        return False
    units = [clean_label(item.get("unit")) for item in series]
    if all(units):
        if units[0] != units[1]:
            return True
        return _scale_ratio(series) >= SAME_UNIT_SPLIT_RATIO
    # 단위를 알 수 없을 때만 값의 규모 차이로 판단한다.
    return _scale_ratio(series) >= DUAL_AXIS_SCALE_RATIO


# 계열 값을 표 형태로 정리해 답변에 인용할 수 있게 한다.
def _joined_rows(
    keys: list[str],
    labels: dict[str, Any],
    series: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for key in keys[:MAX_JOINED_ROWS]:
        row: dict[str, Any] = {"항목": labels.get(key, key)}
        for item in series:
            row[item["label"]] = item["points"]["values"].get(key)
        rows.append(row)
    return rows


# 어떤 항목으로 표를 맞추려 했는지 보여줄 기준 항목 예시를 만든다.
def _key_samples(source: dict[str, Any]) -> str:
    candidates = _candidate_key_columns(source["profiles"])
    if not candidates:
        return f"{source['label']}: 기준 항목 컬럼 없음"
    column = candidates[0]
    values = [display_category_label(row.get(column, "")) for row in source["rows"][:3]]
    return f"{source['label']}: " + ", ".join(value for value in values if value)


# 표를 하나도 대조하지 못했을 때 이유를 담은 응답을 만든다.
def _empty_response(
    prepared: list[dict[str, Any]],
    request: dict[str, Any],
    reason: str,
    warnings: list[str],
) -> dict[str, Any]:
    chart = {
        "type": "table",
        "requested_type": request.get("chart_type"),
        "decision_source": "server_validation",
        "reason": reason,
        "title": " · ".join(source["label"] for source in prepared),
        "x": None,
        "y": None,
        "group": None,
        "unit": None,
        "sort_order": None,
    }
    return {
        "ok": True,
        "version": "0.1",
        "library": "vega-lite",
        "renderer": "client",
        "stat": stat_block(prepared[0]["table"]),
        "stats": [stat_block(source["table"]) for source in prepared],
        "sources": [
            {
                "label": source["label"],
                "stat_id": source["table"]["stat_id"],
                "ref_id": source["table"]["ref_id"],
                "title_ko": source["table"]["title_ko"],
                "selected_row_count": len(source["rows"]),
            }
            for source in prepared
        ],
        "request": request,
        "chart": chart,
        "data": {"records": [], "record_count": 0, "joined_rows": []},
        "warnings": warnings,
    }


# 여러 표의 지표를 공통 항목으로 맞춰 하나의 차트 spec을 만든다.
def build_multi_source_spec(
    sources: list[dict[str, Any]],
    *,
    query: str | None = None,
    chart_type: str = "auto",
    top_n: int | None = None,
    total_mode: TotalMode = "auto",
    year: int | None = None,
    title: str | None = None,
    orientation: Literal["vertical", "horizontal"] = "vertical",
    sort_order: str = "auto",
    derive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    resolved_sort_order = resolve_sort_order(sort_order, query, warnings)
    prepared = [
        _prepare_source(index, source, year, query, warnings)
        for index, source in enumerate(sources)
    ]
    request: dict[str, Any] = {
        "query": query,
        "chart_type": chart_type,
        "top_n": top_n,
        "total_mode": total_mode,
        "year": year,
        "orientation": orientation,
        "sort_order": sort_order,
        "resolved_sort_order": resolved_sort_order,
        "derive": derive,
        "sources": [
            {
                key: value
                for key, value in source["request"].items()
                if key in {"stat_id", "table_handle", "label", "key", "value", "unit", "year", "filters"}
            }
            for source in prepared
        ],
    }

    chosen = _choose_key_columns(prepared, warnings)
    if chosen is None:
        samples = " ; ".join(_key_samples(source) for source in prepared)
        return _empty_response(
            prepared,
            request,
            "표끼리 맞출 공통 항목(지역·연도 등)을 찾지 못해 함께 그리지 않았습니다. "
            f"각 표의 기준 항목 예시는 다음과 같습니다. {samples}",
            warnings,
        )

    key_columns, key_is_year = chosen
    include_totals = resolve_total_mode(total_mode, query) == "include"
    series: list[dict[str, Any]] = []
    for source, key_column in zip(prepared, key_columns):
        value_column = _pick_value_column(source, key_column, query, year, warnings)
        if value_column is None:
            continue
        points = _series_points(
            source, key_column, key_is_year, value_column, include_totals, warnings,
        )
        if not points["values"]:
            warnings.append(f"[{source['label']}] 선택한 조건에서 읽을 수 있는 숫자 값이 없습니다.")
            continue
        series.append({
            "source": source,
            "label": source["label"],
            "key_column": key_column,
            "value_column": value_column,
            "unit": clean_label(source["request"].get("unit"))
            or source_unit(value_column, source["table"].get("unit")),
            "points": points,
        })

    if len(series) < 2:
        return _empty_response(
            prepared,
            request,
            "표에서 함께 그릴 숫자 지표를 두 개 이상 확인하지 못했습니다.",
            warnings,
        )
    _unique_labels(series)

    # 파생 지표는 계열 두 개를 소비해 하나를 만든다. 표별 계열이 다 갖춰진 뒤에 계산해야
    # 분자와 분모가 같은 기준 항목으로 이미 맞춰진 값이 된다.
    source_series = series
    derived = _derive_series(series, derive, query, warnings) if derive else None
    if derived is not None:
        if len(series) > 2:
            warnings.append("파생 지표는 분자와 분모 두 표만 쓰므로 나머지 표는 그리지 않았습니다.")
        series = [derived]
        if resolved_sort_order is None and not key_is_year and wants_words(query, RANK_WORDS):
            # 순위를 묻는 요청에 값 순서를 두지 않으면 표에 실린 순서 그대로 나와 순위가 드러나지 않는다.
            resolved_sort_order = "descending"
            request["resolved_sort_order"] = resolved_sort_order

    all_labels = list(dict.fromkeys(
        label for item in series for label in item["points"]["axis_values"].values()
    ))
    selected_type, decision_source, reason = _select_multi_chart(
        chart_type, query, key_is_year, series, all_labels, warnings, derived is not None,
    )
    shared_keys = set(series[0]["points"]["values"])
    for item in series[1:]:
        shared_keys &= set(item["points"]["values"])
    if not shared_keys:
        return _empty_response(
            prepared,
            request,
            "표끼리 공통으로 값을 가진 항목이 없어 함께 그리지 않았습니다.",
            warnings,
        )

    ordered_keys: list[str] = []
    for item in series:
        for key in item["points"]["order"]:
            if key not in ordered_keys and (selected_type != "scatter" or key in shared_keys):
                ordered_keys.append(key)
    if key_is_year:
        # 연도 축이어도 다른 표가 연도가 아닌 라벨을 섞어 넣을 수 있어 숫자만 연도로 정렬한다.
        ordered_keys.sort(key=lambda key: (not key.isdigit(), int(key) if key.isdigit() else key))
    axis_labels: dict[str, Any] = {}
    for item in series:
        for key, label in item["points"]["axis_values"].items():
            axis_labels.setdefault(key, label)

    missing = [key for key in ordered_keys if key not in shared_keys]
    if missing:
        shown = ", ".join(str(axis_labels.get(key, key)) for key in missing[:5])
        more = f" 외 {len(missing) - 5}개" if len(missing) > 5 else ""
        warnings.append(f"일부 표에만 있는 항목({shown}{more})은 해당 계열에서 비워 두었습니다.")

    if selected_type == "scatter":
        records = [
            {
                "x": series[0]["points"]["values"][key],
                "value": series[1]["points"]["values"][key],
                "series": None,
                "label": axis_labels.get(key, key),
            }
            for key in ordered_keys
        ]
        mark_scatter_labels(records)
    else:
        # 값 기준 정렬은 첫 계열의 값으로 정한다. 단위가 다른 계열을 더한 순서는 뜻이 없다.
        if resolved_sort_order and not key_is_year:
            leading = series[0]["points"]["values"]
            descending = resolved_sort_order == "descending"
            # 첫 계열에 값이 없는 항목은 방향과 상관없이 뒤로 보낸다.
            ordered_keys.sort(
                key=lambda key: (
                    key not in leading,
                    -leading.get(key, 0.0) if descending else leading.get(key, 0.0),
                )
            )
        records = [
            # 파생 지표는 계열이 하나뿐이라 계열명을 두면 항목이 하나인 범례만 늘어난다.
            {
                "x": axis_labels.get(key, key),
                "value": value,
                "series": None if derived is not None else item["label"],
            }
            for key in ordered_keys
            for item in series
            if (value := item["points"]["values"].get(key)) is not None
        ]
        records = limit_categories(records, selected_type, key_is_year, top_n, warnings)

    units = {item["unit"] for item in series}
    same_unit = _same_unit(series)
    scale_ratio = _scale_ratio(series)
    dual_axis = selected_type != "scatter" and _needs_dual_axis(selected_type, series)
    if dual_axis:
        # 값 축을 나누면 막대를 나란히 둘 수 없다. 계열마다 mark를 달리하는 콤보 차트로 바꾼다.
        selected_type = "combo"
    if dual_axis and same_unit:
        # 같은 단위인데 규모가 이만큼 벌어지는 것은 표의 단위 표기가 서로 어긋났다는 뜻일 때가 많다.
        warnings.append(
            f"단위가 같은데도 두 지표의 규모가 약 {scale_ratio:,.0f}배 차이나, 한 축에 두면 작은 쪽이 "
            "보이지 않아 값 축을 좌우로 나눴습니다. 두 축의 눈금이 서로 다르므로 막대 높이를 그대로 "
            "견주면 안 되며, 표에 적힌 단위가 실제 수치와 맞는지 확인이 필요합니다."
        )
    elif same_unit and scale_ratio >= DUAL_AXIS_SCALE_RATIO:
        warnings.append(
            "두 지표의 규모 차이가 커서 작은 쪽 막대가 낮게 보입니다. 단위가 같아 축은 하나로 두었으니, "
            "작은 쪽을 자세히 보려면 그 표만 따로 그려 주세요."
        )
    chart: dict[str, Any] = {
        "type": selected_type,
        "requested_type": chart_type,
        "decision_source": decision_source,
        "reason": reason,
        "title": " · ".join(item["label"] for item in series),
        "x": "year" if key_is_year else "category",
        "y": "value",
        "group": None if selected_type == "scatter" or derived is not None else "series",
        "unit": next(iter(units)) if len(units) == 1 else None,
        "orientation": orientation,
        "sort_order": resolved_sort_order,
        "series": [{"label": item["label"], "unit": item["unit"]} for item in series],
        "dual_axis": dual_axis,
        # 축 순서는 서버가 정한다. 두지 않으면 Vega-Lite가 가나다순으로 다시 늘어놓아
        # 표에 실린 지역 순서도, 값 기준 정렬도 사라진다.
        "category_order": (
            None
            if key_is_year or selected_type == "scatter"
            else list(dict.fromkeys(record["x"] for record in records))
        ),
    }
    if selected_type == "scatter":
        chart["point_label"] = True
        chart["x_title"] = axis_title(series[0])
        chart["y_title"] = axis_title(series[1])
    elif dual_axis:
        chart["y_title"] = axis_title(series[0])
        # 값 축을 나누면 mark도 바뀌므로 원래 이유를 덧붙이지 않고 다시 쓴다.
        axis_label = "연도" if key_is_year else "표끼리 공통인 항목"
        cause = "규모가 크게 달라" if same_unit else "단위가 달라"
        chart["reason"] = (
            f"{axis_label}을 축으로 맞추되, 두 계열의 {cause} 한 축에 나란히 두면 작은 쪽이 "
            "보이지 않으므로 값 축을 좌우로 나누고 첫 계열은 막대, 나머지는 선으로 겹쳤습니다."
        )

    spec = {
        "ok": True,
        "version": "0.1",
        "library": "vega-lite",
        "renderer": "client",
        "stat": stat_block(source_series[0]["source"]["table"]),
        # 실제로 그린 표만 남겨 답변의 출처 줄이 쓰지 않은 표를 인용하지 않게 한다.
        # 파생 지표는 계열이 하나로 줄어도 분자·분모 두 표가 모두 근거이므로 계산 전 계열을 쓴다.
        "stats": list({
            item["source"]["table"]["stat_id"]: stat_block(item["source"]["table"])
            for item in source_series
        }.values()),
        "sources": [
            {
                "label": item["label"],
                "stat_id": item["source"]["table"]["stat_id"],
                "ref_id": item["source"]["table"]["ref_id"],
                "title_ko": item["source"]["table"]["title_ko"],
                "base_date": item["source"]["table"]["base_date"],
                "key_column": item["key_column"],
                "value_column": item["value_column"],
                "unit": item["unit"],
                "point_count": len(item["points"]["values"]),
                "selection": item["source"]["selection"],
            }
            for item in source_series
        ],
        "request": request,
        "chart": chart,
        "transform": {
            "type": "multi_source_derive" if derived is not None else "multi_source_join",
            "key_is_year": key_is_year,
            "key_columns": [
                {"label": item["label"], "column": item["key_column"]} for item in source_series
            ],
            "matched_key_count": len(shared_keys),
            "join": "inner" if selected_type == "scatter" else "outer",
            "derived": derived["derived"] if derived is not None else None,
        },
        "data": {
            "records": records,
            "record_count": len(records),
            # 파생 지표는 분자·분모와 계산 결과를 한 줄에 두어야 답변이 계산 근거를 인용할 수 있다.
            "joined_rows": _joined_rows(
                ordered_keys,
                axis_labels,
                [*source_series, derived] if derived is not None else series,
            ),
        },
        "warnings": warnings,
    }
    return apply_display_title(spec, title)
