# 이 파일은 임베딩 batch 실행기의 DB 저장 모드와 DML 생성 모드를 검증한다.
import unittest

from utils.embedding import EmbeddingProfile, EmbeddingSettings
from admin.backend.models.embedding import (
    EmbeddingBatch,
    WeightedEmbeddingTexts,
)
from admin.backend.services.load_embedding import EmbeddingRunner


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeProvider:
    def __init__(self):
        self.settings = EmbeddingSettings("local", "unused", 2)
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        return [[float(index), 1.0] for index, _text in enumerate(texts)]


class FakeSource:
    name = "fake-source"

    def __init__(self, count=5):
        self.rows = [
            {"source_id": index, "text": f"row {index}"}
            for index in range(1, count + 1)
        ]
        self.saved = []
        self.validated_dimension = None

    def select_and_validate_dimension(self, _conn, expected_dimension):
        self.validated_dimension = expected_dimension

    def select_max_source_id(self, _conn):
        return self.rows[-1]["source_id"] if self.rows else 0

    def select_candidate_count(self, _conn, _profile_key, _force, _max_source_id):
        return len(self.rows)

    def select_candidate_batch(
        self,
        _conn,
        _profile_key,
        _force,
        after_source_id,
        max_source_id,
        batch_size,
    ):
        rows = [
            row for row in self.rows
            if after_source_id < row["source_id"] <= max_source_id
        ][:batch_size]
        last_id = rows[-1]["source_id"] if rows else after_source_id
        return EmbeddingBatch(rows=rows, last_source_id=last_id)

    def select_embedding_texts(self, rows):
        return [row["text"] for row in rows]

    def update_embedding_batch(self, _conn, rows, vectors, profile_key):
        self.saved.extend(
            (row["source_id"], vector, profile_key)
            for row, vector in zip(rows, vectors)
        )


class FakeJobs:
    def __init__(self):
        self.created = []
        self.progress = []
        self.completed = []
        self.failed = []
        self.locked = False

    def acquire_lock(self, _conn):
        self.locked = True

    def release_lock(self, _conn):
        self.locked = False

    def insert_embedding_profile(self, _conn, profile):
        self.profile = profile

    def insert_embedding_job(self, _conn, *args):
        self.created.append(args)
        return 42

    def update_embedding_job_progress(self, _conn, job_id, processed):
        self.progress.append((job_id, processed))

    def update_embedding_job_completed(self, _conn, job_id, processed):
        self.completed.append((job_id, processed))

    def update_embedding_job_failed(self, _conn, job_id, processed, error):
        self.failed.append((job_id, processed, str(error)))


def profile():
    return EmbeddingProfile(
        profile_key="profile-key",
        provider="local",
        model="BAAI/bge-m3",
        revision="revision",
        dimension=2,
        max_length=512,
        content_version="test-v1",
        normalized=True,
    )


class EmbeddingRunnerTests(unittest.TestCase):
    def test_combines_weighted_embedding_groups_and_normalizes_result(self) -> None:
        provider = FakeProvider()
        runner = EmbeddingRunner(provider, profile(), FakeSource(), FakeJobs())
        provider.encode = lambda texts: (
            [[1.0, 0.0] for _text in texts]
            if texts and texts[0].startswith("leaf")
            else [[0.0, 1.0] for _text in texts]
        )

        vectors = runner._encode_texts(WeightedEmbeddingTexts(groups=(
            (0.7, ["leaf title"]),
            (0.3, ["context title"]),
        )))

        self.assertAlmostEqual(vectors[0][0] / vectors[0][1], 7 / 3)
        self.assertAlmostEqual(sum(value * value for value in vectors[0]), 1.0)

    def test_processes_snapshot_in_reusable_batches_and_tracks_job(self) -> None:
        conn = FakeConnection()
        provider = FakeProvider()
        source = FakeSource(count=5)
        jobs = FakeJobs()
        progress = []
        runner = EmbeddingRunner(provider, profile(), source, jobs)

        result = runner.run(
            conn,
            batch_size=2,
            progress=lambda done, total: progress.append((done, total)),
        )

        self.assertEqual(result.job_id, 42)
        self.assertEqual(result.processed_count, 5)
        self.assertEqual(result.max_source_id, 5)
        self.assertEqual([len(call) for call in provider.calls], [2, 2, 1])
        self.assertEqual(len(source.saved), 5)
        self.assertEqual(jobs.progress, [(42, 2), (42, 4), (42, 5)])
        self.assertEqual(jobs.completed, [(42, 5)])
        self.assertEqual(progress, [(2, 5), (4, 5), (5, 5)])
        self.assertFalse(jobs.locked)

    def test_dml_mode_emits_vectors_without_direct_database_writes(self) -> None:
        conn = FakeConnection()
        provider = FakeProvider()
        source = FakeSource(count=3)
        jobs = FakeJobs()
        emitted = []
        runner = EmbeddingRunner(provider, profile(), source, jobs)

        result = runner.run(
            conn,
            batch_size=2,
            mode="dml",
            on_batch=lambda rows, vectors, _profile: emitted.extend(
                zip(rows, vectors)
            ),
        )

        self.assertIsNone(result.job_id)
        self.assertEqual(result.processed_count, 3)
        self.assertEqual(len(emitted), 3)
        self.assertEqual(source.saved, [])
        self.assertEqual(jobs.created, [])
        self.assertEqual(jobs.progress, [])
        self.assertEqual(jobs.completed, [])
        self.assertEqual(conn.commits, 0)
        self.assertFalse(jobs.locked)

    def test_dry_run_does_not_load_provider_or_create_job(self) -> None:
        conn = FakeConnection()
        provider = FakeProvider()
        source = FakeSource(count=3)
        jobs = FakeJobs()
        runner = EmbeddingRunner(provider, profile(), source, jobs)

        result = runner.run(conn, batch_size=2, dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.target_count, 3)
        self.assertEqual(provider.calls, [])
        self.assertEqual(jobs.created, [])
        self.assertEqual(conn.rollbacks, 1)
        self.assertFalse(jobs.locked)


if __name__ == "__main__":
    unittest.main()
