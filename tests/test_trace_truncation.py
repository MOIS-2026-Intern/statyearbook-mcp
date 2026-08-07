# -*- coding: utf-8 -*-
"""프런트엔드가 trace에서 읽는 시각화 사양이 크기 한도를 넘겨도 살아남는지 검증한다."""
import unittest

from backend.serializers.mcp_result_serializer import json_dumps, truncate_jsonable
from backend.services.chat_service import _trace_result_for_tool


def _spec() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": "지역별 외국인주민 유형별 구성비",
        "mark": "bar",
        "encoding": {"x": {"field": "x"}, "y": {"field": "value"}},
        "data": {"values": [{"x": "서 울 Seoul", "value": 37734, "series": "외국인근로자"}]},
    }


# 실패한 호출과 같은 모양으로, 사양 옆에 같은 레코드를 여러 번 실은 결과를 만든다.
def _visualize_result(bulk_rows: int = 400) -> dict:
    long_column = "한국국적을 가지지 않은 자 Foreign Residents_외국인근로자 Migrant Workers_소계 Sub Total"
    records = [{long_column: f"{index:,}", "지역 Region": f"행 {index}"} for index in range(bulk_rows)]
    return {
        "content": [{"type": "text", "text": "시각화를 생성했습니다."}],
        "structuredContent": {
            "ok": True,
            "version": "0.1",
            "library": "vega-lite",
            "renderer": "client",
            "stat": {"stat_id": 422, "title_ko": "유형별 지방자치단체 외국인주민"},
            "chart": {"type": "stacked_bar", "unit": "명"},
            "request": {"stat_id": 422, "chart_type": "stacked_bar"},
            "warnings": [],
            "vega_lite": _spec(),
            "data": {
                "record_count": len(records),
                "source_row_count": 18,
                "records": records,
                "table_preview": records,
                "selected_dataset": {"records": records, "provenance": records},
            },
        },
        "isError": False,
    }


def _size(value) -> int:
    return len(json_dumps(value))


class VisualizeTraceResultTests(unittest.TestCase):
    # 사양만 있으면 차트를 그릴 수 있는데, 중복 데이터가 결과를 한도 너머로 밀어낸다.
    def test_drops_the_payload_the_frontend_never_reads(self) -> None:
        result = _visualize_result()

        traced = _trace_result_for_tool("visualize", result)

        structured = traced["structuredContent"]
        self.assertEqual(structured["vega_lite"], _spec())
        self.assertNotIn("records", structured["data"])
        self.assertNotIn("table_preview", structured["data"])
        self.assertNotIn("selected_dataset", structured["data"])
        self.assertLess(_size(traced), _size(result) // 4)

    # 같은 호출의 재시도를 묶는 키라서 request가 빠지면 차트가 중복 표시된다.
    def test_keeps_the_fields_the_frontend_uses(self) -> None:
        traced = _trace_result_for_tool("visualize", _visualize_result())

        structured = traced["structuredContent"]
        for key in ("ok", "stat", "chart", "request", "warnings", "vega_lite"):
            self.assertIn(key, structured)
        self.assertEqual(structured["data"]["record_count"], 400)

    # 실패한 호출은 이유를 그대로 봐야 하므로 손대지 않는다.
    def test_leaves_failed_results_untouched(self) -> None:
        failed = {"structuredContent": {"ok": False, "error": "표를 찾지 못했습니다."}, "isError": True}

        self.assertIs(_trace_result_for_tool("visualize", failed), failed)

    # 다른 도구의 결과까지 줄이면 trace에서 확인할 내용이 사라진다.
    def test_leaves_other_tools_untouched(self) -> None:
        result = _visualize_result()

        self.assertIs(_trace_result_for_tool("search_tables", result), result)


class TruncateJsonableTests(unittest.TestCase):
    # 한도 안에 드는 결과는 그대로 통과해야 한다.
    def test_returns_small_values_unchanged(self) -> None:
        value = {"ok": True, "vega_lite": _spec()}

        self.assertEqual(truncate_jsonable(value, 60_000), value)

    # 통째로 미리보기 문자열로 바꾸면 프런트엔드가 사양을 찾지 못해 차트가 사라진다.
    def test_keeps_the_spec_when_the_result_is_too_large(self) -> None:
        result = _visualize_result()
        self.assertGreater(_size(result), 60_000)

        cut = truncate_jsonable(result, 60_000)

        structured = cut["structuredContent"]
        self.assertEqual(structured["vega_lite"], _spec())
        self.assertEqual(structured["stat"]["stat_id"], 422)
        self.assertLessEqual(_size(cut), 60_000)

    # 어떤 값이 줄었는지 알 수 없으면 잘린 결과를 원본으로 오해한다.
    def test_marks_what_it_dropped(self) -> None:
        cut = truncate_jsonable({"rows": [{"n": index} for index in range(5_000)]}, 2_000)

        self.assertLessEqual(_size(cut), 2_000)
        self.assertTrue(cut["rows"][-1]["truncated"])
        self.assertGreater(cut["rows"][-1]["omitted_items"], 0)

    # 값 하나가 예산을 다 써도 나머지 키는 남아 있어야 한다.
    def test_keeps_every_key_of_an_oversized_mapping(self) -> None:
        value = {"small": "짧은 값", "huge": "가" * 50_000, "flag": True}

        cut = truncate_jsonable(value, 1_000)

        self.assertEqual(sorted(cut), ["flag", "huge", "small"])
        self.assertEqual(cut["small"], "짧은 값")
        self.assertTrue(cut["flag"])
        self.assertLessEqual(_size(cut), 1_000)

    # 길이가 0 이하이면 자르지 않는다는 기존 약속을 유지한다.
    def test_does_not_truncate_without_a_limit(self) -> None:
        value = {"rows": [{"n": index} for index in range(1_000)]}

        self.assertEqual(truncate_jsonable(value, 0), value)


if __name__ == "__main__":
    unittest.main()
