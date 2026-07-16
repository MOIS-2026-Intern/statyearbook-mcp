# 이 파일은 ingest, serve, promote를 제공하는 관리자 통합 CLI를 정의한다.
# 모든 명령은 backend service와 repository를 조합해 실행한다.
import argparse
import shutil
import sys

from pathlib import Path

from admin.backend.config import settings
from admin.backend.models.ingestion_job import ARTIFACT_NAMES, IngestionOptions
from admin.backend.repositories.admin_jobs import AdminJobRepository
from admin.backend.services.load_dml import YEARBOOK_LOAD_MODES
from admin.backend.services.load_pipeline import YearbookIngestionService
from admin.backend.services.load_promotion import ProductionPromotionService
from admin.backend.services.load_workspace import create_workspace, migrate_legacy_workspaces


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StatYearbook administrator")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser(
        "ingest",
        help="parse, load, embed and verify with one command",
    )
    ingest.add_argument("hwpx_path")
    ingest.add_argument("--year", type=int, required=True)
    ingest.add_argument("--title", default=None)
    ingest.add_argument("--pub-no", default=None)
    ingest.add_argument("--target", choices=("local", "production"), default="local")
    ingest.add_argument("--mode", choices=YEARBOOK_LOAD_MODES, default="reject")
    ingest.add_argument("--embedding", choices=("bge-m3", "skip"), default="bge-m3")
    ingest.add_argument("--extract-images", action="store_true")
    commands.add_parser("serve", help="run isolated administrator web server")

    promote = commands.add_parser(
        "promote",
        help="apply reviewed SQL artifacts from a completed local job to production",
    )
    promote.add_argument("job_id")
    promote.add_argument("--confirm-year", type=int, required=True)
    return parser


def run_ingestion_command(args) -> int:
    source = Path(args.hwpx_path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"input file not found: {source}")
    job_id, workspace = create_workspace(settings.workspace_dir)
    target = workspace / ARTIFACT_NAMES.source_yearbook
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
    repository = AdminJobRepository(settings.db_path)
    migrate_legacy_workspaces(settings.workspace_dir, repository)
    repository.insert_job(job_id, options.as_dict())
    result = YearbookIngestionService(settings, repository).run(job_id)
    print(f"job={job_id} status={result['status']} progress={result['progress']}%")
    print(result["message"])
    for name, filename in result["artifacts"].items():
        print(f"  {name}: {workspace / filename}")
    if result.get("error"):
        print(result["error"], file=sys.stderr)
    return 0 if result["status"] == "completed" else 1


def run_promotion_command(args) -> int:
    repository = AdminJobRepository(settings.db_path)
    migrate_legacy_workspaces(settings.workspace_dir, repository)
    result = ProductionPromotionService(settings, repository).promote(
        args.job_id,
        args.confirm_year,
    )
    print(
        "production promotion completed: "
        f"job={result['job_id']} year={result['year']}"
    )
    return 0


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        from admin.backend.app import run as run_server

        run_server()
        return
    try:
        status = (
            run_promotion_command(args)
            if args.command == "promote"
            else run_ingestion_command(args)
        )
        raise SystemExit(status)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
