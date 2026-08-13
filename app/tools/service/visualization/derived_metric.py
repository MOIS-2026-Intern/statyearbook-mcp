# -*- coding: utf-8 -*-
"""두 지표를 항목마다 계산해 파생 지표 하나로 만드는 규칙을 모은다.

표 하나에서 고른 두 컬럼이든 서로 다른 두 표에서 고른 두 계열이든, 계산에 필요한 것은
'항목별 값' 두 묶음과 각 묶음의 이름·단위뿐이다. 두 경로가 같은 계산 규칙과 같은 경고
문구를 쓰도록 계산·단위·이름 짓기를 여기에 모은다.

여기에 들어오는 값은 이미 항목마다 하나로 모인 값이어야 한다. 행마다 나눈 뒤 평균을 내면
평균의 평균이 되어 합계끼리 나눈 값과 달라지므로, 부르는 쪽이 먼저 집계하고 나서 넘긴다.
"""
import re
from dataclasses import dataclass, field
from typing import Any

from .table_interpreter import clean_label, normalize_key


# 허용하는 연산이다. 임의 수식은 값이 옳은지 검증할 수 없어 받지 않는다.
DERIVE_OPS = frozenset({"ratio", "per_capita", "share", "difference"})
# 질의에 적힌 '1만 명당' 같은 말에서 배수를 읽는다. 작은 단위가 큰 단위 안에 들어 있어 큰 쪽부터 본다.
PER_SCALE_PATTERNS = (
    (re.compile(r"(?:100만|백만)\s*[가-힣]{0,4}\s*당"), 1_000_000),
    (re.compile(r"(?:10만|십만)\s*[가-힣]{0,4}\s*당"), 100_000),
    (re.compile(r"(?:1만|만)\s*[가-힣]{0,4}\s*당"), 10_000),
    (re.compile(r"(?:1천|천)\s*[가-힣]{0,4}\s*당"), 1_000),
    (re.compile(r"(?:1인|1명|1가구|1세대|한\s*명)\s*당"), 1),
)
# 단위에 이런 배수가 붙은 표는 셀 값이 이미 그만큼 줄어 있어, 배수를 그대로 곱하면 자릿수가 어긋난다.
# 긴 표기가 짧은 표기를 앞머리에 품으므로 긴 쪽부터 본다.
UNIT_MULTIPLIER_WORDS = ("십만", "백만", "천", "만", "억", "조")
# 단위가 '명, 세대'처럼 여러 개인 표에서 컬럼 뜻과 맞는 단위를 고를 실마리다.
UNIT_HINTS = (
    ("세대", ("세대",)),
    ("명", ("인명", "인구", "인원", "사망", "부상", "이재민", "환자", "직원", "정원")),
    ("원", ("재산", "금액", "적립액", "피해액", "예산", "지출", "잔액", "사업비")),
    ("개", ("개소", "건수", "기관", "시설")),
)


# 표에 단위가 여러 개면 컬럼 이름을 보고 그 컬럼의 단위만 남긴다. 좁히지 못하면 부르는 쪽이
# 이미 구해 둔 단위를 그대로 쓴다. 단위를 좁히지 않으면 '명, 세대'를 통째로 물고 들어가
# 파생 단위가 '명, 세대/1 명, 세대'처럼 읽을 수 없는 값이 된다.
def column_unit(column: str, table_unit: str | None, fallback: str) -> str:
    units = [part.strip() for part in str(table_unit or "").split(",") if part.strip()]
    if len(units) <= 1:
        return fallback
    normalized = normalize_key(column)
    for marker, words in UNIT_HINTS:
        if not any(word in normalized for word in words):
            continue
        matched = next((unit for unit in units if marker in unit), None)
        if matched:
            return matched
    return fallback


@dataclass(frozen=True)
class Operand:
    """파생 계산에 넣을 한쪽 지표. 항목 키로 값을 찾을 수 있으면 출처가 표든 계열이든 상관없다."""

    label: str
    unit: str
    values: dict[str, float]
    axis_labels: dict[str, Any] = field(default_factory=dict)
    base_date: str | None = None
    order: list[str] | None = None


