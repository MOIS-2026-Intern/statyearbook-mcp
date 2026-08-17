# -*- coding: utf-8 -*-
"""주석이 표 항목과 섞이지 않는 별도 검색 청크로 만들어지는지 검증한다.

주석을 표 항목 청크 문구에 이어 붙이면 주석 검색과 표 항목 검색이 함께 나빠진다.
그래서 청크는 통계 단위로 따로 만들고, 검색 융합에서도 표 항목보다 낮게 잡는다.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from admin.backend.services.load_dml import build_load_dml
from admin.backend.services.table_search_chunks import (
    build_note_search_chunks,
    build_table_search_chunks,
)
from app.tools.service.statistics_search_service import search_statistics_data


STATISTIC = {
    "ref_id": "1-1-5",
    "chapter": "정부조직",
    "section": "정부조직",
    "level3_title": "행정기관 위원회",
    "level4_title": "행정기관 위원회",
    "title_ko": "행정기관 위원회",
    "title_en": "Administration Committees",
    "footnotes": [
        {"seq": 1, "content": "주) 2022년부터 자원봉사자는 조사항목에서 제외"},
        {"seq": 2, "content": "주2) 참여율은 총 성인 인구수 대비 참여 인구수"},
    ],
    "tables": [
        {
            "seq": 1,
            "body": {
                "columns": ["구분", "계"],
                "records": [{"구분": "행정위원회", "계": "40"}],
            },
        },
        {
            "seq": 2,
            "body": {
                "columns": ["구분", "계"],
                "records": [{"구분": "자문위원회", "계": "500"}],
            },
        },
    ],
}


# 검색 융합 입력으로 쓸 표 청크 행을 만든다.
# 같은 통계의 청크는 stat_id를, 다른 통계는 목차 번호와 제목까지 달리해야 중복 제거를 피한다.
def chunk_row(
    chunk_kind: str,
    labels: list[str],
    table_seq: int | None,
    stat_id: int = 8,
) -> dict:
    return {
        "stat_id": stat_id,
        "publication_year": 2025,
        "ref_id": f"1-1-{stat_id}",
        "chapter_no": 1,
        "section_no": 1,
        "level3_no": 5,
        "level4_no": None,
        "chapter": "정부조직",
        "section": "정부조직",
        "level3_title": "행정기관 위원회",
        "level4_title": "행정기관 위원회",
        "title_ko": f"행정기관 위원회 {stat_id}",
        "title_en": "Administration Committees",
        "unit": "개",
        "base_date": "2024.12.31.",
        "page_start": 19,
        "table_seq": table_seq,
        "chunk_kind": chunk_kind,
        "search_labels": labels,
        "search_text": " | ".join(labels),
    }


class NoteSearchChunkTests(unittest.TestCase):
    # 주석 청크는 표 항목과 같은 제목 문맥을 쓰되 주석 문구만 담아야 한다.
    def test_note_chunk_keeps_context_and_only_note_text(self) -> None:
        chunks = build_note_search_chunks(STATISTIC)

        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk["chunk_kind"], "notes")
        self.assertEqual(chunk["chunk_no"], 1)
        self.assertIn("행정기관 위원회", chunk["search_text"])
        self.assertIn("주석: ", chunk["search_text"])
        self.assertIn("자원봉사자는 조사항목에서 제외", chunk["search_text"])
        self.assertNotIn("항목: ", chunk["search_text"])
        self.assertEqual(len(chunk["search_labels"]), 2)

    # 표 항목 청크에는 주석이 섞이지 않아야 기존 벡터를 그대로 쓸 수 있다.
    def test_table_chunks_do_not_contain_notes(self) -> None:
        chunks = build_table_search_chunks(STATISTIC, STATISTIC["tables"][0])

        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertIn(chunk["chunk_kind"], {"headers", "labels"})
            self.assertNotIn("주석", chunk["search_text"])

    # 주석이 없는 통계는 빈 청크 목록을 돌려줘야 한다.
    def test_statistic_without_footnotes_has_no_note_chunk(self) -> None:
        self.assertEqual(build_note_search_chunks({"title_ko": "제목", "footnotes": []}), [])
        self.assertEqual(build_note_search_chunks({"title_ko": "제목"}), [])

    # 주석은 표가 아니라 통계에 달리므로 표가 여러 개여도 한 벌만 적재해야 한다.
    def test_load_dml_inserts_one_note_chunk_per_statistic(self) -> None:
        dml = build_load_dml(
            {
                "publication": {"year": 2025, "title": "2025 행정안전통계연보"},
                "statistics": [STATISTIC],
            }
        )

        note_inserts = [
            line
            for line in dml.splitlines()
            if "INSERT INTO table_search_chunks" in line and "'notes'" in line
        ]
        table_inserts = [
            line
            for line in dml.splitlines()
            if "INSERT INTO table_search_chunks" in line and "'notes'" not in line
        ]
        self.assertEqual(len(note_inserts), 1)
        self.assertIn("v_stat_id, NULL", note_inserts[0])
        self.assertTrue(table_inserts)
        for line in table_inserts:
            self.assertIn("v_stat_id, v_table_id", line)


class NoteSearchRankingTests(unittest.TestCase):
    # 검색 서비스가 두 profile과 질의 임베딩을 실제로 호출하지 않게 감싼다.
    def search(self, lexical_rows: list[dict], vector_rows: list[dict]) -> dict:
        with patch(
            "app.tools.service.statistics_search_service.SEARCH_REPOSITORY.fetch_rows",
            return_value=([], lexical_rows, vector_rows),
        ), patch(
            "app.tools.service.statistics_search_service.embed_query",
            return_value="[0.1,0.2]",
        ), patch(
            "app.tools.service.statistics_search_service.embedding_profile",
            return_value=SimpleNamespace(profile_key="profile-key"),
        ), patch(
            "app.tools.service.statistics_search_service.table_search_embedding_profile",
            return_value=SimpleNamespace(profile_key="table-profile-key"),
        ):
            # 랭킹만 확인하므로 한 발간물로 좁혀 두 발간물의 후보가 섞이지 않게 한다.
            return search_statistics_data(
                "자원봉사자 제외",
                publication_year=2025,
                publication_kind="yearbook",
            )

    # 주석으로만 찾은 통계는 근거가 주석임을 그대로 밝혀야 한다.
    def test_note_match_is_reported_as_footnote(self) -> None:
        note_row = chunk_row("notes", ["주) 2022년부터 자원봉사자는 조사항목에서 제외"], None)

        response = self.search([note_row], [])

        self.assertEqual(response["count"], 1)
        result = response["results"][0]
        self.assertEqual(result["matched_source"], "footnote")
        self.assertIn("자원봉사자", result["matched_text"])
        self.assertIsNone(result["table_seq"])

    # 같은 순위라면 주석보다 표 항목이 더 직접적인 근거이므로 점수가 높아야 한다.
    def test_table_label_outscores_note_at_the_same_rank(self) -> None:
        label_row = chunk_row("labels", ["자원봉사자"], 1)
        note_row = chunk_row("notes", ["자원봉사자"], None, stat_id=9)

        response = self.search([label_row, note_row], [])

        scores = {result["stat_id"]: result["score"] for result in response["results"]}
        self.assertGreater(scores[8], scores[9])

    # 표 항목과 주석이 함께 맞은 통계는 한쪽만 맞은 통계보다 높아야 한다.
    def test_label_and_note_evidence_add_up(self) -> None:
        label_row = chunk_row("labels", ["자원봉사자"], 1)
        note_row = chunk_row("notes", ["자원봉사자 제외"], None)
        other_row = chunk_row("labels", ["자원봉사자"], 1, stat_id=9)

        both = self.search([label_row, note_row], [])
        single = self.search([other_row], [])

        both_score = next(r["score"] for r in both["results"] if r["stat_id"] == 8)
        self.assertGreater(both_score, single["results"][0]["score"])


if __name__ == "__main__":
    unittest.main()
