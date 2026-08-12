"""통계표 해석 결과로 시각화 명세를 구성한다."""
import re
from typing import Any, Literal

from .table_interpreter import (
    TotalMode,
    apply_exact_filters,
    body_to_rows,
    column_family,
    column_family_groups,
    display_category_label,
    family_category_label,
    filter_chart_records,
    is_total_column,
    is_total_label,
    normalize_key,
    parse_number,
    parse_year,
    pick_column_from_query,
    pick_focus_row,
    pick_x_column,
    profile_by_name,
    profile_columns,
    requested_year,
    resolve_column,
    resolve_total_mode,
    row_x_value,
    select_source_rows,
    wants_delta_chart,
    wants_trend_chart,
    year_value_columns,
)


ChartType = Literal[
    "auto",
    "bar",
    "grouped_bar",
    "stacked_bar",
    "stacked_bar_100",
    "lollipop",
    "diverging_bar",
    "waterfall",
    "line",
    "area",
    "slope",
    "bump",
    "combo",
    "scatter",
    "dumbbell",
    "heatmap",
    "donut",
    "table",
]
SortOrder = Literal["auto", "ascending", "descending"]

VALID_CHART_TYPES = set(ChartType.__args__)
# 시간 축을 따라 읽는 차트는 값이 아니라 시점 순서로 늘어놓아야 한다.
TIME_ORDERED_TYPES = {"line", "area", "scatter", "slope", "bump"}
# 값 기준 정렬을 적용할 수 있는 범주형 차트다. 폭포 차트는 순서 자체가 뜻을 가져 제외한다.
VALUE_SORTED_TYPES = {
    "bar",
    "grouped_bar",
    "stacked_bar",
    "stacked_bar_100",
    "lollipop",
    "diverging_bar",
    "dumbbell",
    "combo",
    "donut",
}
# 부분이 모여 전체를 이루는 차트는 합계 범주를 함께 그리면 두 번 세게 된다.
PART_OF_WHOLE_TYPES = {"donut", "stacked_bar_100", "waterfall"}
# 값의 수준이 아니라 값이 얼마나 움직였는지를 그리는 차트다.
CHANGE_CHART_TYPES = {"diverging_bar", "waterfall"}
SHARE_WORDS = ("비중", "구성", "구성비", "점유", "점유율", "분포", "share", "ratio", "composition")
RANK_WORDS = ("순위", "랭킹", "등수", "rank")
GAP_WORDS = ("격차", "차이", "간극", "gap", "difference")
MAX_SERIES = 12
_MISSING = object()
CATEGORY_ALIASES = {"category", "classification", "label", "name", "구분", "분류"}
VALUE_ALIASES = {"value", "count", "measure", "값", "수", "정원", "인원"}


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
def limit_categories(
    records: list[dict[str, Any]],
    chart_type: str,
    x_is_year: bool,
    top_n: int | None,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if x_is_year or chart_type in TIME_ORDERED_TYPES or chart_type == "table":
        return records
    if top_n is not None and top_n <= 0:
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

    if chart_type == "waterfall":
        # 폭포 차트는 앞 단계의 누적 위에 다음 단계를 쌓으므로 중간을 빼면 값이 어긋난다.
        keep = set(categories[:limit])
    else:
        totals: dict[Any, float] = {}
        for record in records:
            totals[record["x"]] = totals.get(record["x"], 0.0) + abs(float(record["value"]))
        keep = {
            name for name, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
        }
    warnings.append(
        f"범주가 {len(categories)}개라 상위 {limit}개 범주만 표시했습니다. 전체를 보려면 top_n=0으로 요청하세요."
    )
    return [record for record in records if record["x"] in keep]


# 질의에 해당 의도를 나타내는 말이 들어 있는지 본다.
def wants_words(query: str | None, words: tuple[str, ...]) -> bool:
    text = (query or "").lower()
    return any(word in text for word in words)


# 요청이 비중/구성비 차트를 의도하는지 판단한다.
def _wants_share_chart(query: str | None) -> bool:
    return wants_words(query, SHARE_WORDS)


# 축 라벨이 순서를 갖는지 본다. 숫자가 들어간 라벨(연도·연령대·금액 구간)은 이어 그려도 뜻이 통하지만,
# 지역명처럼 순서가 없는 라벨을 선으로 이으면 없는 추세가 보인다.
def ordered_categories(categories: list[Any]) -> bool:
    labels = [str(category) for category in categories if category is not None]
    return bool(labels) and all(any(char.isdigit() for char in label) for label in labels)


# 차트 선택에 필요한 레코드 구조를 뽑는다.
def _record_shape(records: list[dict[str, Any]]) -> tuple[list[Any], list[Any], bool]:
    categories = list(dict.fromkeys(record.get("x") for record in records))
    series = list(dict.fromkeys(
        record.get("series") for record in records if record.get("series") is not None
    ))
    has_negative = any(float(record.get("value") or 0) < 0 for record in records)
    return categories, series, has_negative


# 차트 타입을 지정하지 않은 요청에서 데이터 구조와 질의 의도로 가장 잘 맞는 차트를 고른다.
def _auto_chart(
    query: str | None,
    x_is_year: bool,
    has_group: bool,
    categories: list[Any],
    series: list[Any],
    has_negative: bool,
) -> tuple[str, str, str]:
    if _wants_share_chart(query) and has_group:
        return "stacked_bar_100", "server_auto", "질의가 구성비를 요구하고 계열이 있어 항목마다 100%로 맞춘 누적 막대그래프를 선택했습니다."
    if _wants_share_chart(query) and not x_is_year:
        return "donut", "server_auto", "질의가 구성비/비중을 요구하고 단일 범주-값 구조라 도넛형을 선택했습니다."
    if x_is_year and has_group and wants_words(query, RANK_WORDS):
        return "bump", "server_auto", "질의가 순위 변화를 요구해 시점마다 순위를 매겨 잇는 그래프를 선택했습니다."
    if x_is_year and has_group and len(categories) == 2:
        return "slope", "server_auto", "비교할 시점이 둘뿐이라 항목별 변화 방향이 드러나는 기울기 그래프를 선택했습니다."
    if x_is_year:
        return "line", "server_auto", "연도 축이 있는 숫자 데이터라 추이 확인에 적합한 선그래프를 선택했습니다."
    if len(series) == 2 and wants_words(query, GAP_WORDS):
        return "dumbbell", "server_auto", "두 계열의 격차를 묻는 질의라 항목마다 두 값을 이어 벌어진 폭을 보여주는 아령 차트를 선택했습니다."
    if has_negative and not has_group:
        return "diverging_bar", "server_auto", "값에 음수가 섞여 있어 0을 기준으로 증감을 가르는 막대그래프를 선택했습니다."
    if has_group:
        return "grouped_bar", "server_auto", "범주와 계열을 함께 비교하기 위해 그룹 막대그래프를 선택했습니다."
    return "bar", "server_auto", "범주별 숫자 비교에 적합한 막대그래프를 선택했습니다."


# 클라이언트가 지정한 차트가 데이터 구조에 맞지 않으면 가장 가까운 차트로 바꾼다.
def _correct_chart(
    requested_type: str,
    x_is_year: bool,
    x_is_numeric: bool,
    has_group: bool,
    categories: list[Any],
    series: list[Any],
    has_negative: bool,
) -> tuple[str, str] | None:
    grouped = "grouped_bar" if has_group else "bar"
    if requested_type == "donut" and (x_is_year or has_group):
        return ("line" if x_is_year else "grouped_bar"), "도넛형은 단일 시점의 구성비에 적합해 요청 차트를 대체했습니다."
    if requested_type == "scatter" and not x_is_numeric:
        return ("line" if x_is_year else "bar"), "산점도에는 숫자형 x축이 필요해 요청 차트를 대체했습니다."
    if requested_type == "heatmap" and not has_group:
        return "bar", "히트맵에는 두 개의 범주 축이 필요해 막대그래프로 대체했습니다."
    if requested_type in {"stacked_bar", "stacked_bar_100", "dumbbell", "bump", "slope", "combo"} and not has_group:
        return ("line" if x_is_year else "bar"), "요청한 차트는 계열이 둘 이상 필요해 단일 계열 차트로 대체했습니다."
    if requested_type == "dumbbell" and len(series) != 2:
        return "grouped_bar", "아령 차트는 계열이 정확히 두 개여야 해 그룹 막대그래프로 대체했습니다."
    if requested_type in {"bump", "slope"} and not x_is_year:
        return grouped, "순위·기울기 그래프에는 시점 축이 필요해 요청 차트를 대체했습니다."
    if requested_type == "slope" and len(categories) != 2:
        return "line", "기울기 그래프는 두 시점을 견줄 때 쓰므로 선그래프로 대체했습니다."
    if requested_type == "waterfall" and has_group:
        return "stacked_bar", "폭포 차트는 한 계열의 증감을 쌓아 보여주므로 누적 막대그래프로 대체했습니다."
    if requested_type == "lollipop" and has_group:
        return "grouped_bar", "롤리팝 차트는 계열이 하나일 때 쓰므로 그룹 막대그래프로 대체했습니다."
    if requested_type in {"line", "area"} and not x_is_year and not ordered_categories(categories):
        return grouped, "선·영역그래프는 순서가 있는 축의 추이를 보여줄 때 적합해 막대그래프로 대체했습니다."
    if requested_type == "bar" and has_group:
        return "grouped_bar", "계열 컬럼이 있어 그룹 막대그래프로 보정했습니다."
    if requested_type == "bar" and has_negative:
        return "diverging_bar", "값에 음수가 섞여 있어 0 기준선이 있는 증감 막대그래프로 보정했습니다."
    return None


# 단위가 둘로 갈리는 계열은 한 축에 그리면 작은 쪽이 축 바닥에 눌려 보이지 않는다.
# 값 축을 좌우로 나눌 수 있는 것은 두 종류까지라, 단위가 셋 이상이면 나누지 못한다.
def needs_axis_split(series: list[dict[str, Any]]) -> bool:
    units = [str(item.get("unit") or "").strip() for item in series]
    return len(series) >= 2 and all(units) and len(set(units)) == 2


# 단위가 갈리는 계열은 계열마다 mark를 달리하는 콤보로 바꿔 값 축을 좌우로 나눈다.
def apply_axis_split(chart_type: str, series: list[dict[str, Any]]) -> tuple[str, bool]:
    if chart_type not in {"bar", "grouped_bar", "line", "area", "combo"}:
        return chart_type, False
    if not needs_axis_split(series):
        return chart_type, False
    return "combo", True


# 표 메타데이터와 선택 범주로 차트 제목을 만든다.
def _chart_title(table: dict, subtitle: str | None = None) -> str:
    title = table["title_ko"]
    if subtitle:
        title = f"{subtitle} {title}"
    if table["table_seq"] and table["table_seq"] != 1:
        title = f"{title} ({table['table_seq']})"
    return title


# LLM이 정한 표시 제목이 있으면 서버 자동 제목 대신 사용한다.
def apply_display_title(spec: dict[str, Any], title: str | None) -> dict[str, Any]:
    display_title = " ".join((title or "").split())
    if not display_title:
        return spec
    spec["chart"]["title"] = display_title
    spec["request"]["title"] = display_title
    return spec


# 요청 힌트와 '_' 상위 헤더를 비교해 wide 표에서 사용할 컬럼군을 고른다.
def _pick_column_family(
    table: dict,
    profiles: list[dict[str, Any]],
    query: str | None,
    x: str | None,
    y: str | None,
    requested_family: str | None,
    warnings: list[str],
) -> tuple[str | None, list[str]]:
    groups = column_family_groups(profiles)
    if requested_family:
        columns = column_family(requested_family, profiles)
        if columns:
            prefix = next(prefix for prefix, values in groups.items() if values == columns)
            return prefix, columns
        warnings.append(f"표에서 요청한 컬럼군 '{requested_family}'을 찾지 못했습니다.")
        return None, []

    for hint in (x, y):
        columns = column_family(hint, profiles)
        if columns:
            prefix = next(prefix for prefix, values in groups.items() if values == columns)
            return prefix, columns

    semantic_request = normalize_key(x) in CATEGORY_ALIASES and (
        not y or normalize_key(y) in VALUE_ALIASES or resolve_column(y, profiles) is None
    )
    if not semantic_request or not groups:
        return None, []
    if len(groups) == 1:
        return next(iter(groups.items()))

    context = normalize_key(" ".join(
        value for value in (query, table.get("title_ko"), table.get("caption")) if value
    ))
    scored: list[tuple[int, int, str, list[str]]] = []
    for prefix, columns in groups.items():
        compact_prefix = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", prefix)
        tokens = [token for token in re.findall(r"[가-힣A-Za-z0-9]+", compact_prefix) if len(token) >= 2]
        score = sum(len(token) for token in tokens if token.lower() in context)
        scored.append((score, len(columns), prefix, columns))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    if len(scored) > 1 and scored[0][:2] == scored[1][:2]:
        warnings.append("여러 컬럼군의 우선순위가 같아 column_family를 명시해야 합니다.")
        return None, []
    return scored[0][2], scored[0][3]


# 요청과 데이터 구조를 바탕으로 최종 차트 타입을 결정한다.
def _select_chart(
    requested: str,
    query: str | None,
    records: list[dict[str, Any]],
    x_profile: dict[str, Any] | None,
    has_group: bool,
    warnings: list[str],
) -> tuple[str, str, str]:
    requested_type = requested if requested in VALID_CHART_TYPES else "auto"
    if requested_type != requested:
        warnings.append(f"지원하지 않는 차트 타입 '{requested}' 대신 auto를 사용했습니다.")

    x_is_year = bool(x_profile and x_profile["is_year"])
    x_is_numeric = bool(x_profile and x_profile["is_numeric"])

    if not records:
        return "table", "server_fallback", "시각화 가능한 숫자 데이터가 없어 차트를 생성하지 않았습니다."

    categories, series, has_negative = _record_shape(records)
    if requested_type == "auto":
        return _auto_chart(query, x_is_year, has_group, categories, series, has_negative)

    corrected = _correct_chart(
        requested_type, x_is_year, x_is_numeric, has_group, categories, series, has_negative,
    )
    if corrected is not None:
        return corrected[0], "server_fallback", corrected[1]
    return requested_type, "client_spec_validated", "클라이언트가 지정한 차트 타입을 데이터 구조 검증 후 사용했습니다."


# 부분-전체 차트는 합계 조각을 넣으면 중복 집계되므로 total_mode와 무관하게 제외한다.
def _drop_total_slices(records: list[dict[str, Any]], chart_type: str) -> list[dict[str, Any]]:
    if chart_type not in PART_OF_WHOLE_TYPES:
        return records
    return [
        record for record in records
        if not is_total_label(record.get("x")) and not is_total_label(record.get("series"))
    ]


# 사용자가 질의에 값 기준 정렬 방향을 직접 적은 경우 도구 인자 누락을 보완한다.
def resolve_sort_order(
    sort_order: str,
    query: str | None,
    warnings: list[str],
) -> Literal["ascending", "descending"] | None:
    if sort_order in {"ascending", "descending"}:
        return sort_order
    if sort_order != "auto":
        warnings.append(f"지원하지 않는 정렬 방향 '{sort_order}'은 적용하지 않았습니다.")
        return None

    text = re.sub(r"\s+", "", (query or "").lower())
    descending_patterns = (
        r"내림차순",
        r"(?:큰|높은|많은)(?:값|수|숫자|규모)?(?:부터|순(?:서)?(?:대로)?|로정렬)",
        r"(?:값|수|숫자|규모)(?:이|가)?(?:큰|높은|많은)(?:것)?(?:부터|순(?:서)?(?:대로)?|대로|로정렬)",
        r"최(?:대|다)(?:값)?(?:부터|순(?:서)?(?:대로)?)",
    )
    ascending_patterns = (
        r"오름차순",
        r"(?:작은|낮은|적은)(?:값|수|숫자|규모)?(?:부터|순(?:서)?(?:대로)?|로정렬)",
        r"(?:값|수|숫자|규모)(?:이|가)?(?:작은|낮은|적은)(?:것)?(?:부터|순(?:서)?(?:대로)?|대로|로정렬)",
        r"최(?:소|저)(?:값)?(?:부터|순(?:서)?(?:대로)?)",
    )
    wants_descending = any(re.search(pattern, text) for pattern in descending_patterns)
    wants_ascending = any(re.search(pattern, text) for pattern in ascending_patterns)
    if wants_descending == wants_ascending:
        return None
    return "descending" if wants_descending else "ascending"


# 시간 축은 시간순으로, 요청된 값 정렬은 범주별 값 합계 순으로 레코드를 정렬한다.
def sort_records(
    records: list[dict[str, Any]],
    x_is_year: bool,
    chart_type: str,
    sort_order: Literal["ascending", "descending"] | None,
) -> list[dict[str, Any]]:
    if x_is_year or chart_type in TIME_ORDERED_TYPES:
        return sorted(records, key=lambda record: (record.get("x") is None, record.get("x"), str(record.get("series", ""))))
    if sort_order is None and chart_type == "diverging_bar":
        # 증감 차트는 많이 줄어든 쪽에서 늘어난 쪽으로 늘어놓아야 변화의 방향이 한눈에 읽힌다.
        sort_order = "ascending"
    if sort_order and chart_type in VALUE_SORTED_TYPES:
        totals: dict[Any, float] = {}
        for record in records:
            totals[record.get("x")] = totals.get(record.get("x"), 0.0) + float(record["value"])
        category_order = {
            category: index
            for index, (category, _) in enumerate(
                sorted(
                    totals.items(),
                    key=lambda item: item[1],
                    reverse=sort_order == "descending",
                )
            )
        }
        return sorted(records, key=lambda record: category_order[record.get("x")])
    return records


# 응답에 실을 통계표 출처 정보를 만든다.
def stat_block(table: dict) -> dict[str, Any]:
    return {
        "stat_id": table["stat_id"],
        "ref_id": table["ref_id"],
        "publication_year": table["publication_year"],
        "chapter_no": table.get("chapter_no"),
        "section_no": table.get("section_no"),
        "level3_no": table.get("level3_no"),
        "level4_no": table.get("level4_no"),
        "chapter": table.get("chapter"),
        "section": table.get("section"),
        "level3_title": table.get("level3_title"),
        "level4_title": table.get("level4_title"),
        "title_ko": table["title_ko"],
        "title_en": table["title_en"],
        "unit": table["unit"],
        "base_date": table["base_date"],
        "page_start": table.get("page_start"),
        "table_seq": table["table_seq"],
        "caption": table["caption"],
    }


# 모든 변환 경로가 공유하는 structuredContent 응답을 조립한다.
def _build_response(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    total_mode: TotalMode,
    chart: dict[str, Any],
    profiles: list[dict[str, Any]],
    records: list[dict[str, Any]],
    source_rows: list[dict[str, str]],
    warnings: list[str],
    *,
    request_hints: dict[str, Any] | None = None,
    transform: dict[str, Any] | None = None,
    selected_dataset: dict[str, Any] | None = None,
    delta_records: list[dict[str, Any]] | object = _MISSING,
) -> dict[str, Any]:
    chart = {
        **chart,
        "sort_order": (request_hints or {}).get("resolved_sort_order"),
    }
    data: dict[str, Any] = {
        "records": records,
        "record_count": len(records),
        "source_row_count": len(source_rows),
        "table_preview": source_rows[:20],
    }
    if delta_records is not _MISSING:
        data["delta_records"] = delta_records
    if selected_dataset is not None:
        data["selected_dataset"] = selected_dataset

    spec: dict[str, Any] = {
        "ok": True,
        "version": "0.1",
        "library": "vega-lite",
        "renderer": "client",
        "stat": stat_block(table),
        "request": {
            "query": query,
            "chart_type": chart_type,
            "x": x,
            "y": y,
            "group": group,
            "top_n": top_n,
            "total_mode": total_mode,
            **(request_hints or {}),
        },
        "chart": chart,
        "columns": profiles,
        "data": data,
        "warnings": warnings,
    }
    if transform is not None:
        spec = {
            **{key: spec[key] for key in ("ok", "version", "library", "renderer", "stat", "request", "chart", "columns")},
            "transform": transform,
            "data": data,
            "warnings": warnings,
        }
    return spec


# 복합 단위 표에서 선택한 지표 헤더를 기준으로 표시 단위를 좁힌다.
def metric_unit(column: str, table_unit: str | None) -> str:
    lowered = column.lower()
    if "비율" in column or "percentage" in lowered or "ratio" in lowered or "%" in column:
        return "%"
    units = [part.strip() for part in (table_unit or "").split(",") if part.strip()]
    non_percent_units = [unit for unit in units if "%" not in unit]
    if len(units) > 1 and len(non_percent_units) == 1:
        return non_percent_units[0]
    return table_unit or "값"


# 여러 지표 컬럼이 공유하는 헤더 방향을 찾아 차트 범주 라벨을 만든다.
def _metric_labels(columns: list[str], requested_labels: list[str | None]) -> list[str]:
    prefixes = [column.split("_", 1)[0] if "_" in column else column for column in columns]
    suffixes = [column.split("_", 1)[1] if "_" in column else "" for column in columns]
    same_prefix = len(set(prefixes)) == 1 and all(suffixes)
    same_suffix = len(set(suffixes)) == 1 and bool(suffixes[0])

    labels: list[str] = []
    for column, prefix, requested in zip(columns, prefixes, requested_labels):
        if requested:
            labels.append(requested)
        elif same_prefix:
            labels.append(family_category_label(column))
        elif same_suffix:
            labels.append(display_category_label(prefix))
        else:
            labels.append(display_category_label(column))
    return labels


# 구조화된 선택 계획을 검증하고 같은 데이터셋으로 표와 차트 응답을 만든다.
def _selection_plan_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    total_mode: TotalMode,
    source_rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    metrics: list[dict[str, str | None]],
    warnings: list[str],
    target_year: int | None,
    request_hints: dict[str, Any],
) -> dict[str, Any]:
    profile_map = profile_by_name(profiles)
    validated: list[dict[str, str]] = []
    validation_errors: list[str] = []
    seen_columns: set[str] = set()

    if not metrics:
        validation_errors.append("metrics에는 하나 이상의 숫자 컬럼을 지정해야 합니다.")
    for metric in metrics:
        requested_column = str(metric.get("column") or "").strip()
        label = str(metric.get("label") or "").strip()
        requested_unit = str(metric.get("unit") or "").strip()
        # 컬럼명은 영문 병기와 띄어쓰기가 섞여 있어 표기가 조금 달라도 같은 컬럼으로 본다.
        column = resolve_column(requested_column, profiles) or requested_column
        profile = profile_map.get(column)
        if profile is None:
            validation_errors.append(f"선택 지표 컬럼 '{requested_column}'이 원본 표에 없습니다.")
            continue
        if not profile["is_numeric"]:
            validation_errors.append(f"선택 지표 컬럼 '{column}'은 숫자형이 아닙니다.")
            continue
        if column in seen_columns:
            validation_errors.append(f"선택 지표 컬럼 '{column}'이 중복되었습니다.")
            continue

        inferred_unit = metric_unit(column, table.get("unit"))
        valid_units = {part.strip() for part in str(table.get("unit") or "").split(",") if part.strip()}
        valid_units.add(inferred_unit)
        if requested_unit and requested_unit not in valid_units:
            validation_errors.append(
                f"선택 지표 '{column}'의 단위 '{requested_unit}'이 표 단위 '{table.get('unit')}'와 맞지 않습니다."
            )
            continue
        seen_columns.add(column)
        validated.append({
            "column": column,
            "label": label,
            "unit": requested_unit or inferred_unit,
        })

    # 지표 일부만 확인돼도 확인된 지표로 그린다. 확인하지 못한 지표는 경고로만 알리고 채우지 않는다.
    warnings.extend(validation_errors)
    if not validated or not source_rows:
        if not source_rows and not validation_errors:
            warnings.append("선택 조건에 맞는 원본 표 행이 없습니다.")
        chart = {
            "type": "table",
            "requested_type": chart_type,
            "decision_source": "server_validation",
            "reason": "요청한 행 또는 지표를 원본 표에서 검증하지 못해 차트를 생성하지 않았습니다.",
            "title": _chart_title(table),
            "x": "category",
            "y": "value",
            "group": None,
            "unit": table.get("unit"),
        }
        return _build_response(
            table, query, chart_type, x, y, group, top_n, total_mode, chart, profiles,
            [], source_rows, warnings, request_hints=request_hints,
            transform={"type": "validated_selection_plan", "metrics": validated},
            selected_dataset={"columns": ["x", "value", "series"], "records": [], "provenance": []},
        )

    columns = [metric["column"] for metric in validated]
    labels = _metric_labels(columns, [metric.get("label") for metric in validated])
    # 범주 컬럼이 없으면 연도 컬럼을 축으로 쓴다. 축을 못 찾으면 모든 행이 한 칸에 겹쳐 쌓인다.
    axis_profiles = [
        profile for profile in profiles if profile.get("is_categorical")
    ] or [profile for profile in profiles if profile["is_year"]]
    x_column = resolve_column(x, profiles)
    if x_column and not profile_map[x_column].get("is_categorical") and not profile_map[x_column].get("is_year"):
        warnings.append(f"선택 계획의 x축 컬럼 '{x_column}'은 범주형 또는 연도형이 아닙니다.")
        x_column = None
    x_column = x_column or (axis_profiles[0]["name"] if axis_profiles else None)
    x_profile = profile_map.get(x_column) if x_column else None

    records: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    single_row = len(source_rows) == 1
    for row_index, row in enumerate(source_rows):
        row_category = row_x_value(row, x_column, x_profile)
        for metric, label in zip(validated, labels):
            value = parse_number(row.get(metric["column"]))
            if value is None:
                continue
            record = {
                "x": label if single_row else row_category,
                "value": value,
                "series": None if single_row or len(validated) == 1 else label,
            }
            records.append(record)
            provenance.append({
                "record": record,
                "source_row_index": row_index,
                "source_row": {key: row.get(key) for key in row if key == x_column},
                "source_column": metric["column"],
                "source_value": row.get(metric["column"]),
                "label": label,
                "unit": metric["unit"],
            })

    records = filter_chart_records(
        records, query, total_mode, target_year=target_year, apply_query_filters=False,
    )
    allowed_record_ids = {id(record) for record in records}
    provenance = [item for item in provenance if id(item["record"]) in allowed_record_ids]
    has_group = any(record.get("series") for record in records)
    selected_type, decision_source, _ = _select_chart(
        chart_type, query, records, x_profile if not single_row else None, has_group, warnings,
    )
    records = _drop_total_slices(records, selected_type)
    records = _limit_series(records, warnings)
    records = limit_categories(records, selected_type, bool(x_profile and x_profile["is_year"]), top_n, warnings)
    records = sort_records(
        records,
        bool(x_profile and x_profile["is_year"]),
        selected_type,
        request_hints.get("resolved_sort_order"),
    )
    visible_record_ids = {id(record) for record in records}
    provenance = [item for item in provenance if id(item["record"]) in visible_record_ids]

    units = {metric["unit"] for metric in validated}
    chart_unit = next(iter(units)) if len(units) == 1 else table.get("unit")
    if not records:
        warnings.append("선택한 행의 지표 값이 비어 있어 차트 데이터를 만들지 못했습니다.")

    # 지표마다 단위가 달라도 한 축에 그리면 작은 단위 지표가 축 바닥에 눌린다.
    chart_series = [
        {"label": label, "unit": metric["unit"]}
        for metric, label in zip(validated, labels)
        if any(record.get("series") == label for record in records)
    ]
    if has_group:
        selected_type, dual_axis = apply_axis_split(selected_type, chart_series)
    else:
        dual_axis = False
    chart = {
        "type": selected_type,
        "requested_type": chart_type,
        "decision_source": (
            "server_validation" if not records
            else "selection_plan" if decision_source != "server_fallback"
            else decision_source
        ),
        "reason": (
            "선택한 원본 셀에 숫자 값이 없어 차트를 생성하지 않았습니다."
            if not records
            else "원본 표와 대조한 행·지표 선택 계획으로 차트 데이터를 구성했습니다."
            + (
                " 지표마다 단위가 달라 값 축을 좌우로 나누고 계열별로 mark를 달리했습니다."
                if dual_axis else ""
            )
        ),
        "title": _chart_title(table),
        "x": "metric" if single_row else x_column,
        "y": "value",
        "group": "metric" if has_group else None,
        "unit": chart_unit,
        "series": chart_series if has_group else None,
        "dual_axis": dual_axis,
    }
    return _build_response(
        table, query, chart_type, x, y, group, top_n, total_mode, chart, profiles,
        records, source_rows, warnings, request_hints=request_hints,
        transform={
            "type": "validated_selection_plan",
            "row_shape": "single_row_metrics" if single_row else "rows_by_metrics",
            "metrics": validated,
        },
        selected_dataset={
            "columns": ["x", "value", "series"],
            "records": records,
            "provenance": provenance,
            "unit": chart_unit,
        },
    )


