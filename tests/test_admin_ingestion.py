# 이 파일은 관리자 적재 DML, 임베딩 DML, SQLite 작업과 workspace 규칙을 검증한다.
import json
import tempfile
import unittest
import zipfile

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from admin.backend.config import AdminSettings
from admin.backend.models.ingestion_job import IngestionOptions
from admin.backend.repositories.admin_jobs import AdminJobRepository
from admin.backend.repositories.postgres_dml import PostgresDmlRepository
from admin.backend.services.load_pipeline import YearbookIngestionService
from admin.backend.services.load_verification import YearbookVerificationService
from admin.backend.services.load_workspace import (
    create_workspace_id,
    migrate_legacy_workspaces,
)
from admin.backend.services.load_dml import build_load_dml
from admin.backend.services.load_embedding_dml import (
    TableSearchEmbeddingDmlWriter,
    TitleEmbeddingDmlWriter,
)
from utils.embedding import EmbeddingProfile


def parsed_yearbook(year: int = 2026) -> dict:
    return {
        "publication": {
            "year": year,
            "pub_no": "TEST-1",
            "title": f"{year} 행정안전통계연보",
            "page_count": 10,
        },
        "statistics": [
            {
                "ref_id": "1-1-1",
                "chapter_no": 1,
                "section_no": 1,
                "level3_no": 1,
                "level4_no": None,
                "chapter": "일반행정",
                "section": "정부조직",
                "level3_title": "행정기관 위원회",
                "level4_title": "행정기관 위원회",
                "title_ko": "행정기관 위원회",
                "title_en": "Administration Committees",
                "unit": "개",
                "base_date": "2025.12.31.",
                "page_start": 3,
                "tables": [
                    {
                        "seq": 1,
                        "caption": None,
                        "n_rows": 1,
                        "n_cols": 1,
                        "body": {
                            "rows": 2,
                            "cols": 2,
                            "cells": [],
                            "columns": ["연도 Year", "사망신고 건수"],
                            "records": [{"연도 Year": "2024", "사망신고 건수": "10"}],
                        },
                        "table_md": "| 값 |\n|---|\n|1|",
                    }
                ],
                "footnotes": [],
                "contacts": [],
            }
        ],
    }


class YearbookDmlTests(unittest.TestCase):
    def test_reject_mode_generates_cumulative_portable_dml(self) -> None:
        dml = build_load_dml(parsed_yearbook(), "reject")

        self.assertNotIn("TRUNCATE", dml)
        self.assertNotIn("pub_id, year, pub_no", dml)
        self.assertIn("publication year 2026 already exists", dml)
        self.assertIn("RETURNING pub_id INTO v_pub_id", dml)
        self.assertIn("RETURNING stat_id INTO v_stat_id", dml)
        self.assertIn("RETURNING table_id INTO v_table_id", dml)
        self.assertIn("INSERT INTO table_search_chunks", dml)
        self.assertIn("사망신고 건수", dml)
        self.assertIn("level3_no, level4_no", dml)
        self.assertIn("level3_title, level4_title", dml)
        self.assertNotIn("statistic_images", dml)
        self.assertIn("pg_advisory_xact_lock", dml)
        self.assertIn("BEGIN;", dml)
        self.assertTrue(dml.endswith("COMMIT;\n"))

    def test_replace_mode_deletes_only_selected_publication_year(self) -> None:
        dml = build_load_dml(parsed_yearbook(2027), "replace")

        self.assertIn("DELETE FROM publications WHERE year = 2027", dml)
        self.assertNotIn("TRUNCATE", dml)
        self.assertNotIn("year = 2026", dml)


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return None

    def execute(self, sql, _params=None):
        self.connection.attempted_sql.append(sql)
        self.connection.pending_sql.append(sql)


class RecordingTransactionConnection:
    def __init__(self):
        self.attempted_sql = []
        self.pending_sql = []
        self.committed_sql = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commits += 1
        self.committed_sql.extend(self.pending_sql)
        self.pending_sql.clear()

    def rollback(self):
        self.rollbacks += 1
        self.pending_sql.clear()

    def close(self):
        self.closed = True


class FailingVerification:
    def __init__(self):
        self.connection = None

    def verify_connection(self, conn, _year, _profile_key, _table_profile_key):
        self.connection = conn
        raise RuntimeError("verification failed after load")


