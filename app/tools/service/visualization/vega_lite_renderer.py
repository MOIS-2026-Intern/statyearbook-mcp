"""시각화 명세를 Vega-Lite 형식으로 변환한다."""
from math import tau
from typing import Any


VALUE_FORMAT = ",.2~f"
LABEL_COLOR = "#344054"
ON_MARK_LABEL_COLOR = "#111827"
LABEL_FONT_SIZE = 11
# 막대 꼭대기의 합계는 층 값보다 눈에 먼저 들어오도록 굵게 쓴다.
TOTAL_LABEL_FONT_WEIGHT = 700
# 세로 막대는 글자 높이에 위아래 여백을 더한 만큼, 가로 막대는 글자 수만큼의 폭이 있어야
# 값이 층 밖으로 삐져나오지 않는다.
STACK_LABEL_MIN_HEIGHT_PX = 18
STACK_LABEL_CHAR_WIDTH_PX = 7
STACK_LABEL_SIDE_PADDING_PX = 12


# 범례와 Vega-Lite text mark가 같은 형태의 숫자를 보여주도록 포맷한다.
def _format_number(value: float) -> str:
    if value.is_integer():
        return f"{value:,.0f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


# x축이 연도인지 판별한다(Vega 축 타입 결정용).
def _vega_x_is_year(spec: dict[str, Any]) -> bool:
    x_name = spec["chart"].get("x")
    if x_name == "year":
        return True
    for profile in spec.get("columns", []):
        if profile.get("name") == x_name:
            return bool(profile.get("is_year"))
    return False


# 누적 막대의 값 라벨 레이어를 만든다.
# 층 값은 층 가운데에 두되 층이 얇으면 겹치므로 숨기고, 막대 전체 합계는 꼭대기에 표시한다.
def _stacked_label_layers(
    value_axis: dict[str, Any],
    horizontal: bool,
    stack_order: dict[str, Any],
) -> list[dict[str, Any]]:
    value_channel = "x" if horizontal else "y"
    # 값 축은 0에서 시작하는 선형 축이라 scale(0)과의 거리가 곧 층의 실제 픽셀 크기다.
    # 축이 확정된 뒤 계산되므로 렌더 크기를 짐작하지 않아도 된다.
    available_px = (
        "scale('x', datum.value) - scale('x', 0)" if horizontal
        else "scale('y', 0) - scale('y', datum.value)"
    )
    required_px = (
        f"length(format(datum.value, '{VALUE_FORMAT}')) * {STACK_LABEL_CHAR_WIDTH_PX}"
        f" + {STACK_LABEL_SIDE_PADDING_PX}"
        if horizontal
        else str(STACK_LABEL_MIN_HEIGHT_PX)
    )
    total_mark: dict[str, Any] = {
        "type": "text",
        "fontSize": LABEL_FONT_SIZE,
        "fontWeight": TOTAL_LABEL_FONT_WEIGHT,
    }
    total_mark.update(
        {"dx": 8, "align": "left", "baseline": "middle"} if horizontal
        else {"dy": -8, "baseline": "bottom"}
    )
    return [
        {
            "mark": {
                "type": "text",
                "fontSize": LABEL_FONT_SIZE,
                "align": "center",
                "baseline": "middle",
            },
            "encoding": {
                value_channel: {**value_axis, "stack": "zero", "bandPosition": 0.5},
                "order": stack_order,
                # 층이 좁으면 레코드를 지우는 대신 빈 문자열을 그려 층 위치를 그대로 유지한다.
                "text": {
                    "condition": {
                        "test": f"({available_px}) >= ({required_px})",
                        "field": "value",
                        "type": "quantitative",
                        "format": VALUE_FORMAT,
                    },
                    "value": "",
                },
                "color": {"value": ON_MARK_LABEL_COLOR},
            },
        },
        {
            "mark": total_mark,
            "encoding": {
                value_channel: {**value_axis, "aggregate": "sum"},
                "text": {
                    "aggregate": "sum",
                    "field": "value",
                    "type": "quantitative",
                    "format": VALUE_FORMAT,
                },
                "color": {"value": LABEL_COLOR},
            },
        },
    ]


# 계열별 쌓는 순서를 정한다. 색상 범례는 계열명 오름차순이라, 첫 계열이 맨 위에 오도록
# 내림차순 순위를 매겨 Vega-Lite 기본 누적 순서와 같은 모양을 유지한다.
def _stack_order(records: list[dict[str, Any]]) -> dict[Any, int]:
    series_names = sorted({
        record.get("series") for record in records if record.get("series") is not None
    }, reverse=True)
    return {name: index for index, name in enumerate(series_names)}