# 행이 지표, 열이 연도인 표에서 사용자가 고른 행들을 연도 축 시계열로 편다.
# 이런 표에서 연도는 계열이 아니라 x축이므로, 고른 행 하나하나가 계열이 된다.
# 행을 직접 고른 요청에만 적용해, 표 전체를 그리는 기존 경로는 건드리지 않는다.
def _wide_year_selected_rows_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    total_mode: TotalMode,
    source_rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    metrics: list[dict[str, str | None]] | None,
    warnings: list[str],
    request_hints: dict[str, Any],
) -> dict[str, Any] | None:
    if len(source_rows) < 2:
        return None
    year_columns = year_value_columns(profiles)
    if len(year_columns) < 2:
        return None

    if metrics is not None:
        # 연도 컬럼을 지표로 받아 왔다면 그건 계열이 아니라 x축이다. 연도가 아닌 컬럼이
        # 하나라도 섞여 있으면 지표를 고른 요청이므로 이 경로를 쓰지 않는다.
        requested = [
            resolve_column(str(metric.get("column") or ""), profiles) for metric in metrics
        ]
        year_columns = [item for item in year_columns if item[1] in set(requested)]
        if len(year_columns) < 2 or len(year_columns) != len(requested):
            return None

    category_column = (resolve_column(x, profiles) if x else None) or next(
        (profile["name"] for profile in profiles if profile.get("is_categorical", False)), None,
    )
    if category_column is None:
        return None

    records: list[dict[str, Any]] = []
    labels: list[str] = []
    for row in source_rows:
        label = display_category_label(row.get(category_column))
        for year, column in year_columns:
            value = parse_number(row.get(column))
            if value is not None:
                records.append({"x": year, "value": value, "series": label})
                if label not in labels:
                    labels.append(label)
    if len(labels) < 2:
        return None

    records = _limit_series(records, warnings)
    year_profile = {"name": "year", "is_year": True, "is_numeric": False, "is_categorical": False}
    selected_type, decision_source, reason = _select_chart(
        chart_type, query, records, year_profile, True, warnings,
    )
    records = sort_records(records, True, selected_type, None)

    # '수'와 '비율'처럼 행마다 단위가 다르면 한 축에 겹쳐 그릴 수 없다.
    chart_series = [
        {"label": label, "unit": metric_unit(label, table["unit"])}
        for label in labels
        if any(record.get("series") == label for record in records)
    ]
    selected_type, dual_axis = apply_axis_split(selected_type, chart_series)
    if dual_axis:
        reason = f"{reason} 행마다 단위가 달라 값 축을 좌우로 나누고 계열별로 mark를 달리했습니다."

    chart = {
        "type": selected_type,
        "requested_type": chart_type,
        "decision_source": decision_source,
        "reason": f"행이 지표, 열이 연도인 표에서 고른 행을 연도별 계열로 폈습니다. {reason}",
        "title": _chart_title(table),
        "x": "year",
        "y": "value",
        "group": category_column,
        "series": chart_series,
        "dual_axis": dual_axis,
        "unit": table["unit"],
    }
    return _build_response(
        table, query, chart_type, x, y, group, top_n, total_mode, chart, profiles,
        records, source_rows, warnings,
        request_hints=request_hints,
        transform={
            "type": "wide_year_selected_rows",
            "category_column": category_column,
            "year_columns": [{"year": year, "column": column} for year, column in year_columns],
        },
    )


