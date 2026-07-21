import unittest

from app.search_evaluation import evaluate_recall


class SearchEvaluationTests(unittest.TestCase):
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