class PostgresDmlRepositoryTests(unittest.TestCase):
    def test_execute_dml_file_uses_only_saved_transaction_body(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "yearbook_load.sql"
            path.write_text("BEGIN;\nSELECT 1;\nCOMMIT;\n", encoding="utf-8")
            repository = PostgresDmlRepository()
            connection = RecordingTransactionConnection()

            repository.execute_dml_file(connection, path)

        self.assertEqual(connection.attempted_sql, ["SELECT 1;\n"])

    def test_transaction_commits_exactly_once_after_success(self) -> None:
        connection = RecordingTransactionConnection()
        repository = PostgresDmlRepository()

        with patch(
            "admin.backend.repositories.postgres_dml.psycopg.connect",
            return_value=connection,
        ):
            with repository.transaction("postgresql:///test") as active_connection:
                self.assertIs(active_connection, connection)

        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertTrue(connection.closed)

    def test_execute_dml_file_rejects_missing_exact_transaction_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "invalid.sql"
            path.write_text("SELECT 1;\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "exact outer"):
                PostgresDmlRepository().execute_dml_file(
                    RecordingTransactionConnection(),
                    path,
                )


class AtomicIngestionTests(unittest.TestCase):
    def test_verification_failure_rolls_back_load_without_commit(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            workspace_dir = root_path / "workspaces"
            job_id = "job-atomic-rollback"
            workspace = workspace_dir / job_id
            workspace.mkdir(parents=True)
            input_path = workspace / "yearbook_source.hwpx"
            with zipfile.ZipFile(input_path, "w") as archive:
                archive.writestr("Contents/content.hpf", "test")

            store = AdminJobRepository(root_path / "state" / "jobs.sqlite3")
            options = IngestionOptions(
                input_path=str(input_path),
                original_filename="yearbook.hwpx",
                year=2026,
                title="2026 행정안전통계연보",
                target="local",
                embedding_model="skip",
            )
            store.insert_job(job_id, options.as_dict())
            settings = AdminSettings(
                profile="test",
                state_dir=root_path / "state",
                workspace_dir=workspace_dir,
                dsn="postgresql:///test",
            )
            connection = RecordingTransactionConnection()
            verification = FailingVerification()
            service = YearbookIngestionService(
                settings,
                store,
                verification=verification,
                dml_repository=PostgresDmlRepository(),
            )

            with (
                patch(
                    "admin.backend.repositories.postgres_dml.psycopg.connect",
                    return_value=connection,
                ),
                patch(
                    "admin.backend.services.load_pipeline.parse",
                    return_value=parsed_yearbook(),
                ),
            ):
                result = service.run(job_id)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "verify")
        self.assertIn("verification failed after load", result["error"])
        self.assertIs(verification.connection, connection)
        self.assertTrue(any("INSERT INTO publications" in sql for sql in connection.attempted_sql))
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)
        self.assertEqual(connection.committed_sql, [])
        self.assertEqual(connection.pending_sql, [])
        self.assertTrue(connection.closed)


class VerificationServiceTests(unittest.TestCase):
    def test_verifies_counts_from_shared_dict_row_connection(self) -> None:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            {"statistics_count": 2, "table_count": 3},
            {"count": 2},
            {"count": 4},
            {"count": 4},
        ]
        connection = MagicMock()
        connection.cursor.return_value = cursor

        result = YearbookVerificationService().verify_connection(
            connection,
            2026,
            "title-profile",
            "table-profile",
        )

        self.assertEqual(result["statistics_count"], 2)
        self.assertEqual(result["table_count"], 3)
        self.assertEqual(result["verified_embedding_count"], 2)
        self.assertEqual(result["verified_table_embedding_count"], 4)
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()