# 행은 범주, 열은 연도인 표를 범주마다 한 줄씩 갖는 시계열로 편다.
# 한 행만 골라 펴는 _wide_year_time_series_spec과 달리 여러 범주의 움직임을 함께 본다.
def _wide_year_multi_series_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    total_mode: TotalMode,
    source_rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    warnings: list[str],
    request_hints: dict[str, Any],
) -> dict[str, Any] | None:
    requested_type = chart_type if chart_type in VALID_CHART_TYPES else "auto"
    wants_rank = wants_words(query, RANK_WORDS)
    if requested_type not in {"bump", "slope"} and not (requested_type == "auto" and wants_rank):
        return None

    year_columns = year_value_columns(profiles)
    if len(year_columns) < 2:
        return None
    category_column = resolve_column(x, profiles) if x else None
    category_column = category_column or next(
        (profile["name"] for profile in profiles if profile.get("is_categorical", False)), None,
    )
    if category_column is None:
        return None

    # 전국 합계 행은 개별 범주와 나란히 두면 순위도 기울기도 뜻이 달라진다.
    rows = source_rows
    if resolve_total_mode(total_mode, query) != "include":
        rows = [row for row in source_rows if not is_total_label(row.get(category_column))]
    if len(rows) < 2:
        return None

    selected_type = "slope" if requested_type == "slope" else "bump"
    # 기울기 그래프는 두 시점만 잇는다. 처음과 마지막 연도를 견준다.
    selected_columns = (
        [year_columns[0], year_columns[-1]] if selected_type == "slope" else year_columns
    )
    records: list[dict[str, Any]] = []
    for row in rows:
        label = display_category_label(row.get(category_column))
        for year, column in selected_columns:
            value = parse_number(row.get(column))
            if value is not None:
                records.append({"x": year, "value": value, "series": label})
    if len(records) < 4:
        return None

    records = _limit_series(records, warnings)
    records = sort_records(records, True, selected_type, None)
    reason = (
        "행이 범주, 열이 연도인 표를 펴서 처음과 마지막 연도 사이의 범주별 변화를 기울기로 그렸습니다."
        if selected_type == "slope"
        else "행이 범주, 열이 연도인 표를 펴서 연도마다 범주 순위를 매겨 이었습니다."
    )
    chart = {
        "type": selected_type,
        "requested_type": chart_type,
        "decision_source": "server_auto" if requested_type == "auto" else "client_spec_validated",
        "reason": reason,
        "title": _chart_title(table),
        "x": "year",
        "y": "value",
        "group": category_column,
        "unit": table["unit"],
    }
    return _build_response(
        table, query, chart_type, x, y, group, top_n, total_mode, chart, profiles,
        records, source_rows, warnings,
        request_hints=request_hints,
        transform={
            "type": "wide_year_rows_to_series",
            "category_column": category_column,
            "year_columns": [{"year": year, "column": column} for year, column in selected_columns],
        },
    )