@dataclass(frozen=True)
class DerivedResult:
    """계산이 끝난 파생 지표. 값과 함께 무엇을 무엇으로 계산했는지도 들고 있다."""

    label: str
    unit: str
    values: dict[str, float]
    order: list[str]
    axis_labels: dict[str, Any]
    numerator_index: int
    denominator_index: int
    detail: dict[str, Any]


# 도구 인자에 배수가 빠졌을 때 질의에 적힌 '1만 명당'에서 읽어 보완한다.
def query_per_scale(query: str | None) -> int | None:
    text = (query or "").lower()
    return next((scale for pattern, scale in PER_SCALE_PATTERNS if pattern.search(text)), None)


# 배수를 '1만', '10만'처럼 사람이 읽는 표기로 바꾼다.
def per_label(per: int) -> str:
    for size, word in ((100_000_000, "억"), (10_000, "만"), (1_000, "천")):
        if per >= size and per % size == 0:
            return f"{per // size}{word}"
    return f"{per:,}"


# 파생 지표의 단위를 만든다. 분자와 분모의 단위를 이어 붙여 무엇을 무엇으로 나눈 값인지
# 단위만 봐도 드러나게 한다.
def derived_unit(op: str, numerator_unit: str, denominator_unit: str, per: int) -> str:
    if op == "share":
        return "%"
    if op == "difference":
        return numerator_unit or denominator_unit or "값"
    if not numerator_unit or not denominator_unit:
        return "배" if op == "ratio" else "값"
    if op == "ratio":
        return "배" if numerator_unit == denominator_unit else f"{numerator_unit}/{denominator_unit}"
    return f"{numerator_unit}/{per_label(per)} {denominator_unit}"


# 파생 지표의 이름을 만든다.
def derived_label(op: str, numerator: Operand, denominator: Operand, per: int) -> str:
    top, bottom = numerator.label, denominator.label
    if op == "share":
        return f"{bottom} 대비 {top} 비중"
    if op == "difference":
        return f"{top} - {bottom}"
    if op == "ratio":
        return f"{top} / {bottom}"
    return f"{top} ({per_label(per)} {clean_label(denominator.unit) or bottom}당)"


# 값을 못 읽은 항목을 열거하되 너무 길어지지 않게 줄인다.
def _sample_labels(keys: list[str], axis_labels: dict[str, Any]) -> str:
    shown = ", ".join(str(axis_labels.get(key, key)) for key in keys[:5])
    return shown + (f" 외 {len(keys) - 5}개" if len(keys) > 5 else "")


# 파생값의 자릿수나 기준 시점이 흔들릴 수 있는 조건을 미리 알린다.
def _warn_inputs(
    op: str, numerator: Operand, denominator: Operand, warnings: list[str],
) -> None:
    denominator_unit = clean_label(denominator.unit)
    if op != "difference" and denominator_unit:
        multiplier = next(
            (word for word in UNIT_MULTIPLIER_WORDS if denominator_unit.startswith(word)), None,
        )
        if multiplier:
            warnings.append(
                f"분모로 쓴 '{denominator.label}'의 단위가 '{denominator_unit}'이라 표의 수치가 이미 "
                f"{multiplier} 단위로 줄어 있습니다. 파생값의 자릿수가 요청한 기준과 맞는지 확인이 필요합니다."
            )
    top_date = clean_label(numerator.base_date)
    bottom_date = clean_label(denominator.base_date)
    if top_date and bottom_date and top_date != bottom_date:
        warnings.append(
            f"두 표의 기준일이 달라({numerator.label} {top_date}, {denominator.label} {bottom_date}) "
            "파생값은 서로 다른 시점의 수치를 나눈 결과입니다."
        )


