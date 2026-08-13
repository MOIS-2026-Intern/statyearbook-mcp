"""시각화 명세를 Vega-Lite 형식으로 변환한다."""
from math import tau
from typing import Any


VALUE_FORMAT = ",.2~f"
# 증감 차트는 부호가 곧 정보라 항상 +/- 를 붙여 읽는다.
SIGNED_VALUE_FORMAT = "+,.2~f"
SHARE_FORMAT = ".1%"
LABEL_COLOR = "#344054"
ON_MARK_LABEL_COLOR = "#111827"
LABEL_FONT_SIZE = 11
# 계열마다 mark를 달리 그리는 차트는 색도 계열마다 못 박아 mark·축·라벨을 같은 색으로 묶는다.
COMBO_COLORS = ("#4c78a8", "#f58518", "#54a24b", "#e45756")
# 값 축을 좌우로 나눌 때 축 제목과 mark 색을 맞춰 어느 축이 어느 계열인지 드러낸다.
DUAL_AXIS_COLORS = COMBO_COLORS[:2]
# 증감을 그리는 차트에서 늘어난 값과 줄어든 값을 색으로 가른다.
POSITIVE_COLOR = "#2a78d6"
NEGATIVE_COLOR = "#e34948"
BASELINE_COLOR = "#98a2b3"
# 두 값을 잇는 아령 차트의 연결선은 양 끝 점보다 눈에 덜 띄어야 한다.
GAP_RULE_COLOR = "#cbd5e1"
# 100% 누적 막대에서 이보다 얇은 층은 라벨이 층 밖으로 삐져나온다.
MIN_SHARE_LABEL = 0.05
# 두 시점만 잇는 기울기 차트는 양 끝 라벨이 들어갈 여백이 필요하다.
SLOPE_SCALE_PADDING = 0.45
# 라벨 겹침을 재는 기준이 되는 프론트엔드 기본 차트 높이와 라벨 사이 최소 세로 간격이다.
VIEW_HEIGHT_PX = 340
LABEL_MIN_GAP_PX = 15
# 0 아래로 뻗은 막대의 값 라벨이 눈금 라벨과 겹치지 않도록 증감 축에 남기는 여백이다.
DIVERGING_AXIS_PADDING_PX = 22
# 아령 차트는 점 위아래에 값을 적으므로 그만큼의 여백이 더 필요하다.
GAP_AXIS_PADDING_PX = 26
# 막대 꼭대기의 합계는 층 값보다 눈에 먼저 들어오도록 굵게 쓴다.
TOTAL_LABEL_FONT_WEIGHT = 700
# 세로 막대는 글자 높이에 위아래 여백을 더한 만큼, 가로 막대는 글자 수만큼의 폭이 있어야
# 값이 층 밖으로 삐져나오지 않는다.
STACK_LABEL_MIN_HEIGHT_PX = 18
STACK_LABEL_CHAR_WIDTH_PX = 7
STACK_LABEL_SIDE_PADDING_PX = 12

# 프론트엔드가 차트에 주는 가로 폭. 값 라벨이 들어갈 자리를 이 폭으로 가늠한다.
VIEW_WIDTH_PX = 640
# 값 라벨 한 글자의 대략적인 폭.
LABEL_CHAR_WIDTH_PX = 7
# 라벨이 이웃과 살짝 스치더라도 값이 보이는 편이 낫다. 항목 한 칸보다 이만큼까지 넓어도 그대로
# 적고, 이 선을 넘어야 라벨을 접는다. 정확한 값은 tooltip에 그대로 남는다.
LABEL_OVERLAP_TOLERANCE = 1.15
# 가로 막대는 값을 막대 오른쪽에 적으므로 이만큼 떨어뜨리고, 축 끝에 라벨 자리를 남긴다.
HORIZONTAL_LABEL_DX_PX = 8
MAX_VALUE_HEADROOM = 0.4
# 값을 그대로 라벨로 붙이는 차트. 순위·구성비처럼 라벨 규칙이 따로 있는 차트는 뺀다.
VALUE_LABEL_CHARTS = frozenset({
    "bar", "grouped_bar", "line", "area", "scatter",
    "combo", "paired_panels", "lollipop", "diverging_bar", "waterfall", "dumbbell",
})
# 라벨을 줄일 때 쓰는 큰 수 단위. 큰 단위부터 본다.
COMPACT_UNITS = ((10**12, "조"), (10**8, "억"), (10**4, "만"))
# 부호를 붙여 읽는 증감 차트는 라벨 형식이 달라 줄이지 않고, 자리가 없으면 접기만 한다.
SIGNED_LABEL_CHARTS = frozenset({"diverging_bar", "waterfall"})
# 계열이 여럿이어도 라벨이 가로로 갈라지지 않는 차트. 그룹 막대와 달리 같은 x 위에 겹쳐 놓인다.
STACKED_LABEL_CHARTS = frozenset({"line", "area", "scatter"})


# 범례와 Vega-Lite text mark가 같은 형태의 숫자를 보여주도록 포맷한다.
def _format_number(value: float) -> str:
    if value.is_integer():
        return f"{value:,.0f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


# 값 라벨 하나에 돌아가는 가로 폭을 어림한다. 가로 막대는 범주마다 높이를 늘려 잡고 라벨을
# 막대 오른쪽에 한 줄씩 두므로 폭을 따질 필요가 없다.
def _label_slot_width(chart: dict[str, Any], values: list[dict[str, Any]]) -> float:
    if chart.get("orientation") == "horizontal":
        return float("inf")
    slots = len({value.get("x") for value in values}) or 1
    width = VIEW_WIDTH_PX / slots
    if chart["type"] in {"grouped_bar", "combo"}:
        # 그룹 막대는 범주 한 칸을 계열 수만큼 나눠 쓴다. 콤보는 막대 값과 선 값이 한 칸에서
        # 같은 높이로 만나기 쉬워, 나란히 놓이지 않더라도 같은 자리를 다투는 것으로 본다.
        width /= max(len(values) / slots, 1)
    return width


# 가장 긴 라벨이 주어진 폭 안에 들어가는지 본다. 살짝 넘치는 정도는 들어가는 것으로 본다.
def _labels_fit(labels: list[str], width: float) -> bool:
    if not labels:
        return True
    longest = max(len(label) for label in labels) * LABEL_CHAR_WIDTH_PX
    return longest <= width * LABEL_OVERLAP_TOLERANCE


