# 이 파일은 생성된 제목 벡터를 다시 적용할 수 있는 이관용 DML로 기록한다.
# DB별 ID 대신 연도와 통계표 자연키를 사용해 운영 이관을 지원한다.
from __future__ import annotations

from pathlib import Path

from app.embedding import EmbeddingProfile
from app.vector import vector_literal
from admin.backend.services.load_dml import sql_literal


class TitleEmbeddingDmlWriter:
    def __init__(self, path: str | Path, profile: EmbeddingProfile):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        self._file = self.path.open("w", encoding="utf-8")
        self._closed = False
        self._write_header()

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

    def abort(self, error: Exception) -> None:
        if self._closed:
            return
        self._file.write(f"\nROLLBACK;\n-- generation failed: {str(error).replace(chr(10), ' ')[:1000]}\n")
        self._file.close()
        self._closed = True