# 행은 범주, 열은 연도인 표를 시계열 차트 spec으로 변환한다.
def _wide_year_time_series_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    total_mode: TotalMode,
    source_rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    warnings: list[str],
    target_year: int | None,
    request_hints: dict[str, Any],
) -> dict[str, Any] | None:
    requested_type = chart_type if chart_type in VALID_CHART_TYPES else "auto"
    if requested_type != chart_type:
        warnings.append(f"지원하지 않는 차트 타입 '{chart_type}' 대신 auto를 사용했습니다.")

    if not wants_trend_chart(query, requested_type, x):
        return None

    year_columns = year_value_columns(profiles)
    if len(year_columns) < 2:
        return None

    category_columns = [
        profile["name"]
        for profile in profiles
        if profile.get("is_categorical", False)
    ]
    category_column = None
    if x and normalize_key(x) not in {"year", "date", "연도", "년도"}:
        category_column = resolve_column(x, profiles)
    category_column = category_column or (category_columns[0] if category_columns else None)
    if category_column is None:
        return None

    # 합계 행은 포커스 행을 고르기 전에 제외해야 한다.
    resolved_total_mode = resolve_total_mode(total_mode, query)
    eligible_rows = source_rows
    if resolved_total_mode != "include":
        eligible_rows = [row for row in source_rows if not is_total_label(row.get(category_column))]

    focus_row = pick_focus_row(eligible_rows, category_column, query, x, y, group)
    if focus_row is None and len(eligible_rows) == 1:
        focus_row = eligible_rows[0]
    if focus_row is None:
        return None

    records: list[dict[str, Any]] = []
    for year, column in year_columns:
        value = parse_number(focus_row.get(column))
        if value is not None:
            records.append({"x": year, "value": value, "series": None})
    if len(records) < 2:
        return None

    records = filter_chart_records(records, query, total_mode, target_year=target_year)
    if not records:
        return None

    selected_category = display_category_label(focus_row.get(category_column))
    deltas = [
        {"x": cur["x"], "value": cur["value"] - prev["value"], "series": "전년 대비 증감"}
        for prev, cur in zip(records, records[1:])
    ]

    delta_records: list[dict[str, Any]] = []
    if requested_type in CHANGE_CHART_TYPES and deltas:
        # 값 자체가 아니라 변화를 그려 달라는 요청이라 전년 대비 증감을 본 차트로 세운다.
        selected_type = requested_type
        records = deltas
        decision_source = "client_spec_validated"
        reason = "연도별 값에서 전년 대비 증감을 계산해 요청한 변화 차트로 그렸습니다."
    else:
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
        if wants_delta_chart(query):
            delta_records = deltas

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

    return _build_response(
        table, query, chart_type, x, y, group, top_n, total_mode, chart, profiles,
        records, source_rows, warnings,
        request_hints=request_hints,
        transform={
            "type": "wide_year_row_to_time_series",
            "category_column": category_column,
            "selected_category": selected_category,
            "year_columns": [{"year": year, "column": column} for year, column in year_columns],
        },
        delta_records=delta_records,
    )