# 만·억 단위로 줄인 값의 자릿수를 정한다. 세 자리 정도만 남겨 라벨을 짧게 유지한다.
def _scaled_label(scaled: float) -> str:
    if abs(scaled) >= 100:
        return f"{scaled:,.0f}"
    if abs(scaled) >= 10:
        return f"{scaled:,.1f}"
    return f"{scaled:,.2f}"


# 자리가 빠듯할 때 쓸 짧은 라벨을 만든다. 한 눈금은 한 단위만 쓰며, 값 하나라도 그 단위에
# 못 미치면(0.12만처럼) 읽기 어려워지므로 줄이지 않는다.
def _compact_group_labels(numbers: list[float]) -> list[str] | None:
    magnitudes = [abs(number) for number in numbers if number]
    if not magnitudes:
        return None
    for size, name in COMPACT_UNITS:
        if min(magnitudes) >= size:
            return [f"{_scaled_label(number / size)}{name}" for number in numbers]
    return None


# 한 눈금에 놓인 값들의 라벨을 고른다. 값 그대로가 들어가면 그대로 쓰고, 자리가 모자라면
# 만·억 단위로 줄여 본다. 줄여도 넘치면 None을 돌려 그 값들의 라벨을 비운다.
def _fit_group_labels(
    numbers: list[float],
    width: float,
    allow_compact: bool,
) -> tuple[list[str], bool] | None:
    raw = [_format_number(number) for number in numbers]
    if _labels_fit(raw, width):
        return raw, False
    compact = _compact_group_labels(numbers) if allow_compact else None
    if compact and _labels_fit(compact, width):
        return compact, True
    return None


# 값 라벨을 만든다. 계열마다 값 축이 따로인 차트(칸을 나눈 차트·이중 축)는 계열별로 따로 고른다.
# 자릿수가 다른 계열을 한 단위로 묶으면 작은 계열이 0.00에 눌리고, 한 계열이 길다는 이유로
# 나머지 계열의 라벨까지 접히기 때문이다. 한 축을 함께 쓰는 계열은 서로 견줘야 하므로 함께 고른다.
# 자리가 없는 계열은 그 계열만 라벨을 비우고 이름을 돌려준다(값은 tooltip에 그대로 남는다).
def _fit_value_labels(
    values: list[dict[str, Any]],
    width: float,
    chart: dict[str, Any],
) -> tuple[list[str] | None, bool, list[str]]:
    numbers = [float(value.get("value") or 0) for value in values]
    allow_compact = chart["type"] not in SIGNED_LABEL_CHARTS
    groups: dict[Any, list[int]] = {}
    for index, value in enumerate(values):
        key = value.get("series") if chart.get("dual_axis") else None
        groups.setdefault(key, []).append(index)

    labels = [""] * len(values)
    custom = len(groups) > 1
    hidden: list[str] = []
    for key, indexes in groups.items():
        fitted = _fit_group_labels([numbers[index] for index in indexes], width, allow_compact)
        if fitted is None:
            hidden.append(str(key))
            custom = True
            continue
        for index, label in zip(indexes, fitted[0]):
            labels[index] = label
        custom = custom or fitted[1]
    if len(hidden) == len(groups):
        return None, False, hidden
    return labels, custom, hidden


# 계열이 여럿이면 같은 x에 라벨이 겹쳐 놓인다. 값이 비슷한 계열끼리는 세로로도 가까워
# 서로를 가리므로, 값이 큰 쪽을 남기고 가까이 붙는 라벨은 비운다(값은 tooltip에 남는다).
def _blank_overlapping_labels(values: list[dict[str, Any]], labels: list[str]) -> bool:
    top = max((float(value.get("value") or 0) for value in values), default=0)
    if top <= 0:
        return False

    groups: dict[Any, list[int]] = {}
    for index, value in enumerate(values):
        groups.setdefault(value.get("x"), []).append(index)

    blanked = False
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        placed: list[float] = []
        for index in sorted(indexes, key=lambda item: -float(values[item].get("value") or 0)):
            position = VIEW_HEIGHT_PX * (1 - float(values[index].get("value") or 0) / top)
            if any(abs(position - other) < LABEL_MIN_GAP_PX for other in placed):
                labels[index] = ""
                blanked = True
            else:
                placed.append(position)
    return blanked


# 값 라벨의 text 인코딩. 자리가 빠듯하거나 서로 겹치면 서버가 미리 손본 라벨을 그대로 쓴다.
def _value_text(chart: dict[str, Any]) -> dict[str, Any]:
    if chart.get("text_labels"):
        return {"field": "_label", "type": "nominal"}
    return {"field": "value", "type": "quantitative", "format": VALUE_FORMAT}


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


# 레이어마다 쌓는 순서가 갈리면 라벨이 다른 층 위에 찍히므로 순서를 명시한다.
# 세로형은 첫 계열이 맨 위, 가로형은 첫 계열이 맨 왼쪽에 오는 기본 모양을 유지한다.
def _stack_order_encoding(horizontal: bool) -> dict[str, Any]:
    return {
        "field": "_stack_order",
        "type": "quantitative",
        "sort": "descending" if horizontal else "ascending",
    }


# 계열별 쌓는 순서를 정한다. 색상 범례는 계열명 오름차순이라, 첫 계열이 맨 위에 오도록
# 내림차순 순위를 매겨 Vega-Lite 기본 누적 순서와 같은 모양을 유지한다.
def _stack_order(records: list[dict[str, Any]]) -> dict[Any, int]:
    series_names = sorted({
        record.get("series") for record in records if record.get("series") is not None
    }, reverse=True)
    return {name: index for index, name in enumerate(series_names)}


# 범주(또는 연도) 축 인코딩을 만든다. 축 순서는 서버가 정한 순서를 그대로 따른다.
def _category_axis(chart: dict[str, Any], x_is_year: bool) -> dict[str, Any]:
    axis: dict[str, Any] = {
        "field": "x",
        "type": "ordinal" if x_is_year else "nominal",
        "title": chart.get("x_title") or "",
    }
    if chart.get("category_order"):
        axis["sort"] = chart["category_order"]
    return axis


