# 이 파일은 생성된 제목 벡터를 다시 적용할 수 있는 이관용 DML로 기록한다.
# DB별 ID 대신 연도와 통계표 자연키를 사용해 운영 이관을 지원한다.
from __future__ import annotations

from pathlib import Path

from utils.embedding import EmbeddingProfile
from utils.vector import vector_literal
from admin.backend.sql import sql_literal


class TitleEmbeddingDmlWriter:
    # 이관용 SQL 파일을 열고 사용 profile을 등록하는 트랜잭션 헤더를 쓴다.
    def __init__(self, path: str | Path, profile: EmbeddingProfile):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        self._file = self.path.open("w", encoding="utf-8")
        self._closed = False
        self._write_header()

    # 임베딩 profile을 멱등 등록하는 SQL로 산출물을 시작한다.
    def _write_header(self) -> None:
        profile = self.profile
        values = ", ".join([
            sql_literal(profile.profile_key),
            sql_literal(profile.provider),
            sql_literal(profile.model),
            sql_literal(profile.revision),
            sql_literal(profile.dimension),
            sql_literal(profile.max_length),
            sql_literal(profile.content_version),
            sql_literal(profile.normalized),
        ])
        self._file.write("BEGIN;\n")
        self._file.write(
            "INSERT INTO embedding_profiles "
            "(profile_key, provider, model, revision, dimension, max_length, "
            "content_version, normalized) VALUES ("
            + values
            + ") ON CONFLICT (profile_key) DO NOTHING;\n\n"
        )

    # DB별 ID 대신 통계 자연키 조건으로 제목 벡터 UPDATE 문을 기록한다.
    def write_batch(
        self,
        rows: list[dict],
        vectors: list[list[float]],
        _profile: EmbeddingProfile,
    ) -> None:
        for row, vector in zip(rows, vectors):
            conditions = [
                f"year = {sql_literal(row['year'])}",
                f"ref_id IS NOT DISTINCT FROM {sql_literal(row.get('ref_id'))}",
                f"title_ko = {sql_literal(row['title_ko'])}",
                f"chapter IS NOT DISTINCT FROM {sql_literal(row.get('chapter'))}",
                f"section IS NOT DISTINCT FROM {sql_literal(row.get('section'))}",
                f"level3_title IS NOT DISTINCT FROM {sql_literal(row.get('level3_title'))}",
                f"level4_title IS NOT DISTINCT FROM {sql_literal(row.get('level4_title'))}",
                f"page_start IS NOT DISTINCT FROM {sql_literal(row.get('page_start'))}",
            ]
            self._file.write(
                "UPDATE statistics SET embedding = "
                + sql_literal(vector_literal(vector))
                + "::vector, embedding_profile_key = "
                + sql_literal(self.profile.profile_key)
                + " WHERE "
                + " AND ".join(conditions)
                + ";\n"
            )
        self._file.flush()

    # 선택적으로 완료 이력을 추가하고 트랜잭션을 커밋한 뒤 파일을 닫는다.
    def complete(
        self,
        source_name: str | None = None,
        target_count: int | None = None,
        processed_count: int | None = None,
        max_source_id: int | None = None,
        force: bool = False,
    ) -> None:
        if self._closed:
            return
        if source_name is not None:
            if None in {target_count, processed_count, max_source_id}:
                raise ValueError("embedding job counts are required with source_name")
            values = ", ".join([
                sql_literal(source_name),
                sql_literal(self.profile.profile_key),
                "'completed'",
                sql_literal(force),
                sql_literal(target_count),
                sql_literal(processed_count),
                sql_literal(max_source_id),
                "now()",
            ])
            self._file.write(
                "\nINSERT INTO embedding_jobs "
                "(source_name, profile_key, status, force_reembed, target_count, "
                "processed_count, max_source_id, finished_at) VALUES ("
                + values
                + ");\n"
            )
        self._file.write("COMMIT;\n")
        self._file.close()
        self._closed = True

    # 생성 실패를 rollback SQL과 제한된 주석으로 남기고 writer를 닫는다.
    def abort(self, error: Exception) -> None:
        if self._closed:
            return
        self._file.write(f"\nROLLBACK;\n-- generation failed: {str(error).replace(chr(10), ' ')[:1000]}\n")
        self._file.close()
        self._closed = True


class TableSearchEmbeddingDmlWriter(TitleEmbeddingDmlWriter):
    """DB별 ID 대신 발간연도·ref_id·표 순번·청크 키로 표 벡터를 기록한다."""

    # 발간물·표·청크 자연키를 사용해 표 검색 벡터 UPDATE 문을 기록한다.
    def write_batch(
        self,
        rows: list[dict],
        vectors: list[list[float]],
        _profile: EmbeddingProfile,
    ) -> None:
        for row, vector in zip(rows, vectors):
            conditions = [
                f"s.year = {sql_literal(row['year'])}",
                f"s.ref_id IS NOT DISTINCT FROM {sql_literal(row.get('ref_id'))}",
                f"s.title_ko = {sql_literal(row['title_ko'])}",
                f"t.seq = {sql_literal(row['table_seq'])}",
                f"c.chunk_kind = {sql_literal(row['chunk_kind'])}",
                f"c.chunk_no = {sql_literal(row['chunk_no'])}",
            ]
            self._file.write(
                "UPDATE table_search_chunks c SET embedding = "
                + sql_literal(vector_literal(vector))
                + "::vector, embedding_profile_key = "
                + sql_literal(self.profile.profile_key)
                + " FROM stat_tables t JOIN statistics s ON s.stat_id = t.stat_id"
                + " WHERE c.table_id = t.table_id AND "
                + " AND ".join(conditions)
                + ";\n"
            )
        self._file.flush()