# 특정 행에서 같은 상위 헤더 아래 지표들을 범주형 레코드로 펼친다.
def _wide_row_category_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    total_mode: TotalMode,
    source_rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    warnings: list[str],
    target_year: int | None,
    requested_family: str | None,
    request_hints: dict[str, Any],
) -> dict[str, Any] | None:
    requested_type = chart_type if chart_type in VALID_CHART_TYPES else "auto"
    if not source_rows:
        return None
    year_profile = next((profile for profile in profiles if profile["is_year"]), None)
    family_prefix, family_columns = _pick_column_family(
        table, profiles, query, x, y, requested_family, warnings,
    )
    category_profiles = [
        profile for profile in profiles if profile.get("is_categorical", False)
    ]
    category_profile = next(
        (
            profile for profile in category_profiles
            if resolve_column(group, [profile]) or resolve_column(x, [profile])
        ),
        category_profiles[0] if category_profiles else None,
    )
    if len(family_columns) < 2 or (target_year is None and category_profile is None):
        return None

    if target_year is not None and year_profile is not None:
        target_column = year_profile["name"]
        selected_row = next(
            (row for row in source_rows if parse_year(row.get(target_column)) == target_year),
            None,
        )
        target_label = f"{target_year}년"
    else:
        target_column = category_profile["name"]
        selected_row = source_rows[0] if len(source_rows) == 1 else pick_focus_row(
            source_rows, target_column, query, x, y, group,
        )
        target_label = display_category_label(selected_row.get(target_column)) if selected_row else ""
    selection = request_hints.get("selection", {})
    selected_place = selection.get("city_value") or selection.get("query_row_value")
    if selected_place and normalize_key(selected_place) not in normalize_key(target_label):
        target_label = f"{target_label} {display_category_label(selected_place)}".strip()
    if selected_row is None:
        if target_year is not None:
            warnings.append(f"표에서 {target_year}년 행을 찾지 못했습니다.")
        elif group:
            warnings.append(f"표에서 '{group}'에 해당하는 행을 찾지 못했습니다.")
        return None

    resolved_total_mode = resolve_total_mode(total_mode, query)
    aggregate_columns = [column for column in family_columns if is_total_column(column)]
    # 집계 열은 하위 범주와 중복될 수 있어 auto에서도 제외한다.
    applied_total_mode = "include" if resolved_total_mode == "include" else "exclude" if aggregate_columns else "not_applicable"
    excluded_columns = aggregate_columns if applied_total_mode == "exclude" else []

    aggregate_values = [
        value
        for column in aggregate_columns
        if (value := parse_number(selected_row.get(column))) is not None
    ]
    component_values = [
        value
        for column in family_columns
        if column not in aggregate_columns
        if (value := parse_number(selected_row.get(column))) is not None
    ]
    component_sum = sum(component_values)
    aggregate_matches_components = any(
        abs(value - component_sum) <= max(1e-9, abs(value) * 1e-6)
        for value in aggregate_values
    )
    records: list[dict[str, Any]] = []
    selected_columns: list[str] = []
    for column in family_columns:
        if column in excluded_columns:
            continue
        value = parse_number(selected_row.get(column))
        if value is None:
            continue
        selected_columns.append(column)
        records.append({"x": family_category_label(column), "value": value, "series": None})

    records = filter_chart_records(records, query, total_mode)
    if len(records) < 2:
        return None

    # 한 행의 지표들을 범주로 편 구조라 계열도 시간 축도 없다. 그 구조에 맞는 차트만 남긴다.
    categories, series, has_negative = _record_shape(records)
    if requested_type == "auto":
        selected_type = _auto_chart(query, False, False, categories, series, has_negative)[0]
    else:
        corrected = _correct_chart(
            requested_type, False, False, False, categories, series, has_negative,
        )
        selected_type = corrected[0] if corrected is not None else requested_type
    records = _drop_total_slices(records, selected_type)
    records = limit_categories(records, selected_type, False, top_n, warnings)
    records = sort_records(
        records,
        False,
        selected_type,
        request_hints.get("resolved_sort_order"),
    )
    if applied_total_mode == "not_applicable":
        total_reason = "선택한 범주에서 집계 범주를 찾지 못했습니다."
    elif applied_total_mode == "exclude" and resolved_total_mode == "auto":
        total_reason = "하위 범주와 중복되는 집계 범주를 자동 제외했습니다."
    elif applied_total_mode == "exclude":
        total_reason = "total_mode=exclude 요청에 따라 집계 범주를 제외했습니다."
    else:
        total_reason = "total_mode=include 요청에 따라 집계 범주를 유지했습니다."

    chart = {
        "type": selected_type,
        "requested_type": chart_type,
        "decision_source": "server_wide_row",
        "reason": (
            f"{target_label} 행을 선택하고 같은 상위 헤더의 지표들을 범주로 변환했습니다. "
            f"{total_reason}"
        ),
        "title": _chart_title(table, target_label or None),
        "x": "category",
        "y": "value",
        "group": None,
        "unit": table["unit"],
    }
    return _build_response(
        table, query, chart_type, x, y, group, top_n, total_mode, chart, profiles,
        records, source_rows, warnings,
        request_hints=request_hints,
        transform={
            "type": "wide_row_to_categories",
            "target_column": target_column,
            "target_value": selected_row.get(target_column),
            "selected_year": target_year,
            "column_family": family_prefix,
            "selected_columns": selected_columns,
            "requested_total_mode": total_mode,
            "resolved_total_mode": resolved_total_mode,
            "applied_total_mode": applied_total_mode,
            "excluded_total_columns": excluded_columns,
            "aggregate_values": aggregate_values,
            "component_sum": component_sum,
            "aggregate_matches_components": aggregate_matches_components,
        },
    )