# 값 축 인코딩을 만든다.
def _value_axis(chart: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": "value",
        "type": "quantitative",
        "title": chart.get("y_title") or chart.get("unit") or "값",
    }


# 계열 이름과 단위를 합쳐 값 축 제목을 만든다.
def _series_axis_title(item: dict[str, Any]) -> str:
    unit = item.get("unit")
    return f"{item['label']} ({unit})" if unit else item["label"]


# 값 라벨 text mark를 만든다(막대·점 바깥쪽에 붙인다).
def _label_mark(horizontal: bool, negative: bool = False) -> dict[str, Any]:
    mark: dict[str, Any] = {"type": "text", "fontSize": LABEL_FONT_SIZE}
    if horizontal:
        mark.update({
            "dx": -8 if negative else 8,
            "align": "right" if negative else "left",
            "baseline": "middle",
        })
    else:
        mark.update({"dy": 8 if negative else -8, "baseline": "top" if negative else "bottom"})
    return mark


# 계열 이름을 색으로 나누는 인코딩을 만든다. 계열 순서는 요청한 순서를 그대로 쓴다.
def _series_color(
    labels: list[str],
    colors: tuple[str, ...] | None = None,
    legend: bool = True,
) -> dict[str, Any]:
    color: dict[str, Any] = {"field": "series", "type": "nominal", "title": ""}
    if labels:
        scale: dict[str, Any] = {"domain": labels}
        if colors:
            scale["range"] = list(colors[: len(labels)])
        color["scale"] = scale
    if not legend:
        # 선 끝에 계열 이름을 직접 적는 차트는 범례가 같은 말을 되풀이한다.
        color["legend"] = None
    return color


# 콤보 차트에서 계열 성격에 맞는 mark를 만든다.
def _combo_mark(kind: str) -> dict[str, Any]:
    if kind == "bar":
        return {"type": "bar", "cornerRadiusEnd": 3}
    if kind == "area":
        return {"type": "area", "opacity": 0.55}
    if kind == "point":
        return {"type": "point", "filled": True, "size": 110}
    return {"type": "line", "point": True, "strokeWidth": 2.5}


