from typing import Any


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
            "encoding": {
                "theta": {"field": "value", "type": "quantitative"},
                "color": {"field": "x", "type": "nominal", "title": ""},
            },
            "layer": [
                {"mark": {"type": "arc", "innerRadius": 60}},
                {
                    "mark": {"type": "text", "radius": 90, "fontSize": 11},
                    "encoding": {
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
    x_type = "quantitative" if ctype == "scatter" else "ordinal" if x_is_year else "nominal"
    encoding: dict[str, Any] = {
        "x": {"field": "x", "type": x_type, "title": ""},
        "y": {"field": "value", "type": "quantitative", "title": unit},
    }
    if has_series:
        encoding["color"] = {"field": "series", "type": "nominal", "title": ""}
        if ctype == "grouped_bar":
            encoding["xOffset"] = {"field": "series"}
    label_mark: dict[str, Any] = {"type": "text", "fontSize": 11, "dy": -8}
    if ctype in {"bar", "grouped_bar", "stacked_bar"}:
        label_mark["baseline"] = "bottom"
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
    lines = [
        f"{chart['title']}",
        f"차트: {chart['type']} ({chart['decision_source']})",
        f"선택 이유: {chart['reason']}",
        f"데이터 포인트: {spec['data']['record_count']}개",
    ]
    if spec.get("vega_lite"):
        lines.append("structuredContent.vega_lite에 프론트엔드 렌더링용 Vega-Lite spec이 있습니다.")
    if spec["warnings"]:
        lines.append("경고: " + " / ".join(spec["warnings"]))
    return "\n".join(lines)