class EmbeddingDmlTests(unittest.TestCase):
    def test_embedding_dml_uses_portable_natural_key(self) -> None:
        profile = EmbeddingProfile(
            profile_key="profile-key",
            provider="local",
            model="BAAI/bge-m3",
            revision="revision",
            dimension=2,
            max_length=512,
            content_version="statistics-title-v1",
            normalized=True,
        )
        row = {
            "stat_id": 999,
            "year": 2026,
            "ref_id": "1-1-1",
            "title_ko": "행정기관 위원회",
            "chapter": "일반행정",
            "section": "정부조직",
            "level3_title": "행정기관 위원회",
            "level4_title": "행정기관 위원회",
            "page_start": 3,
        }
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "yearbook_title_embeddings.sql"
            writer = TitleEmbeddingDmlWriter(path, profile)
            writer.write_batch([row], [[0.6, 0.8]], profile)
            writer.complete(
                source_name="statistics:2026",
                target_count=1,
                processed_count=1,
                max_source_id=999,
            )
            dml = path.read_text(encoding="utf-8")

        self.assertIn("year = 2026", dml)
        self.assertIn("ref_id IS NOT DISTINCT FROM '1-1-1'", dml)
        self.assertIn("level3_title IS NOT DISTINCT FROM '행정기관 위원회'", dml)
        self.assertIn("level4_title IS NOT DISTINCT FROM '행정기관 위원회'", dml)
        self.assertNotIn("stat_id = 999", dml)
        self.assertIn("[0.6,0.8]", dml)
        self.assertIn("INSERT INTO embedding_jobs", dml)
        self.assertIn("'statistics:2026'", dml)
        self.assertTrue(dml.endswith("COMMIT;\n"))

    def test_table_embedding_dml_uses_portable_table_chunk_key(self) -> None:
        profile = EmbeddingProfile(
            profile_key="table-profile",
            provider="local",
            model="BAAI/bge-m3",
            revision="revision",
            dimension=2,
            max_length=512,
            content_version="table-search-v1",
            normalized=True,
        )
        row = {
            "chunk_id": 777,
            "year": 2026,
            "ref_id": "2-1-1-5",
            "title_ko": "안심상속 원스톱서비스",
            "table_seq": 1,
            "chunk_kind": "headers",
            "chunk_no": 1,
        }
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "yearbook_table_search_embeddings.sql"
            writer = TableSearchEmbeddingDmlWriter(path, profile)
            writer.write_batch([row], [[0.6, 0.8]], profile)
            writer.complete(
                source_name="table_search:2026",
                target_count=1,
                processed_count=1,
                max_source_id=777,
            )
            dml = path.read_text(encoding="utf-8")

        self.assertIn("UPDATE table_search_chunks c", dml)
        self.assertIn("s.ref_id IS NOT DISTINCT FROM '2-1-1-5'", dml)
        self.assertIn("c.chunk_kind = 'headers'", dml)
        self.assertNotIn("chunk_id = 777", dml)
        self.assertIn("'table_search:2026'", dml)


class AdminJobRepositoryTests(unittest.TestCase):
    def test_persists_progress_events_artifacts_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = AdminJobRepository(Path(root) / "jobs.sqlite3")
            store.insert_job("job-1", {"year": 2026})
            store.update_job(
                "job-1",
                status="running",
                stage="parse",
                progress=25,
                message="파싱 중",
                artifacts={"parsed_json": "parsed.json"},
                result={"statistics_count": 319},
            )
            store.insert_event("job-1", "parse", "통계표 파싱 완료")

            job = store.select_job("job-1")

        self.assertEqual(job["progress"], 25)
        self.assertEqual(job["artifacts"]["parsed_json"], "parsed.json")
        self.assertEqual(job["result"]["statistics_count"], 319)
        self.assertEqual(job["events"][-1]["message"], "통계표 파싱 완료")


class WorkspaceServiceTests(unittest.TestCase):
    def test_workspace_id_contains_date_time_and_microseconds(self) -> None:
        timestamp = datetime(2026, 7, 16, 17, 5, 9, 123456, tzinfo=timezone.utc)

        workspace_id = create_workspace_id(timestamp)

        self.assertEqual(workspace_id, "20260716-170509-123456")

    def test_migrates_legacy_workspace_id_paths_and_artifact_names(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            repository = AdminJobRepository(root_path / "jobs.sqlite3")
            legacy_id = "a" * 32
            legacy_workspace = root_path / legacy_id
            legacy_workspace.mkdir()
            (legacy_workspace / "source.hwpx").write_bytes(b"test")
            (legacy_workspace / "parsed_yearbook.json").write_text(
                json.dumps({"metadata": {"source": "old"}}),
                encoding="utf-8",
            )
            repository.insert_job(
                legacy_id,
                {
                    "input_path": str(legacy_workspace / "source.hwpx"),
                    "year": 2026,
                },
            )
            repository.update_job(
                legacy_id,
                artifacts={"parsed_json": "parsed_yearbook.json"},
            )

            migrated = migrate_legacy_workspaces(root_path, repository)
            new_id = migrated[0][1]
            job = repository.select_job(new_id)

        self.assertRegex(new_id, r"^\d{8}-\d{6}-\d{6}$")
        self.assertTrue(job["options"]["input_path"].endswith("yearbook_source.hwpx"))
        self.assertEqual(job["artifacts"]["parsed_json"], "yearbook_parsed.json")


if __name__ == "__main__":
    unittest.main()