# 계열을 단위별로 묶는다. 같은 단위 계열은 한 축을 함께 쓰고, 단위가 갈리면 축도 갈린다.
def _unit_groups(series: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in series:
        groups.setdefault(str(item.get("unit") or ""), []).append(item)
    return list(groups.values())


# 축 하나가 맡은 계열들의 제목을 만든다. 여러 계열이 한 축을 쓰면 단위만 적는다.
def _group_axis_title(group: list[dict[str, Any]]) -> str:
    if len(group) == 1:
        return _series_axis_title(group[0])
    return str(group[0].get("unit") or "값")


# 성격이 다른 지표를 한 그래프에 놓을 때 계열마다 mark를 나눠 그린다.
# 계열별 mark와 값 라벨을 한 겹으로 묶어야 라벨이 자기 계열의 축을 따라간다.
def _combo_view(chart: dict[str, Any], x_is_year: bool) -> dict[str, Any]:
    series = chart["series"]
    labels = [item["label"] for item in series]
    colors = {label: COMBO_COLORS[index % len(COMBO_COLORS)] for index, label in enumerate(labels)}
    dual = bool(chart.get("dual_axis"))
    shared_title = chart.get("y_title") or chart.get("unit") or "값"
    # 축을 나눌 때는 같은 단위끼리 한 축에 모은다. 단위가 같은데도 규모 차이로 축을 나누는
    # 경우가 있어, 단위로 갈리지 않으면 계열마다 축을 하나씩 준다.
    groups = _unit_groups(series) if dual else []
    if len(groups) < 2:
        groups = [[item] for item in series]

    layers: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        group_labels = [item["label"] for item in group]
        value_axis: dict[str, Any] = {
            "field": "value",
            "type": "quantitative",
            "title": _group_axis_title(group) if dual else shared_title,
        }
        if dual:
            axis: dict[str, Any] = {"orient": "left" if index == 0 else "right"}
            if len(group) == 1:
                # 축 제목과 mark 색을 맞춰 어느 축이 어느 계열인지 드러낸다.
                axis["titleColor"] = axis["labelColor"] = colors[group_labels[0]]
            value_axis["axis"] = axis
        kind = group[0].get("mark") or ("bar" if index == 0 else "line")
        mark_encoding: dict[str, Any] = {}
        if kind == "bar" and len(group) > 1:
            # 한 축을 나눠 쓰는 막대는 서로 겹치지 않게 옆으로 민다.
            mark_encoding["xOffset"] = {"field": "series", "sort": group_labels}
        # 라벨이 겹쳐 접히는 차트가 있으므로 값은 언제나 tooltip으로도 읽을 수 있어야 한다.
        tooltip = [
            {"field": "x", "type": "ordinal" if x_is_year else "nominal", "title": ""},
            {"field": "series", "type": "nominal", "title": ""},
            {
                "field": "value",
                "type": "quantitative",
                "title": _group_axis_title(group) if dual else shared_title,
                "format": VALUE_FORMAT,
            },
        ]
        marks: list[dict[str, Any]] = [
            {"mark": _combo_mark(kind), "encoding": {**mark_encoding, "tooltip": tooltip}},
        ]
        if chart.get("value_labels", True):
            # 막대 값은 막대 위에, 겹쳐 그린 계열의 값은 점 오른쪽에 둔다.
            # 축을 나누면 두 계열이 같은 높이에 놓이기 쉬워 라벨을 같은 자리에 두면 서로 가린다.
            placement = (
                {"dy": -8, "baseline": "bottom"} if kind == "bar"
                else {"dx": 9, "align": "left", "baseline": "middle"}
            )
            marks.append({
                "mark": {"type": "text", "fontSize": LABEL_FONT_SIZE, **placement},
                "encoding": {
                    **mark_encoding,
                    "text": _value_text(chart),
                },
            })
        layers.append({
            "transform": [{"filter": {"field": "series", "oneOf": group_labels}}],
            "encoding": {
                "y": value_axis,
                "color": _series_color(labels, COMBO_COLORS),
            },
            "layer": marks,
        })

    # 겹쳐 그린 계열의 값 라벨이 점 오른쪽에 붙으므로 축 양 끝에 라벨이 들어갈 자리를 남긴다.
    category_axis = {**_category_axis(chart, x_is_year), "scale": {"paddingOuter": 0.35}}
    view: dict[str, Any] = {"encoding": {"x": category_axis}, "layer": layers}
    if dual:
        view["resolve"] = {"scale": {"y": "independent"}}
    return view


# 늘어난 값과 줄어든 값을 0 기준선 양쪽으로 갈라 그린다.
def _diverging_bar_view(
    chart: dict[str, Any], x_is_year: bool, horizontal: bool,
) -> dict[str, Any]:
    value_channel = "x" if horizontal else "y"
    encoding: dict[str, Any] = {
        "y" if horizontal else "x": _category_axis(chart, x_is_year),
        # 가장 긴 막대의 값 라벨이 눈금 라벨과 겹치지 않도록 축 양 끝에 여백을 둔다.
        value_channel: {**_value_axis(chart), "scale": {"padding": DIVERGING_AXIS_PADDING_PX}},
        "color": {
            "condition": {"test": "datum.value < 0", "value": NEGATIVE_COLOR},
            "value": POSITIVE_COLOR,
        },
    }
    layers: list[dict[str, Any]] = [
        {"mark": {"type": "bar", "cornerRadiusEnd": 3}, "encoding": encoding},
        # 기준선은 범주와 무관하게 축을 가로질러야 해서 범주 인코딩을 물려받지 않는다.
        {
            "mark": {"type": "rule", "color": BASELINE_COLOR, "strokeWidth": 1},
            "encoding": {value_channel: {"datum": 0}},
        },
    ]
    if chart.get("value_labels", True):
        for negative in (False, True):
            layers.append({
                "transform": [{"filter": f"datum.value {'<' if negative else '>='} 0"}],
                "mark": _label_mark(horizontal, negative),
                "encoding": {
                    **encoding,
                    "text": {
                        "field": "value",
                        "type": "quantitative",
                        "format": SIGNED_VALUE_FORMAT,
                    },
                    "color": {"value": LABEL_COLOR},
                },
            })
    return {"layer": layers}


# 증감이 쌓여 마지막 값에 이르는 과정을 단계별 막대로 그린다.
def _waterfall_view(
    chart: dict[str, Any], x_is_year: bool, horizontal: bool,
) -> dict[str, Any]:
    value_channel = "x" if horizontal else "y"
    step_axis = {**_value_axis(chart), "field": "_start"}
    encoding: dict[str, Any] = {
        "y" if horizontal else "x": _category_axis(chart, x_is_year),
        value_channel: step_axis,
        f"{value_channel}2": {"field": "_end"},
        "color": {
            "condition": {"test": "datum.value < 0", "value": NEGATIVE_COLOR},
            "value": POSITIVE_COLOR,
        },
        "tooltip": [
            {"field": "x", "type": "nominal", "title": ""},
            {
                "field": "value",
                "type": "quantitative",
                "title": "증감",
                "format": SIGNED_VALUE_FORMAT,
            },
            {"field": "_end", "type": "quantitative", "title": "누적", "format": VALUE_FORMAT},
        ],
    }
    layers: list[dict[str, Any]] = [{"mark": {"type": "bar"}, "encoding": encoding}]
    if chart.get("value_labels", True):
        # 라벨은 막대의 바깥쪽 끝에 붙여야 줄어든 단계에서도 막대를 가리지 않는다.
        label_encoding = {
            key: value for key, value in encoding.items() if key != f"{value_channel}2"
        }
        layers.append({
            "mark": _label_mark(horizontal),
            "encoding": {
                **label_encoding,
                value_channel: {**step_axis, "field": "_label_at"},
                "text": {
                    "field": "value",
                    "type": "quantitative",
                    "format": SIGNED_VALUE_FORMAT,
                },
                "color": {"value": LABEL_COLOR},
            },
        })
    return {"layer": layers}


# 값 크기를 선과 점으로 표시해 막대보다 가볍게 순위를 비교한다.
def _lollipop_view(
    chart: dict[str, Any], x_is_year: bool, horizontal: bool,
) -> dict[str, Any]:
    value_channel = "x" if horizontal else "y"
    encoding: dict[str, Any] = {
        "y" if horizontal else "x": _category_axis(chart, x_is_year),
        value_channel: _value_axis(chart),
    }
    layers: list[dict[str, Any]] = [
        {
            "mark": {"type": "rule", "strokeWidth": 2, "color": DUAL_AXIS_COLORS[0]},
            "encoding": {**encoding, f"{value_channel}2": {"datum": 0}},
        },
        {
            "mark": {
                "type": "point",
                "filled": True,
                "size": 110,
                "color": DUAL_AXIS_COLORS[0],
            },
            "encoding": encoding,
        },
    ]
    if chart.get("value_labels", True):
        layers.append({
            "mark": _label_mark(horizontal),
            "encoding": {
                **encoding,
                "text": _value_text(chart),
                "color": {"value": LABEL_COLOR},
            },
        })
    return {"layer": layers}


# 막대 길이를 100%로 맞춰 항목마다 구성비만 비교한다.
def _stacked_share_view(
    chart: dict[str, Any],
    x_is_year: bool,
    horizontal: bool,
    stack_order: dict[str, Any],
) -> dict[str, Any]:
    value_channel = "x" if horizontal else "y"
    share_axis: dict[str, Any] = {
        "field": "value",
        "type": "quantitative",
        "title": "구성비",
        "stack": "normalize",
        "axis": {"format": ".0%"},
    }
    encoding: dict[str, Any] = {
        "y" if horizontal else "x": _category_axis(chart, x_is_year),
        value_channel: share_axis,
        "color": {"field": "series", "type": "nominal", "title": ""},
        "tooltip": [
            {"field": "x", "type": "nominal", "title": ""},
            {"field": "series", "type": "nominal", "title": ""},
            {
                "field": "value",
                "type": "quantitative",
                "title": chart.get("unit") or "값",
                "format": VALUE_FORMAT,
            },
            {"field": "_share", "type": "quantitative", "title": "구성비", "format": SHARE_FORMAT},
        ],
    }
    series_order = [item["label"] for item in chart.get("series") or []]
    if series_order:
        encoding["color"]["scale"] = {"domain": series_order}
    return {
        "encoding": encoding,
        "layer": [
            {"mark": "bar", "encoding": {"order": stack_order}},
            {
                # 얇은 층에 라벨을 넣으면 층 밖으로 삐져나오므로 비율이 큰 층만 표시한다.
                "transform": [{"filter": f"datum._share >= {MIN_SHARE_LABEL}"}],
                "mark": {
                    "type": "text",
                    "fontSize": LABEL_FONT_SIZE,
                    "align": "center",
                    "baseline": "middle",
                },
                "encoding": {
                    value_channel: {**share_axis, "bandPosition": 0.5},
                    "order": stack_order,
                    "text": {"field": "_share", "type": "quantitative", "format": SHARE_FORMAT},
                    "color": {"value": ON_MARK_LABEL_COLOR},
                },
            },
        ],
    }


# 두 시점 사이에서 항목마다 값이 어느 방향으로 얼마나 움직였는지 기울기로 보여준다.
def _slope_view(chart: dict[str, Any]) -> dict[str, Any]:
    labels = [item["label"] for item in chart.get("series") or []]
    encoding: dict[str, Any] = {
        # 양 끝 라벨이 잘리지 않도록 point 척도로 안쪽 여백을 준다.
        "x": {
            "field": "x",
            "type": "ordinal",
            "title": "",
            "scale": {"type": "point", "padding": SLOPE_SCALE_PADDING},
        },
        # 기울기 차트가 보여주는 것은 값의 수준이 아니라 움직임이라 축을 0까지 늘리지 않는다.
        "y": {**_value_axis(chart), "scale": {"zero": False}},
        "color": _series_color(labels, legend=False),
        "detail": {"field": "series", "type": "nominal"},
        "tooltip": [
            {"field": "series", "type": "nominal", "title": ""},
            {"field": "x", "type": "ordinal", "title": ""},
            {
                "field": "value",
                "type": "quantitative",
                "title": chart.get("unit") or "값",
                "format": VALUE_FORMAT,
            },
        ],
    }
    layers: list[dict[str, Any]] = [
        {"mark": {"type": "line", "strokeWidth": 2.5}},
        {"mark": {"type": "point", "filled": True, "size": 80}},
    ]
    for edge, align, offset in (("start", "right", -10), ("end", "left", 10)):
        layers.append({
            "transform": [{"filter": f"datum._edge === '{edge}'"}],
            "mark": {
                "type": "text",
                "fontSize": LABEL_FONT_SIZE,
                "align": align,
                "baseline": "middle",
                "dx": offset,
            },
            "encoding": {"text": {"field": "_edge_label", "type": "nominal"}},
        })
    return {"encoding": encoding, "layer": layers}


# 값 자체 대신 순위를 이어 시점마다 자리가 어떻게 바뀌었는지 보여준다.
def _bump_view(chart: dict[str, Any]) -> dict[str, Any]:
    labels = [item["label"] for item in chart.get("series") or []]
    encoding: dict[str, Any] = {
        "x": {"field": "x", "type": "ordinal", "title": "", "scale": {"padding": 0.2}},
        # 1위가 위로 오도록 축을 뒤집고, 없는 순위(0위)가 눈금에 끼지 않도록 범위를 못 박는다.
        "y": {
            "field": "_rank",
            "type": "quantitative",
            "title": "순위",
            "scale": {
                "reverse": True,
                "nice": False,
                "domain": [0.5, (chart.get("rank_count") or 1) + 0.5],
            },
            "axis": {"tickMinStep": 1, "format": "d"},
        },
        "color": _series_color(labels, legend=False),
        "tooltip": [
            {"field": "series", "type": "nominal", "title": ""},
            {"field": "x", "type": "ordinal", "title": ""},
            {"field": "_rank", "type": "quantitative", "title": "순위", "format": "d"},
            {
                "field": "value",
                "type": "quantitative",
                "title": chart.get("unit") or "값",
                "format": VALUE_FORMAT,
            },
        ],
    }
    layers: list[dict[str, Any]] = [
        {"mark": {"type": "line", "strokeWidth": 2.5, "interpolate": "monotone"}},
        {"mark": {"type": "point", "filled": True, "size": 110}},
        {
            "mark": {
                "type": "text",
                "fontSize": LABEL_FONT_SIZE - 1,
                "baseline": "middle",
            },
            "encoding": {
                "text": {"field": "_rank", "type": "quantitative", "format": "d"},
                "color": {"value": "#ffffff"},
            },
        },
        {
            "transform": [{"filter": "datum._edge === 'end'"}],
            "mark": {
                "type": "text",
                "fontSize": LABEL_FONT_SIZE,
                "align": "left",
                "baseline": "middle",
                "dx": 12,
            },
            "encoding": {"text": {"field": "series", "type": "nominal"}},
        },
    ]
    return {"encoding": encoding, "layer": layers}


# 항목마다 두 값을 점으로 찍고 그 사이를 이어 격차를 길이로 보여준다.
def _dumbbell_view(
    chart: dict[str, Any], x_is_year: bool, horizontal: bool,
) -> dict[str, Any]:
    value_channel = "x" if horizontal else "y"
    labels = [item["label"] for item in chart.get("series") or []]
    # 아령 차트가 보여주는 것은 두 값 사이의 폭이라 축을 0까지 늘리지 않는다.
    # 대신 위아래로 붙는 값 라벨이 눈금 라벨과 겹치지 않도록 양 끝에 여백을 둔다.
    value_axis = {
        **_value_axis(chart),
        "scale": {"zero": False, "nice": False, "padding": GAP_AXIS_PADDING_PX},
    }
    category_axis = _category_axis(chart, x_is_year)
    connector: dict[str, Any] = {
        "mark": {"type": "rule", "color": GAP_RULE_COLOR, "strokeWidth": 3},
        "encoding": {
            "y" if horizontal else "x": category_axis,
            value_channel: {**value_axis, "aggregate": "min"},
            f"{value_channel}2": {"field": "value", "aggregate": "max"},
        },
    }
    points: dict[str, Any] = {
        "mark": {"type": "point", "filled": True, "size": 130},
        "encoding": {
            "y" if horizontal else "x": category_axis,
            value_channel: value_axis,
            "color": _series_color(labels, DUAL_AXIS_COLORS) if labels else {
                "field": "series", "type": "nominal", "title": "",
            },
            "tooltip": [
                {"field": "x", "type": "nominal", "title": ""},
                {"field": "series", "type": "nominal", "title": ""},
                {
                    "field": "value",
                    "type": "quantitative",
                    "title": chart.get("unit") or "값",
                    "format": VALUE_FORMAT,
                },
            ],
        },
    }
    layers = [connector, points]
    if chart.get("value_labels", True):
        # 두 점이 가까우면 라벨이 겹치므로 위쪽 값은 위에, 아래쪽 값은 아래에 붙인다.
        for is_top in (True, False):
            layers.append({
                "transform": [{"filter": f"datum._is_top === {str(is_top).lower()}"}],
                "mark": {
                    "type": "text",
                    "fontSize": LABEL_FONT_SIZE,
                    "dy": -12 if is_top else 12,
                    "baseline": "bottom" if is_top else "top",
                },
                "encoding": {
                    **points["encoding"],
                    "text": _value_text(chart),
                    "color": {"value": LABEL_COLOR},
                },
            })
    return {"layer": layers}


# 순서 없는 범주 축에서 단위가 다른 지표를 나눠 그릴 때 한 칸에 주는 높이다.
# 두 칸을 합쳐도 한 장짜리 차트보다 크게 늘어나지 않도록 한 칸을 낮게 잡는다.
PANEL_HEIGHT_PX = 170


# 지표마다 칸을 위아래로 나눠 각자의 값 축에 막대로 그린다.
# 이중 축 콤보와 달리 눈금을 임의로 맞춰 겹치지 않으므로 두 계열이 만나는 자리에 없는 뜻이
# 생기지 않고, 선이 범주 사이를 잇지 않아 흐름으로 오해되지도 않는다. x축은 두 칸이 같은
# 항목 순서를 쓰므로 위아래로 견주는 읽기는 그대로 된다.
def _paired_panels_view(chart: dict[str, Any], x_is_year: bool) -> dict[str, Any]:
    series = chart["series"]
    labels = [item["label"] for item in series]
    panels: list[dict[str, Any]] = []
    for index, item in enumerate(series):
        label = item["label"]
        axis_title = _series_axis_title(item)
        category_axis = _category_axis(chart, x_is_year)
        if index < len(series) - 1:
            # 항목 이름은 맨 아래 칸에만 적는다. 칸마다 되풀이하면 위 칸의 눈금이 아래 칸
            # 막대와 붙어 어느 칸의 축인지 읽기 어려워진다.
            category_axis = {**category_axis, "axis": {"labels": False, "ticks": False, "title": None}}
        tooltip = [
            {"field": "x", "type": "ordinal" if x_is_year else "nominal", "title": ""},
            {"field": "value", "type": "quantitative", "title": axis_title, "format": VALUE_FORMAT},
        ]
        marks: list[dict[str, Any]] = [
            {"mark": {"type": "bar", "cornerRadiusEnd": 3}, "encoding": {"tooltip": tooltip}},
        ]
        if chart.get("value_labels", True):
            marks.append({
                "mark": {"type": "text", "fontSize": LABEL_FONT_SIZE, "dy": -6, "baseline": "bottom"},
                "encoding": {"text": _value_text(chart)},
            })
        panels.append({
            "height": PANEL_HEIGHT_PX,
            "transform": [{"filter": {"field": "series", "oneOf": [label]}}],
            "encoding": {
                "x": category_axis,
                "y": {"field": "value", "type": "quantitative", "title": axis_title},
                "color": {**_series_color(labels, COMBO_COLORS), "legend": None},
            },
            "layer": marks,
        })
    # 칸을 나눠 그린 계열은 축 제목이 곧 계열 이름이라 범례가 같은 말을 되풀이한다.
    return {"vconcat": panels, "spacing": 12}


# 여러 표에서 짝지은 두 지표를 항목 이름과 함께 점으로 그린다.
def _relation_scatter_view(chart: dict[str, Any]) -> dict[str, Any]:
    x_title = chart.get("x_title") or chart.get("x") or ""
    y_title = chart.get("y_title") or chart.get("unit") or "값"
    return {
        "encoding": {
            "x": {
                "field": "x",
                "type": "quantitative",
                "title": x_title,
                "scale": {"zero": False},
            },
            "y": {
                "field": "value",
                "type": "quantitative",
                "title": y_title,
                "scale": {"zero": False},
            },
            "tooltip": [
                {"field": "label", "type": "nominal", "title": ""},
                {"field": "x", "type": "quantitative", "title": x_title, "format": VALUE_FORMAT},
                {"field": "value", "type": "quantitative", "title": y_title, "format": VALUE_FORMAT},
            ],
        },
        "layer": [
            {
                "mark": {
                    "type": "point",
                    "filled": True,
                    "size": 90,
                    "opacity": 0.85,
                    "color": DUAL_AXIS_COLORS[0],
                },
            },
            {
                "mark": {
                    "type": "text",
                    "fontSize": LABEL_FONT_SIZE,
                    "dy": -10,
                    "baseline": "bottom",
                },
                "encoding": {
                    # 겹치는 라벨은 서버가 비워 두므로 값은 tooltip으로 확인한다.
                    "text": {"field": "point_label", "type": "nominal"},
                    "color": {"value": LABEL_COLOR},
                },
            },
        ],
    }


# 내부 차트 타입을 Vega-Lite mark/encoding 뷰로 변환한다.
def _vega_view(chart: dict[str, Any], has_series: bool, x_is_year: bool) -> dict[str, Any]:
    ctype = chart["type"]
    unit = chart.get("unit") or "값"
    # 막대 계열 차트만 방향을 바꾼다. 나머지는 세로 배치가 고정이다.
    horizontal = chart.get("orientation") == "horizontal"

    if ctype == "scatter" and chart.get("point_label"):
        return _relation_scatter_view(chart)
    if ctype == "paired_panels" and chart.get("series"):
        return _paired_panels_view(chart, x_is_year)
    if (ctype == "combo" or chart.get("dual_axis")) and chart.get("series"):
        return _combo_view(chart, x_is_year)
    if ctype == "diverging_bar":
        return _diverging_bar_view(chart, x_is_year, horizontal)
    if ctype == "waterfall":
        return _waterfall_view(chart, x_is_year, horizontal)
    if ctype == "lollipop":
        return _lollipop_view(chart, x_is_year, horizontal)
    if ctype == "stacked_bar_100" and has_series:
        return _stacked_share_view(
            chart, x_is_year, horizontal, _stack_order_encoding(horizontal),
        )
    if ctype == "slope":
        return _slope_view(chart)
    if ctype == "bump":
        return _bump_view(chart)
    if ctype == "dumbbell" and has_series:
        return _dumbbell_view(chart, x_is_year, horizontal)

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
                        "text": _value_text(chart),
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
                        "text": _value_text(chart),
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
    horizontal = is_bar and horizontal
    x_type = "quantitative" if ctype == "scatter" else "ordinal" if x_is_year else "nominal"
    category_axis: dict[str, Any] = {
        "field": "x",
        "type": x_type,
        "title": chart.get("x_title") or "",
    }
    value_axis: dict[str, Any] = {
        "field": "value",
        "type": "quantitative",
        "title": chart.get("y_title") or unit,
    }
    if horizontal and chart.get("value_axis_max"):
        # 0에서 시작하는 축이라 padding 대신 축 끝을 늘려야 막대가 축선에 붙은 채로 자리가 생긴다.
        value_axis["scale"] = {"domainMax": chart["value_axis_max"]}
    if chart.get("category_order"):
        # 서버가 축 순서를 정한 차트는 그 순서를 그대로 domain으로 넘긴다.
        category_axis["sort"] = chart["category_order"]
    encoding: dict[str, Any] = (
        {"x": value_axis, "y": category_axis} if horizontal
        else {"x": category_axis, "y": value_axis}
    )
    if has_series:
        encoding["color"] = {"field": "series", "type": "nominal", "title": ""}
        offset: dict[str, Any] = {"field": "series"}
        # 여러 표를 겹칠 때는 요청한 표 순서가 곧 범례·색 순서다.
        series_order = [item["label"] for item in chart.get("series") or []]
        if series_order:
            encoding["color"]["scale"] = {"domain": series_order}
            offset["sort"] = series_order
        if ctype == "grouped_bar":
            encoding["yOffset" if horizontal else "xOffset"] = offset
    if ctype == "stacked_bar" and has_series:
        # 합계 레이어는 계열 구분 없이 집계해야 하므로 순서를 물려받지 않는다.
        stack_order = _stack_order_encoding(horizontal)
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
    # 라벨이 겹쳐 접히는 차트가 있으므로 값은 언제나 tooltip으로도 읽을 수 있어야 한다.
    tooltip: list[dict[str, Any]] = [
        {"field": "x", "type": x_type, "title": chart.get("x_title") or ""},
        {
            "field": "value",
            "type": "quantitative",
            "title": chart.get("y_title") or unit,
            "format": VALUE_FORMAT,
        },
    ]
    if has_series:
        tooltip.insert(1, {"field": "series", "type": "nominal", "title": ""})
    layers: list[dict[str, Any]] = [
        {"mark": mark_map.get(ctype, "bar"), "encoding": {"tooltip": tooltip}},
    ]
    if chart.get("value_labels", True):
        layers.append({
            "mark": label_mark,
            "encoding": {
                "text": _value_text(chart),
                "color": {"value": "#344054"},
            },
        })
    return {"encoding": encoding, "layer": layers}


# 항목마다 계열이 차지하는 비중을 미리 구한다(Vega-Lite 정규화 축은 라벨 값을 주지 않는다).
def _add_shares(values: list[dict[str, Any]]) -> None:
    totals: dict[Any, float] = {}
    for value in values:
        totals[value["x"]] = totals.get(value["x"], 0.0) + max(float(value["value"] or 0), 0)
    for value in values:
        total = totals.get(value["x"]) or 0.0
        value["_share"] = max(float(value["value"] or 0), 0) / total if total > 0 else 0.0


# 각 단계가 어디서 시작해 어디서 끝나는지 누적해 폭포 차트의 막대 구간을 만든다.
def _add_waterfall_steps(values: list[dict[str, Any]]) -> None:
    running = 0.0
    for value in values:
        value["_start"] = running
        running += float(value["value"] or 0)
        value["_end"] = running
        value["_label_at"] = max(value["_start"], value["_end"])


# 시점마다 값이 큰 계열부터 1위를 매기고, 가장 낮은 순위를 돌려준다.
def _add_ranks(values: list[dict[str, Any]]) -> int:
    groups: dict[Any, list[dict[str, Any]]] = {}
    for value in values:
        groups.setdefault(value["x"], []).append(value)
    for group in groups.values():
        ordered = sorted(group, key=lambda item: float(item["value"] or 0), reverse=True)
        for rank, item in enumerate(ordered, start=1):
            item["_rank"] = rank
    return max((len(group) for group in groups.values()), default=1)


# 항목마다 어느 쪽 값이 위에 놓이는지 표시해 두 라벨을 위아래로 갈라 붙일 수 있게 한다.
def _mark_top_values(values: list[dict[str, Any]]) -> None:
    tops: dict[Any, float] = {}
    for value in values:
        number = float(value["value"] or 0)
        tops[value["x"]] = max(tops.get(value["x"], number), number)
    for value in values:
        value["_is_top"] = float(value["value"] or 0) >= tops[value["x"]]


# 양 끝 시점을 표시해 그 자리에만 계열 이름과 값을 붙일 수 있게 한다.
def _mark_edges(values: list[dict[str, Any]]) -> None:
    positions = list(dict.fromkeys(value["x"] for value in values))
    if not positions:
        return
    first, last = positions[0], positions[-1]
    for value in values:
        value["_edge"] = (
            "start" if value["x"] == first else "end" if value["x"] == last else ""
        )


# 값 범위를 차트 세로 픽셀 위치로 바꾼다(위가 큰 값).
def _slope_label_y(value: float, low: float, high: float) -> float:
    if high <= low:
        return VIEW_HEIGHT_PX / 2
    return VIEW_HEIGHT_PX - (value - low) / (high - low) * VIEW_HEIGHT_PX


# 기울기 차트는 선이 겹쳐 범례로 계열을 찾기 어려우므로 시작점에 이름을 함께 적는다.
# 값이 몰린 구간에서는 라벨이 서로 덮으므로 큰 값부터 남기고 나머지는 비운다(값은 tooltip에 남는다).
def _add_slope_labels(values: list[dict[str, Any]]) -> None:
    _mark_edges(values)
    numbers = [float(value["value"] or 0) for value in values]
    low, high = (min(numbers), max(numbers)) if numbers else (0.0, 0.0)
    for edge in ("start", "end"):
        placed: list[float] = []
        ranked = sorted(
            (value for value in values if value["_edge"] == edge),
            key=lambda item: float(item["value"] or 0),
            reverse=True,
        )
        for value in ranked:
            number = float(value["value"] or 0)
            position = _slope_label_y(number, low, high)
            if any(abs(position - other) < LABEL_MIN_GAP_PX for other in placed):
                value["_edge_label"] = ""
                continue
            placed.append(position)
            text = _format_number(number)
            value["_edge_label"] = (
                f"{value.get('series') or ''} {text}".strip() if edge == "start" else text
            )
    for value in values:
        value.setdefault("_edge_label", "")


# 차트 종류마다 Vega-Lite 식으로는 계산할 수 없는 파생 값을 미리 채우고,
# 축을 세우는 데 필요한 값을 chart에 되돌려 준다.
def _add_derived_fields(chart_type: str, values: list[dict[str, Any]]) -> dict[str, Any]:
    if chart_type == "stacked_bar_100":
        _add_shares(values)
    elif chart_type == "waterfall":
        _add_waterfall_steps(values)
    elif chart_type == "bump":
        rank_count = _add_ranks(values)
        _mark_edges(values)
        return {"rank_count": rank_count}
    elif chart_type == "slope":
        _add_slope_labels(values)
    elif chart_type == "dumbbell":
        _mark_top_values(values)
    return {}


# 클라이언트가 직접 렌더링할 수 있는 표준 Vega-Lite spec을 만든다.
def build_vega_lite_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    chart = spec["chart"]
    records = spec["data"]["records"]
    if not records or chart["type"] == "table":
        return None

    has_series = any(record.get("series") for record in records)
    x_is_year = _vega_x_is_year(spec)
    is_donut = chart["type"] == "donut"
    is_stacked = chart["type"] in {"stacked_bar", "stacked_bar_100"} and has_series
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
        for field in ("label", "point_label"):
            if record.get(field) is not None:
                value[field] = record[field]
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

    # 라벨이 들어갈 자리는 최종 레코드 수와 방향이 정해진 여기서야 알 수 있다. 자리가 모자라면
    # 만·억 단위로 줄여 보고, 그래도 안 들어가면 라벨을 접고 값은 tooltip에 남긴다.
    if values and chart.get("value_labels") is None and chart["type"] in VALUE_LABEL_CHARTS:
        width = _label_slot_width(chart, values)
        labels, custom, hidden = _fit_value_labels(values, width, chart)
        if labels is None:
            chart["value_labels"] = False
            # warnings는 모델이 읽는 자리다. 여기에 '가로 막대로 요청하면'처럼 다시 부를 방법을
            # 적어 두면 모델이 그대로 따라 같은 데이터를 방향만 바꿔 한 번 더 그리고, 사용자
            # 화면에는 같은 차트가 둘 남는다. 일어난 일만 적고 고쳐 부를 방법은 적지 않는다.
            spec.setdefault("warnings", []).append(
                f"항목이 {len({value.get('x') for value in values})}개라 값 라벨이 서로 겹쳐 "
                "숨겼습니다. 값은 차트에 마우스를 올리면 볼 수 있습니다."
            )
        elif hidden:
            spec.setdefault("warnings", []).append(
                f"{', '.join(hidden)} 값은 라벨이 서로 겹쳐 숨겼습니다. "
                "값은 차트에 마우스를 올리면 볼 수 있습니다."
            )
        # 축을 나눈 차트는 계열마다 눈금이 달라 값만으로 라벨 높이를 가늠할 수 없다.
        if labels is not None and chart["type"] in STACKED_LABEL_CHARTS and not chart.get("dual_axis"):
            custom = _blank_overlapping_labels(values, labels) or custom
        if labels is not None and custom:
            chart["text_labels"] = True
            for value, label in zip(values, labels):
                value["_label"] = label

        # 가로 막대의 값은 막대 오른쪽으로 뻗으므로 축 끝에 가장 긴 라벨이 들어갈 자리를 남긴다.
        if chart.get("value_labels") is not False and chart.get("orientation") == "horizontal":
            largest = max((float(value.get("value") or 0) for value in values), default=0)
            if largest > 0:
                texts = [
                    value.get("_label") or _format_number(float(value.get("value") or 0))
                    for value in values
                ]
                reserved = max(len(text) for text in texts) * LABEL_CHAR_WIDTH_PX
                share = min(
                    (reserved + HORIZONTAL_LABEL_DX_PX) / VIEW_WIDTH_PX, MAX_VALUE_HEADROOM,
                )
                chart["value_axis_max"] = largest / (1 - share)

    chart = {**chart, **_add_derived_fields(chart["type"], values)}
    if chart["type"] in {"combo", "paired_panels"} and not chart.get("series"):
        # 한 표 안의 계열을 콤보나 나눈 칸으로 그릴 때는 계열 목록을 레코드에서 세운다.
        chart["series"] = [
            {"label": label, "unit": chart.get("unit")}
            for label in dict.fromkeys(
                record["series"] for record in records if record.get("series")
            )
        ]
    if chart["type"] != "scatter" and not chart.get("category_order"):
        # 축 순서를 두지 않으면 Vega-Lite가 가나다순으로 다시 늘어놓아 표에 실린 순서도,
        # 서버가 값 기준으로 다시 세운 순서도 사라진다. 폭포 차트는 누적까지 어긋난다.
        chart["category_order"] = list(dict.fromkeys(record.get("x") for record in records))
    view = _vega_view(chart, has_series, x_is_year)
    view["data"] = {"values": values}

    root: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "title": chart["title"],
    }

    delta_records = spec["data"].get("delta_records") or []
    if delta_records:
        unit = chart.get("unit") or "값"
        # 보조 증감 차트도 본 차트와 같은 증감 막대 규칙(0 기준선·부호 색)을 따른다.
        delta_view = _diverging_bar_view({"type": "diverging_bar", "unit": unit}, True, False)
        delta_view["title"] = f"전년 대비 증감 ({unit})"
        delta_view["data"] = {
            "values": [{"x": record["x"], "value": record["value"]} for record in delta_records]
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