# 범주를 막대 합계 기준으로 정렬한 순서를 만든다(값이 같으면 원래 순서를 유지한다).
def _category_order(records: list[dict[str, Any]], sort_order: str | None) -> list[Any] | None:
    if sort_order not in {"ascending", "descending"}:
        return None
    totals: dict[Any, float] = {}
    for record in records:
        key = record.get("x")
        totals[key] = totals.get(key, 0.0) + float(record.get("value") or 0)
    return [
        key for key, _ in sorted(
            totals.items(), key=lambda item: item[1], reverse=sort_order == "descending",
        )
    ]


# 내부 차트 타입을 Vega-Lite mark/encoding 뷰로 변환한다.
def _vega_view(
    chart: dict[str, Any],
    has_series: bool,
    x_is_year: bool,
    category_order: list[Any] | None = None,
) -> dict[str, Any]:
    ctype = chart["type"]
    unit = chart.get("unit") or "값"

    if ctype == "donut":
        return {
            "layer": [
                {
                    "mark": {"type": "arc", "innerRadius": 50},
                    "encoding": {
                        "theta": {
                            "field": "value",
                            "type": "quantitative",
                            "stack": True,
                        },
                        "color": {
                            "field": "_legend_label",
                            "type": "nominal",
                            "title": "",
                            "sort": {
                                "field": "_order",
                                "op": "min",
                                "order": "ascending",
                            },
                            "scale": {"scheme": "tableau10"},
                        },
                        "order": {
                            "field": "_order",
                            "type": "quantitative",
                            "sort": "ascending",
                        },
                        "tooltip": [
                            {"field": "x", "type": "nominal", "title": ""},
                            {
                                "field": "value",
                                "type": "quantitative",
                                "title": unit,
                                "format": ",.2~f",
                            },
                        ],
                    },
                },
                {
                    # 기본 Vega-Lite 렌더러에서도 겹침을 피하도록 충분히 넓은 조각만 표시한다.
                    # 작은 조각의 값은 색상 범례에서 범주와 함께 표시한다.
                    "transform": [{"filter": "datum._share >= 0.06"}],
                    "mark": {"type": "text", "radius": 90, "fontSize": 11},
                    "encoding": {
                        "theta": {
                            "field": "_mid_angle",
                            "type": "quantitative",
                            "scale": None,
                        },
                        "text": {"field": "value", "type": "quantitative", "format": ",.2~f"},
                        "color": {"value": "#111827"},
                    },
                },
            ],
        }
    if ctype == "heatmap":
        return {
            "encoding": {
                "x": {"field": "x", "type": "nominal", "title": ""},
                "y": {"field": "series", "type": "nominal", "title": ""},
                "color": {"field": "value", "type": "quantitative", "title": unit},
            },
            "layer": [
                {"mark": "rect"},
                {
                    "mark": {"type": "text", "fontSize": 11},
                    "encoding": {
                        "text": {"field": "value", "type": "quantitative", "format": ",.2~f"},
                        "color": {"value": "#111827"},
                    },
                },
            ],
        }

    mark_map: dict[str, Any] = {
        "bar": "bar",
        "grouped_bar": "bar",
        "stacked_bar": "bar",
        "line": {"type": "line", "point": True},
        "area": "area",
        "scatter": "point",
    }
    is_bar = ctype in {"bar", "grouped_bar", "stacked_bar"}
    # 막대는 기본 세로형이고 orientation=horizontal일 때만 값·범주 축을 교환한다.
    horizontal = is_bar and chart.get("orientation") == "horizontal"
    x_type = "quantitative" if ctype == "scatter" else "ordinal" if x_is_year else "nominal"
    category_axis: dict[str, Any] = {"field": "x", "type": x_type, "title": ""}
    value_axis: dict[str, Any] = {"field": "value", "type": "quantitative", "title": unit}
    sort_order = chart.get("sort_order")
    if is_bar and sort_order in {"ascending", "descending"}:
        # 누적 막대는 라벨 레이어마다 데이터셋이 갈려 op 기반 정렬이 무시되므로 미리 계산한 순서를 쓴다.
        category_axis["sort"] = category_order or {
            "field": "value",
            "op": "sum",
            "order": sort_order,
        }
    encoding: dict[str, Any] = (
        {"x": value_axis, "y": category_axis} if horizontal
        else {"x": category_axis, "y": value_axis}
    )
    if has_series:
        encoding["color"] = {"field": "series", "type": "nominal", "title": ""}
        if ctype == "grouped_bar":
            encoding["yOffset" if horizontal else "xOffset"] = {"field": "series"}
    if ctype == "stacked_bar" and has_series:
        # 레이어마다 쌓는 순서가 갈리면 라벨이 다른 층 위에 찍히므로 순서를 명시한다.
        # 합계 레이어는 계열 구분 없이 집계해야 하므로 순서를 물려받지 않는다.
        # 세로형은 첫 계열이 맨 위, 가로형은 첫 계열이 맨 왼쪽에 오는 기본 모양을 유지한다.
        stack_order = {
            "field": "_stack_order",
            "type": "quantitative",
            "sort": "descending" if horizontal else "ascending",
        }
        return {
            "encoding": encoding,
            "layer": [
                {"mark": "bar", "encoding": {"order": stack_order}},
                *_stacked_label_layers(value_axis, horizontal, stack_order),
            ],
        }
    label_mark: dict[str, Any] = {"type": "text", "fontSize": 11}
    if is_bar and horizontal:
        label_mark.update({"dx": 8, "align": "left", "baseline": "middle"})
    elif is_bar:
        label_mark.update({"dy": -8, "baseline": "bottom"})
    else:
        label_mark["dy"] = -8
    return {
        "encoding": encoding,
        "layer": [
            {"mark": mark_map.get(ctype, "bar")},
            {
                "mark": label_mark,
                "encoding": {
                    "text": {"field": "value", "type": "quantitative", "format": ",.2~f"},
                    "color": {"value": "#344054"},
                },
            },
        ],
    }