# 요청한 연산과 피연산자 번호가 쓸 수 있는 값인지 확인한다.
def _resolve_operands(
    derive: dict[str, Any], operands: list[Operand], warnings: list[str],
) -> tuple[str, int, int] | None:
    op = derive.get("op") or "ratio"
    if op not in DERIVE_OPS:
        warnings.append(f"지원하지 않는 파생 연산 '{op}'이라 계산하지 않고 그대로 그렸습니다.")
        return None

    top_index = 0 if derive.get("numerator") is None else derive["numerator"]
    bottom_index = 1 if derive.get("denominator") is None else derive["denominator"]
    if not (0 <= top_index < len(operands) and 0 <= bottom_index < len(operands)):
        warnings.append(
            "파생 지표가 가리키는 번호가 고른 지표의 범위를 벗어나 계산하지 않고 그대로 그렸습니다."
        )
        return None
    if top_index == bottom_index:
        warnings.append("파생 지표의 분자와 분모가 같은 지표라 계산하지 않고 그대로 그렸습니다.")
        return None

    numerator, denominator = operands[top_index], operands[bottom_index]
    numerator_unit = clean_label(numerator.unit)
    denominator_unit = clean_label(denominator.unit)
    if (
        op == "difference"
        and numerator_unit
        and denominator_unit
        and numerator_unit != denominator_unit
    ):
        warnings.append(
            f"단위가 다른 값({numerator_unit}, {denominator_unit})은 빼도 뜻이 없어 "
            "계산하지 않고 그대로 그렸습니다."
        )
        return None
    return op, top_index, bottom_index


# 두 지표를 항목마다 계산해 파생 지표 하나로 만든다. 계산할 수 없는 요청이면 None을 돌려
# 부르는 쪽이 원래 지표를 그대로 그리게 한다.
def build(
    derive: dict[str, Any],
    operands: list[Operand],
    query: str | None,
    warnings: list[str],
) -> DerivedResult | None:
    resolved = _resolve_operands(derive, operands, warnings)
    if resolved is None:
        return None
    op, top_index, bottom_index = resolved
    numerator, denominator = operands[top_index], operands[bottom_index]

    per = derive.get("per") or query_per_scale(query) or 1
    if per < 1:
        warnings.append("파생 지표의 배수는 1 이상이어야 해 1을 적용했습니다.")
        per = 1
    scale = per if op == "per_capita" else 100 if op == "share" else 1

    values: dict[str, float] = {}
    zero_keys: list[str] = []
    for key, top in numerator.values.items():
        bottom = denominator.values.get(key)
        if bottom is None:
            continue
        if op == "difference":
            values[key] = top - bottom
        elif bottom == 0:
            zero_keys.append(key)
        else:
            values[key] = top / bottom * scale

    axis_labels = {**denominator.axis_labels, **numerator.axis_labels}
    if zero_keys:
        warnings.append(
            f"'{denominator.label}' 값이 0인 항목({_sample_labels(zero_keys, axis_labels)})은 "
            "나눌 수 없어 뺐습니다."
        )
    if not values:
        warnings.append("두 지표에 함께 값이 있는 항목이 없어 파생 지표를 만들지 못했습니다.")
        return None
    _warn_inputs(op, numerator, denominator, warnings)

    order = [key for key in (numerator.order or list(numerator.values)) if key in values]
    unit = derived_unit(op, clean_label(numerator.unit), clean_label(denominator.unit), per)
    return DerivedResult(
        label=clean_label(derive.get("label")) or derived_label(op, numerator, denominator, per),
        unit=unit,
        values=values,
        order=order,
        axis_labels={key: axis_labels.get(key, key) for key in order},
        numerator_index=top_index,
        denominator_index=bottom_index,
        detail={
            "op": op,
            "per": per if op == "per_capita" else None,
            "unit": unit,
            "numerator": {"label": numerator.label, "unit": clean_label(numerator.unit)},
            "denominator": {"label": denominator.label, "unit": clean_label(denominator.unit)},
        },
    )
