import json
import unittest

from collections.abc import Callable, Iterable
from pathlib import Path


CASES_PATH = Path(__file__).with_name("fixtures") / "search_statistics_cases.json"


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


class SearchEvaluationTests(unittest.TestCase):
    def test_regression_fixture_has_unique_queries(self) -> None:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

        self.assertTrue(cases)
        self.assertEqual(len(cases), len({case["query"] for case in cases}))

    def test_calculates_recall_at_1_3_5(self) -> None:
        cases = [
            {"query": "첫째", "expected_ref_id": "A"},
            {"query": "둘째", "expected_ref_id": "B"},
        ]

        def search(query, _year, _limit):
            rows = (
                [{"ref_id": "A"}, {"ref_id": "B"}]
                if query == "첫째"
                else [{"ref_id": "X"}, {"ref_id": "Y"}, {"ref_id": "B"}]
            )
            return {"results": rows}

        result = evaluate_recall(cases, search)

        self.assertEqual(result["recall@1"], 0.5)
        self.assertEqual(result["recall@3"], 1.0)
        self.assertEqual(result["recall@5"], 1.0)


if __name__ == "__main__":
    unittest.main()
