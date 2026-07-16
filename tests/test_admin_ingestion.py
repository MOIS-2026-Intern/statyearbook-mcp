# 이 파일은 관리자 적재 DML, 임베딩 DML, SQLite 작업과 workspace 규칙을 검증한다.
import json
import tempfile
import unittest

from datetime import datetime, timezone
from pathlib import Path

from admin.backend.repositories.admin_job_repository import AdminJobRepository
from admin.backend.repositories.postgres_dml_repository import PostgresDmlRepository
from admin.backend.services.workspace_service import (
    create_workspace_id,
    migrate_legacy_workspaces,
)
from admin.backend.services.title_embedding_dml_service import TitleEmbeddingDmlWriter
from admin.backend.services.yearbook_load_dml_service import build_load_dml
from app.embedding import EmbeddingProfile


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
                "chapter": "일반행정",
                "section": "정부조직",
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
                        "body": {"rows": 1, "cols": 1, "cells": []},
                        "table_md": "| 값 |\n|---|\n|1|",
                    }
                ],
                "footnotes": [],
                "contacts": [],
                "images": [],
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
        self.assertIn("pg_advisory_xact_lock", dml)
        self.assertIn("BEGIN;", dml)
        self.assertTrue(dml.endswith("COMMIT;\n"))

    def test_replace_mode_deletes_only_selected_publication_year(self) -> None:
        dml = build_load_dml(parsed_yearbook(2027), "replace")

        self.assertIn("DELETE FROM publications WHERE year = 2027", dml)
        self.assertNotIn("TRUNCATE", dml)
        self.assertNotIn("year = 2026", dml)


class RecordingDmlRepository(PostgresDmlRepository):
    def __init__(self):
        self.executions = []

    def execute(self, dsn: str, dml: str) -> None:
        self.executions.append((dsn, dml))


class PostgresDmlRepositoryTests(unittest.TestCase):
    def test_execute_file_uses_saved_sql_as_execution_source(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "yearbook_load.sql"
            path.write_text("BEGIN; SELECT 1; COMMIT;\n", encoding="utf-8")
            repository = RecordingDmlRepository()

            repository.execute_file("postgresql:///test", path)

        self.assertEqual(
            repository.executions,
            [("postgresql:///test", "BEGIN; SELECT 1; COMMIT;\n")],
        )


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
        self.assertNotIn("stat_id = 999", dml)
        self.assertIn("[0.6,0.8]", dml)
        self.assertIn("INSERT INTO embedding_jobs", dml)
        self.assertIn("'statistics:2026'", dml)
        self.assertTrue(dml.endswith("COMMIT;\n"))


class AdminJobRepositoryTests(unittest.TestCase):
    def test_persists_progress_events_artifacts_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = AdminJobRepository(Path(root) / "jobs.sqlite3")
            store.create("job-1", {"year": 2026})
            store.update(
                "job-1",
                status="running",
                stage="parse",
                progress=25,
                message="파싱 중",
                artifacts={"parsed_json": "parsed.json"},
                result={"statistics_count": 319},
            )
            store.add_event("job-1", "parse", "통계표 파싱 완료")

            job = store.get("job-1")

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
            repository.create(
                legacy_id,
                {
                    "input_path": str(legacy_workspace / "source.hwpx"),
                    "year": 2026,
                },
            )
            repository.update(
                legacy_id,
                artifacts={"parsed_json": "parsed_yearbook.json"},
            )

            migrated = migrate_legacy_workspaces(root_path, repository)
            new_id = migrated[0][1]
            job = repository.get(new_id)

        self.assertRegex(new_id, r"^\d{8}-\d{6}-\d{6}$")
        self.assertTrue(job["options"]["input_path"].endswith("yearbook_source.hwpx"))
        self.assertEqual(job["artifacts"]["parsed_json"], "yearbook_parsed.json")


if __name__ == "__main__":
    unittest.main()
