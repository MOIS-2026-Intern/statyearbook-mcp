# 이 파일은 statistics 테이블의 임베딩 대상 조회와 벡터 저장을 담당한다.
# 발간연도 범위와 현재 model profile을 기준으로 증분 대상을 선택한다.
from __future__ import annotations

from admin.backend.models.embedding import EmbeddingBatch, WeightedEmbeddingTexts
from utils.embedding import EmbeddingConfigurationError
from utils.publication_kind import DEFAULT_PUBLICATION_KIND, normalize_publication_kind
from utils.vector import vector_literal


# 통계 제목 벡터는 "그 표가 무엇인가"(제목)와 "어디에 실렸는가"(장·절·세부절)를 각각 임베딩해
# 합성한다. 제목 쪽이 검색을 좌우하고 계층은 제목만으로 뜻이 통하지 않는 표
# (예: 국민디자인과제 아래의 '중앙행정기관', 국민비서 아래의 '알림서비스')를 갈라 주는 보조 신호다.
TITLE_EMBEDDING_WEIGHT = 0.85
HIERARCHY_CONTEXT_WEIGHT = 0.15


# psycopg의 tuple·dict 행 형식 차이 없이 첫 값을 읽는다.
def _first_value(row):
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


class StatisticsEmbeddingRepository:
    # 선택한 발간연도로 모든 조회·갱신 범위를 제한할 저장소를 구성한다.
    def __init__(
        self,
        publication_year: int | None = None,
        publication_kind: str | None = None,
    ):
        self.publication_year = publication_year
        self.publication_kind = (
            normalize_publication_kind(publication_kind or DEFAULT_PUBLICATION_KIND)
            if publication_year is not None
            else None
        )
        self.name = (
            f"statistics:{self.publication_kind}:{publication_year}"
            if publication_year is not None
            else "statistics"
        )

    # 연도 필터 유무에 맞는 안전한 고정 SQL 조건을 반환한다.
    def _scope_sql(self) -> str:
        clauses = []
        if self.publication_year is not None:
            clauses.append("year = %s")
        if self.publication_kind is not None:
            clauses.append(
                "pub_id IN (SELECT pub_id FROM publications WHERE publication_kind = %s)"
            )
        return " AND ".join(clauses) if clauses else "TRUE"

    # 범위 SQL의 연도 자리표시자와 정확히 대응하는 인자를 만든다.
    def _scope_params(self) -> list:
        params = []
        if self.publication_year is not None:
            params.append(self.publication_year)
        if self.publication_kind is not None:
            params.append(self.publication_kind)
        return params

    # PostgreSQL 카탈로그에서 실제 statistics 벡터 열 타입을 조회한다.
    def select_embedding_column_type(self, conn) -> str:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                WHERE a.attrelid = 'statistics'::regclass
                  AND a.attname = 'embedding'
                  AND NOT a.attisdropped
                """
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("statistics.embedding column was not found")
        return str(next(iter(row.values())) if isinstance(row, dict) else row[0])

    # 모델 차원과 DB vector 차원이 다르면 쓰기 전에 구성 오류로 중단한다.
    def select_and_validate_dimension(self, conn, expected_dimension: int) -> None:
        actual_type = self.select_embedding_column_type(conn)
        expected_type = f"vector({expected_dimension})"
        if actual_type != expected_type:
            raise EmbeddingConfigurationError(
                f"statistics.embedding is {actual_type}, but the configured model requires "
                f"{expected_type}; provision the matching database schema before re-embedding"
            )

    # 실행 시작 시점의 최대 통계 ID를 고정해 처리 범위가 늘어나지 않게 한다.
    def select_max_source_id(self, conn) -> int:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(MAX(stat_id), 0) FROM statistics WHERE {self._scope_sql()}",
                self._scope_params(),
            )
            return int(_first_value(cur.fetchone()))

    # 강제 재처리 여부에 맞춰 증분 임베딩 후보 조건을 선택한다.
    def _candidate_sql(self, force: bool) -> str:
        if force:
            return "TRUE"
        return "(embedding IS NULL OR embedding_profile_key IS DISTINCT FROM %s)"

    # 고정된 source ID 범위에서 이번 실행이 처리할 행 수를 계산한다.
    def select_candidate_count(
        self,
        conn,
        profile_key: str,
        force: bool,
        max_source_id: int,
    ) -> int:
        condition = self._candidate_sql(force)
        params = [] if force else [profile_key]
        params.extend(self._scope_params())
        params.append(max_source_id)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM statistics
                WHERE {condition} AND {self._scope_sql()} AND stat_id <= %s
                """,
                params,
            )
            return int(_first_value(cur.fetchone()))

    # ID 커서 방식으로 다음 임베딩 대상 묶음과 새 커서를 반환한다.
    def select_candidate_batch(
        self,
        conn,
        profile_key: str,
        force: bool,
        after_source_id: int,
        max_source_id: int,
        batch_size: int,
    ) -> EmbeddingBatch:
        condition = self._candidate_sql(force)
        params = [] if force else [profile_key]
        params.extend(self._scope_params())
        params.extend([after_source_id, max_source_id, batch_size])
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT stat_id, year,
                       (SELECT publication_kind FROM publications p WHERE p.pub_id = statistics.pub_id)
                           AS publication_kind,
                       ref_id, title_ko, title_en,
                       chapter, section, level3_title, level4_title, page_start
                FROM statistics
                WHERE {condition}
                  AND {self._scope_sql()}
                  AND stat_id > %s
                  AND stat_id <= %s
                ORDER BY stat_id
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
        last_source_id = int(rows[-1]["stat_id"]) if rows else after_source_id
        return EmbeddingBatch(rows=rows, last_source_id=last_source_id)

    # 제목과 상위 계층 문맥을 서로 다른 가중치의 임베딩 입력으로 구성한다.
    def select_embedding_texts(self, rows: list[dict]) -> WeightedEmbeddingTexts:
        return WeightedEmbeddingTexts(groups=(
            (
                TITLE_EMBEDDING_WEIGHT,
                [self._build_title_embedding_text(row) for row in rows],
            ),
            (
                HIERARCHY_CONTEXT_WEIGHT,
                [self._build_hierarchy_context_text(row) for row in rows],
            ),
        ))

    # 비어 있거나 중복된 제목 조각을 제거하되 항상 임베딩 가능한 문자열을 만든다.
    def _join_unique(self, parts: list[str | None]) -> str:
        unique_parts = []
        for part in parts:
            if part and part not in unique_parts:
                unique_parts.append(part)
        return " ".join(unique_parts).strip() or "(제목 없음)"

    # 통계 자체를 가리키는 제목 문구를 만든다.
    # title_ko는 적재할 때 level4_title이 있으면 그 값, 없으면 level3_title로 채워지므로
    # (load_parser의 title_ko = level4_title or level3_title) 이미 가장 깊은 제목이다.
    # level4_title을 따로 넣어도 항상 title_ko와 같은 값이라 기여가 없어 넣지 않는다.
    def _build_title_embedding_text(self, row: dict) -> str:
        return self._join_unique([
            row.get("title_ko"),
            row.get("title_en"),
        ])

    # 장→절→세부절 순서로 통계가 실린 자리를 나타내는 문맥 문구를 만든다.
    # 제목과 같은 조각은 뺀다. level4_title이 없는 통계는 title_ko가 곧 level3_title이라,
    # 빼지 않으면 문맥 그룹이 제목을 한 번 더 넣는 꼴이 되어 계층 신호가 사라진다.
    def _build_hierarchy_context_text(self, row: dict) -> str:
        title = row.get("title_ko")
        return self._join_unique([
            part
            for part in (row.get("chapter"), row.get("section"), row.get("level3_title"))
            if part != title
        ])

    # 벡터와 profile key를 같은 통계 행에 일괄 저장한다.
    def update_embedding_batch(
        self,
        conn,
        rows: list[dict],
        vectors: list[list[float]],
        profile_key: str,
    ) -> None:
        params = [
            (vector_literal(vector), profile_key, row["stat_id"])
            for vector, row in zip(vectors, rows)
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """
                UPDATE statistics
                SET embedding = %s::vector, embedding_profile_key = %s
                WHERE stat_id = %s
                """,
                params,
            )
