# -*- coding: utf-8 -*-
"""통계 제목 임베딩의 제목 그룹과 계층 문맥 그룹 구성을 검증한다."""
import unittest

from admin.backend.repositories.statistics_embeddings import (
    HIERARCHY_CONTEXT_WEIGHT,
    TITLE_EMBEDDING_WEIGHT,
    StatisticsEmbeddingRepository,
)


# level4_title이 있는 통계. title_ko는 적재 시 level4_title로 채워져 값이 같다.
LEAF_ROW = {
    "title_ko": "중앙행정기관",
    "title_en": "Central Governments",
    "chapter": "행정관리",
    "section": "일반행정",
    "level3_title": "국민디자인과제",
    "level4_title": "중앙행정기관",
}
# level4_title이 없는 통계. 이때 title_ko는 level3_title과 같은 값이다.
LEVEL3_ROW = {
    "title_ko": "온나라시스템 구축 기관",
    "title_en": "Agencies Using Onnara",
    "chapter": "행정관리",
    "section": "일반행정",
    "level3_title": "온나라시스템 구축 기관",
    "level4_title": None,
}


class StatisticsEmbeddingTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = StatisticsEmbeddingRepository()

    # 제목 그룹은 가장 깊은 제목과 영문 제목만 담는다.
    def test_title_group_uses_title_columns(self) -> None:
        self.assertEqual(
            self.repository._build_title_embedding_text(LEAF_ROW),
            "중앙행정기관 Central Governments",
        )

    # level4_title은 언제나 title_ko와 같은 값이라 넣어도 기여가 없으므로 쓰지 않는다.
    def test_title_group_is_unchanged_when_level4_is_missing(self) -> None:
        with_level4 = self.repository._build_title_embedding_text(LEAF_ROW)
        without_level4 = self.repository._build_title_embedding_text(
            {**LEAF_ROW, "level4_title": None}
        )
        self.assertEqual(with_level4, without_level4)

    # 문맥 그룹은 장→절→세부절 순서로 통계가 실린 자리를 담는다.
    def test_context_group_is_ordered_from_chapter_to_leaf(self) -> None:
        self.assertEqual(
            self.repository._build_hierarchy_context_text(LEAF_ROW),
            "행정관리 일반행정 국민디자인과제",
        )

    # level4_title이 없으면 level3_title이 제목과 같으므로 문맥에서 빼야 제목이 되풀이되지 않는다.
    def test_context_group_drops_parts_equal_to_the_title(self) -> None:
        context = self.repository._build_hierarchy_context_text(LEVEL3_ROW)
        self.assertEqual(context, "행정관리 일반행정")
        self.assertNotIn(LEVEL3_ROW["title_ko"], context)

    # 계층이 하나도 남지 않아도 임베딩 가능한 문자열을 돌려줘야 한다.
    def test_context_group_falls_back_when_every_part_matches_the_title(self) -> None:
        row = {
            "title_ko": "정부조직",
            "title_en": None,
            "chapter": "정부조직",
            "section": "정부조직",
            "level3_title": "정부조직",
            "level4_title": None,
        }
        self.assertEqual(
            self.repository._build_hierarchy_context_text(row), "(제목 없음)"
        )

    # 두 그룹의 가중치 합이 1이어야 합성 벡터의 의도한 비율이 유지된다.
    def test_group_weights_sum_to_one(self) -> None:
        self.assertAlmostEqual(
            TITLE_EMBEDDING_WEIGHT + HIERARCHY_CONTEXT_WEIGHT, 1.0
        )
        self.assertGreater(TITLE_EMBEDDING_WEIGHT, HIERARCHY_CONTEXT_WEIGHT)

    # 두 그룹은 행 순서를 유지한 같은 길이의 입력이어야 한다.
    def test_select_embedding_texts_keeps_row_order_in_both_groups(self) -> None:
        rows = [LEAF_ROW, LEVEL3_ROW]
        groups = self.repository.select_embedding_texts(rows).groups

        self.assertEqual(len(groups), 2)
        self.assertEqual([weight for weight, _texts in groups],
                         [TITLE_EMBEDDING_WEIGHT, HIERARCHY_CONTEXT_WEIGHT])
        for _weight, texts in groups:
            self.assertEqual(len(texts), len(rows))
        self.assertTrue(groups[0][1][0].startswith("중앙행정기관"))
        self.assertTrue(groups[0][1][1].startswith("온나라시스템"))


if __name__ == "__main__":
    unittest.main()