# 클라이언트가 직접 렌더링할 수 있는 표준 Vega-Lite spec을 만든다.
def build_vega_lite_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    chart = spec["chart"]
    records = spec["data"]["records"]
    if not records or chart["type"] == "table":
        return None

    has_series = any(record.get("series") for record in records)
    x_is_year = _vega_x_is_year(spec)
    is_donut = chart["type"] == "donut"
    is_stacked = chart["type"] == "stacked_bar" and has_series
    stack_order = _stack_order(records) if is_stacked else {}
    positive_total = (
        sum(max(float(record.get("value") or 0), 0) for record in records)
        if is_donut
        else 0
    )
    cumulative = 0.0
    values: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        numeric_value = max(float(record.get("value") or 0), 0)
        value = {
            "x": record.get("x"),
            "value": record.get("value"),
            "series": record.get("series"),
        }
        if is_stacked:
            value["_stack_order"] = stack_order.get(record.get("series"), 0)
        if is_donut:
            value.update({
                "_order": index,
                "_share": numeric_value / positive_total if positive_total > 0 else 0,
                "_mid_angle": (
                    ((cumulative + numeric_value / 2) / positive_total) * tau
                    if positive_total > 0
                    else 0
                ),
                "_legend_label": (
                    f"{record.get('x')}  {_format_number(numeric_value)}"
                ),
            })
            cumulative += numeric_value
        values.append(value)

    category_order = _category_order(records, chart.get("sort_order")) if is_stacked else None
    view = _vega_view(chart, has_series, x_is_year, category_order)
    view["data"] = {"values": values}

    root: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "title": chart["title"],
    }

    delta_records = spec["data"].get("delta_records") or []
    if delta_records:
        unit = chart.get("unit") or "값"
        delta_view = {
            "title": f"전년 대비 증감 ({unit})",
            "data": {"values": [{"x": r["x"], "value": r["value"]} for r in delta_records]},
            "encoding": {
                "x": {"field": "x", "type": "ordinal", "title": ""},
                "y": {"field": "value", "type": "quantitative", "title": unit},
                "color": {
                    "condition": {"test": "datum.value < 0", "value": "#e34948"},
                    "value": "#2a78d6",
                },
            },
            "layer": [
                {"mark": "bar"},
                {
                    "mark": {"type": "text", "fontSize": 11, "dy": -8, "baseline": "bottom"},
                    "encoding": {
                        "text": {"field": "value", "type": "quantitative", "format": ",.2~f"},
                        "color": {"value": "#344054"},
                    },
                },
            ],
        }
        root["vconcat"] = [view, delta_view]
    else:
        root.update(view)
    return root


# 도구 응답에 넣을 요약 문구를 만든다.
def summary_text(spec: dict[str, Any]) -> str:
    chart = spec["chart"]
    if spec.get("vega_lite"):
        return f"{chart['title']} 시각화를 생성했습니다."

    lines = [
        f"{chart['title']} 시각화를 생성하지 못했습니다.",
        f"이유: {chart['reason']}",
    ]
    if spec["warnings"]:
        lines.append("경고: " + " / ".join(spec["warnings"]))
    return "\n".join(lines)