# 표 데이터와 요청값을 차트 렌더링용 spec으로 만든다.
def build_plot_spec(
    table: dict,
    query: str | None,
    chart_type: str,
    x: str | None,
    y: str | None,
    group: str | None,
    top_n: int | None,
    total_mode: TotalMode = "exclude",
    year: int | None = None,
    city: str | None = None,
    column_family_name: str | None = None,
    filters: list[dict[str, str]] | None = None,
    metrics: list[dict[str, str | None]] | None = None,
    title: str | None = None,
    sort_order: SortOrder = "auto",
) -> dict[str, Any]:
    columns, all_source_rows, warnings = body_to_rows(table["body"])
    resolved_sort_order = resolve_sort_order(sort_order, query, warnings)
    profiles = profile_columns(columns, all_source_rows)
    profile_map = profile_by_name(profiles)
    target_year = requested_year(year, query)
    explicit_selection = filters is not None or metrics is not None
    source_rows, selection, selection_warnings = select_source_rows(
        all_source_rows, profiles, target_year, city, None if explicit_selection else query,
    )
    warnings.extend(selection_warnings)
    applied_filters: list[dict[str, Any]] = []
    filter_errors: list[str] = []
    if filters is not None:
        source_rows, applied_filters, filter_errors = apply_exact_filters(
            source_rows, profiles, filters,
        )
        warnings.extend(filter_errors)
        selection["selected_row_count"] = len(source_rows)
    selection["filters"] = applied_filters
    request_hints = {
        "year": year,
        "city": city,
        "column_family": column_family_name,
        "filters": filters,
        "metrics": metrics,
        "sort_order": sort_order,
        "resolved_sort_order": resolved_sort_order,
        "resolved_year": target_year,
        "selection": selection,
    }

    # 행을 직접 골라 온 요청은 연도 축 시계열일 수 있다. 이 판정을 metrics보다 먼저 해야
    # 연도 컬럼을 지표로 받았을 때 축이 뒤집히지 않는다.
    if filters is not None and source_rows:
        selected_rows_spec = _wide_year_selected_rows_spec(
            table, query, chart_type, x, y, group, top_n, total_mode, source_rows, profiles,
            metrics, warnings, request_hints,
        )
        if selected_rows_spec is not None:
            return apply_display_title(selected_rows_spec, title)

    if metrics is not None:
        return apply_display_title(
            _selection_plan_spec(
                table, query, chart_type, x, y, group, top_n, total_mode, source_rows, profiles,
                metrics, warnings, target_year, request_hints,
            ),
            title,
        )

    multi_series_spec = _wide_year_multi_series_spec(
        table, query, chart_type, x, y, group, top_n, total_mode, source_rows, profiles, warnings,
        request_hints,
    )
    if multi_series_spec is not None:
        return apply_display_title(multi_series_spec, title)

    wide_spec = _wide_year_time_series_spec(
        table, query, chart_type, x, y, group, top_n, total_mode, source_rows, profiles, warnings,
        target_year, request_hints,
    )
    if wide_spec is not None:
        return apply_display_title(wide_spec, title)

    wide_category_spec = _wide_row_category_spec(
        table, query, chart_type, x, y, group, top_n, total_mode, source_rows, profiles, warnings,
        target_year, column_family_name, request_hints,
    )
    if wide_category_spec is not None:
        return apply_display_title(wide_category_spec, title)

    family_columns = column_family(column_family_name, profiles)
    family_validation_failed = bool(column_family_name and not family_columns)
    if family_validation_failed:
        source_rows = []

    x_column = resolve_column(x, profiles) or pick_x_column(profiles, query)
    group_column = resolve_column(group, profiles)

    # 상위 헤더를 지정했으면 그 아래 컬럼만 그린다. 지정하지 않으면 숫자 컬럼을 모두 쓴다.
    numeric_columns = [
        profile["name"]
        for profile in profiles
        if profile["is_numeric"] and profile["name"] not in {x_column, group_column}
        and (not family_columns or profile["name"] in family_columns)
    ]
    y_column = resolve_column(y, profiles)
    if y_column and not profile_map[y_column]["is_numeric"]:
        warnings.append(f"'{y_column}' 컬럼은 숫자형으로 보기 어려워 y축에서 제외했습니다.")
        y_column = None
    if y_column is None:
        y_column = pick_column_from_query(query, numeric_columns)

    records: list[dict[str, Any]] = []
    y_source: str | None = y_column
    series_source: str | None = group_column
    x_profile = profile_map.get(x_column) if x_column else None

    if y_column:
        for row in source_rows:
            value = parse_number(row.get(y_column))
            if value is None:
                continue
            records.append({
                "x": row_x_value(row, x_column, x_profile),
                "value": value,
                "series": row.get(group_column) if group_column else None,
            })
    elif numeric_columns:
        y_source = "value"
        # 상위 헤더로 좁힌 컬럼은 헤더가 이미 제목에 드러나므로 하위 항목명만 라벨로 쓴다.
        def column_label(column: str) -> str:
            return family_category_label(column) if family_columns else column

        if len(source_rows) == 1 and not group_column:
            x_column = "metric"
            x_profile = None
            series_source = None
            row = source_rows[0]
            for column in numeric_columns:
                value = parse_number(row.get(column))
                if value is not None:
                    records.append({"x": column_label(column), "value": value, "series": None})
        else:
            series_source = "metric" if not group_column else group_column
            for row in source_rows:
                x_value = row_x_value(row, x_column, x_profile)
                for column in numeric_columns:
                    value = parse_number(row.get(column))
                    if value is not None:
                        series = row.get(group_column) if group_column else column_label(column)
                        records.append({"x": x_value, "value": value, "series": series})

    # 계열 제한 → 차트 선택 → 공통 필터 순서는 기존 응답을 보존한다.
    records = _limit_series(records, warnings)
    has_group = any(record.get("series") for record in records)
    selected_type, decision_source, reason = _select_chart(
        chart_type, query, records, x_profile, has_group, warnings,
    )
    if not source_rows and (selection_warnings or filter_errors or family_validation_failed):
        decision_source = "server_validation"
        reason = "요청한 행 또는 컬럼군을 표에서 확인하지 못해 전체 데이터로 대체하지 않았습니다."
    records = filter_chart_records(records, query, total_mode, target_year=target_year)
    records = _drop_total_slices(records, selected_type)

    x_is_year = bool(x_profile and x_profile["is_year"])
    records = limit_categories(records, selected_type, x_is_year, top_n, warnings)
    records = sort_records(records, x_is_year, selected_type, resolved_sort_order)

    # 계열이 지표 컬럼이면 컬럼마다 단위가 다를 수 있어 값 축을 좌우로 나눠야 한다.
    chart_series = [
        {"label": label, "unit": metric_unit(str(label), table["unit"])}
        for label in dict.fromkeys(
            record["series"] for record in records if record.get("series")
        )
    ] if has_group and series_source == "metric" else []
    dual_axis = False
    if chart_series:
        selected_type, dual_axis = apply_axis_split(selected_type, chart_series)
        if dual_axis:
            reason = f"{reason} 지표마다 단위가 달라 값 축을 좌우로 나누고 계열별로 mark를 달리했습니다."

    chart = {
        "type": selected_type,
        "requested_type": chart_type,
        "decision_source": decision_source,
        "reason": reason,
        "title": _chart_title(table),
        "series": chart_series or None,
        "dual_axis": dual_axis,
        "x": x_column,
        "y": y_source,
        "group": series_source if has_group else None,
        "unit": table["unit"],
    }
    return apply_display_title(
        _build_response(
            table, query, chart_type, x, y, group, top_n, total_mode, chart, profiles,
            records, source_rows, warnings,
            request_hints=request_hints,
        ),
        title,
    )
