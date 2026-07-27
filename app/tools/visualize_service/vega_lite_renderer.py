from math import tau
from typing import Any


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


# 내부 차트 타입을 Vega-Lite mark/encoding 뷰로 변환한다.
def _vega_view(chart: dict[str, Any], has_series: bool, x_is_year: bool) -> dict[str, Any]:
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
    category_axis = {"field": "x", "type": x_type, "title": ""}
    value_axis = {"field": "value", "type": "quantitative", "title": unit}
    encoding: dict[str, Any] = (
        {"x": value_axis, "y": category_axis} if horizontal
        else {"x": category_axis, "y": value_axis}
    )
    if has_series:
        encoding["color"] = {"field": "series", "type": "nominal", "title": ""}
        if ctype == "grouped_bar":
            encoding["yOffset" if horizontal else "xOffset"] = {"field": "series"}
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

    view = _vega_view(chart, has_series, x_is_year)
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
