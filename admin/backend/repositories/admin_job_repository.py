# 이 파일은 관리자 작업 상태와 단계별 이벤트를 내장 SQLite에 저장한다.
# API 재시작 뒤에도 진행 이력과 산출물 메타데이터를 조회할 수 있게 한다.
from __future__ import annotations

import json
import sqlite3
import threading

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdminJobRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    error TEXT,
                    options_json TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                );
                """
            )

    def create(self, job_id: str, options: dict) -> dict:
        now = utc_now()
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, stage, progress, message, options_json,
                    created_at, updated_at
                ) VALUES (?, 'queued', 'queued', 0, ?, ?, ?, ?)
                """,
                (job_id, "작업 대기 중", json.dumps(options, ensure_ascii=False), now, now),
            )
            conn.execute(
                "INSERT INTO job_events (job_id, level, stage, message, created_at) VALUES (?, 'info', 'queued', ?, ?)",
                (job_id, "작업이 등록되었습니다.", now),
            )
        return self.get(job_id)

    def update(self, job_id: str, **changes) -> dict:
        allowed = {"status", "stage", "progress", "message", "error", "artifacts", "result"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unknown job fields: {sorted(unknown)}")
        columns = []
        values = []
        for key, value in changes.items():
            column = f"{key}_json" if key in {"artifacts", "result"} else key
            columns.append(f"{column} = ?")
            values.append(json.dumps(value, ensure_ascii=False) if key in {"artifacts", "result"} else value)
        columns.append("updated_at = ?")
        values.extend([utc_now(), job_id])
        with self._lock, self._connection() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(columns)} WHERE job_id = ?", values)
        return self.get(job_id)

    def add_event(self, job_id: str, stage: str, message: str, level: str = "info") -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "INSERT INTO job_events (job_id, level, stage, message, created_at) VALUES (?, ?, ?, ?, ?)",
                (job_id, level, stage, message, utc_now()),
            )

    def _decode(self, row: sqlite3.Row) -> dict:
        payload = dict(row)
        for source, target in (
            ("options_json", "options"),
            ("artifacts_json", "artifacts"),
            ("result_json", "result"),
        ):
            payload[target] = json.loads(payload.pop(source) or "{}")
        return payload

    def get(self, job_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            payload = self._decode(row)
            events = conn.execute(
                "SELECT level, stage, message, created_at FROM job_events WHERE job_id = ? ORDER BY event_id",
                (job_id,),
            ).fetchall()
        payload["events"] = [dict(event) for event in events]
        return payload

    def list(self, limit: int = 30) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode(row) for row in rows]

    def migrate_job_identity(
        self,
        old_job_id: str,
        new_job_id: str,
        options: dict,
        artifacts: dict,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET job_id = ?, options_json = ?, artifacts_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    new_job_id,
                    json.dumps(options, ensure_ascii=False),
                    json.dumps(artifacts, ensure_ascii=False),
                    utc_now(),
                    old_job_id,
                ),
            )
            conn.execute(
                "UPDATE job_events SET job_id = ? WHERE job_id = ?",
                (new_job_id, old_job_id),
            )
