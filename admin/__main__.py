# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import shutil
import sys
import uuid

from pathlib import Path

from admin.config import settings
from admin.job_store import AdminJobStore
from admin.main import run as run_server
from admin.pipeline import AdminIngestionService, IngestionOptions
from load.yearbook_dml import LOAD_MODES, execute_dml


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StatYearbook administrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="parse, load, embed and verify with one command")
    ingest.add_argument("hwpx_path")
    ingest.add_argument("--year", type=int, required=True)
    ingest.add_argument("--title", default=None)
    ingest.add_argument("--pub-no", default=None)
    ingest.add_argument("--target", choices=("local", "production"), default="local")
    ingest.add_argument("--mode", choices=LOAD_MODES, default="reject")
    ingest.add_argument("--embedding", choices=("bge-m3", "skip"), default="bge-m3")
    ingest.add_argument("--extract-images", action="store_true")
    subparsers.add_parser("serve", help="run isolated administrator web server")
    promote = subparsers.add_parser(
        "promote",
        help="apply reviewed SQL artifacts from a completed local job to production",
    )
    promote.add_argument("job_id")
    promote.add_argument("--confirm-year", type=int, required=True)
    return parser


def ingest(args) -> int:
    source = Path(args.hwpx_path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"input file not found: {source}")
    job_id = uuid.uuid4().hex
    workspace = settings.workspace_dir / job_id
    workspace.mkdir(parents=True)
    target = workspace / "source.hwpx"
    shutil.copy2(source, target)
    options = IngestionOptions(
        input_path=str(target),
        original_filename=source.name,
        year=args.year,
        title=args.title or f"{args.year} 행정안전통계연보",
        pub_no=args.pub_no,
        target=args.target,
        load_mode=args.mode,
        embedding_model=args.embedding,
        extract_images=args.extract_images,
    )
    store = AdminJobStore(settings.db_path)
    store.create(job_id, options.as_dict())
    result = AdminIngestionService(settings, store).run(job_id)
    print(f"job={job_id} status={result['status']} progress={result['progress']}%")
    print(result["message"])
    for name, filename in result["artifacts"].items():
        print(f"  {name}: {workspace / filename}")
    if result.get("error"):
        print(result["error"], file=sys.stderr)
    return 0 if result["status"] == "completed" else 1


def promote(args) -> int:
    store = AdminJobStore(settings.db_path)
    try:
        job = store.get(args.job_id)
    except KeyError as exc:
        raise RuntimeError(f"job not found: {args.job_id}") from exc
    if job["status"] != "completed":
        raise RuntimeError("only a completed job can be promoted")
    year = int(job["options"]["year"])
    if args.confirm_year != year:
        raise RuntimeError(f"--confirm-year must be {year}")
    dsn = settings.target_dsn("production")
    workspace = settings.workspace_dir / args.job_id
    load_sql = workspace / job["artifacts"]["load_dml"]
    embedding_name = job["artifacts"].get("embedding_dml")
    execute_dml(dsn, load_sql.read_text(encoding="utf-8"))
    if embedding_name:
        execute_dml(dsn, (workspace / embedding_name).read_text(encoding="utf-8"))
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*), COUNT(embedding) FROM statistics WHERE year = %s",
            (year,),
        )
        statistics_count, embedding_count = cur.fetchone()
    expected_statistics = int(job["result"].get("statistics_count", statistics_count))
    expected_embeddings = int(
        job["result"].get("verified_embedding_count", embedding_count)
    )
    if statistics_count != expected_statistics or embedding_count != expected_embeddings:
        raise RuntimeError(
            "production verification failed: "
            f"statistics={statistics_count}/{expected_statistics}, "
            f"embeddings={embedding_count}/{expected_embeddings}"
        )
    store.add_event(
        args.job_id,
        "production",
        f"운영 DB 적용 완료: statistics={statistics_count}, embeddings={embedding_count}",
    )
    print(f"production promotion completed: job={args.job_id} year={year}")
    return 0


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        run_server()
        return
    try:
        if args.command == "promote":
            raise SystemExit(promote(args))
        raise SystemExit(ingest(args))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
