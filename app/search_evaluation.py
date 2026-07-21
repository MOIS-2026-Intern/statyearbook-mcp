# -*- coding: utf-8 -*-
"""search_statistics 회귀 질문 세트의 Recall@K를 계산한다."""
from __future__ import annotations

from collections.abc import Callable, Iterable


def evaluate_recall(
    cases: Iterable[dict],
    search: Callable[[str, int | None, int], dict],
    ks: tuple[int, ...] = (1, 3, 5),
) -> dict:
    cases = list(cases)
    if not cases:
        return {f"recall@{k}": 0.0 for k in ks}
    hits = {k: 0 for k in ks}
    details = []
    max_k = max(ks)
    for case in cases:
        response = search(case["query"], case.get("publication_year"), max_k)
        ranked = [row.get("ref_id") for row in response.get("results", [])]
        expected = case["expected_ref_id"]
        rank = ranked.index(expected) + 1 if expected in ranked else None
        for k in ks:
            hits[k] += int(rank is not None and rank <= k)
        details.append({"query": case["query"], "expected_ref_id": expected, "rank": rank})
    return {
        **{f"recall@{k}": round(hits[k] / len(cases), 4) for k in ks},
        "case_count": len(cases),
        "details": details,
    }
