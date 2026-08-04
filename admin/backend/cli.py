# 이 파일은 ingest와 serve를 제공하는 관리자 통합 CLI를 정의한다.
# 모든 명령은 backend service와 repository를 조합해 실행한다.
import argparse
import shutil
import sys

from pathlib import Path

from admin.backend.config import settings
from admin.backend.models.ingestion_job import ARTIFACT_NAMES, IngestionOptions
from admin.backend.repositories.admin_jobs import AdminJobRepository
from admin.backend.services.load_artifacts import YearbookArtifactService
from admin.backend.services.load_dml import YEARBOOK_LOAD_MODES
from admin.backend.services.load_parser import parse
from admin.backend.services.load_pipeline import YearbookIngestionService
from admin.backend.services.load_workspace import create_workspace, migrate_legacy_workspaces


# 관리자 서버와 적재 명령이 공유하는 CLI 인자 구조를 만든다.
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
    ingest.add_argument("--mode", choices=YEARBOOK_LOAD_MODES, default="reject")
    ingest.add_argument("--embedding", choices=("bge-m3", "skip"), default="bge-m3")

    build_sql = commands.add_parser(
        "build-sql",
        help="parse and write review/load artifacts without touching a database",
    )
    build_sql.add_argument("hwpx_path")
    build_sql.add_argument("--year", type=int, required=True)
    build_sql.add_argument("--title", default=None)
    build_sql.add_argument("--pub-no", default=None)
    build_sql.add_argument("--mode", choices=YEARBOOK_LOAD_MODES, default="replace")
    build_sql.add_argument(
        "--out",
        default=None,
        help="output directory (default: a new administrator workspace)",
    )

    commands.add_parser("serve", help="run isolated administrator web server")

    return parser


# HWPX를 격리된 작업공간에 복사하고 전체 적재 파이프라인을 동기 실행한다.
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
        target=settings.default_target,
        load_mode=args.mode,
        embedding_model=args.embedding,
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


# DB 없이 파싱 결과, 검수 문서와 적재 SQL만 만든다. 적재 전에 계층·중복을
# 사람이 먼저 확인하고 SQL을 그대로 다른 환경으로 옮길 수 있게 한다.
def run_build_sql_command(args) -> int:
    source = Path(args.hwpx_path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"input file not found: {source}")

    if args.out:
        workspace = Path(args.out).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
    else:
        _, workspace = create_workspace(settings.workspace_dir)

    parsed = parse(
        str(source),
        publication_year=args.year,
        publication_title=args.title or f"{args.year} 행정안전통계연보",
        publication_no=args.pub_no,
    )
    artifacts = YearbookArtifactService(workspace)
    written = artifacts.save_parsed_outputs(parsed)
    load_sql = artifacts.save_load_dml(parsed, args.mode)

    checks = parsed.get("checks") or {}
    print(f"statistics={checks.get('statistics')} tables={checks.get('tables')}")
    for label, key in (
        ("duplicate ref_id", "duplicate_ref_ids"),
        ("statistics without a table", "statistics_without_tables"),
        ("statistics without a chapter", "statistics_without_chapter"),
    ):
        print(f"  {label}: {len(checks.get(key) or [])}")
    for name in (*written.values(), load_sql.name):
        print(f"  {workspace / name}")
    return 0


# 선택한 하위 명령을 실행하고 CLI에 맞는 종료 코드와 오류 메시지를 전달한다.
def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        from admin.backend.app import run as run_server

        run_server()
        return
    try:
        if args.command == "build-sql":
            status = run_build_sql_command(args)
        else:
            status = run_ingestion_command(args)
        raise SystemExit(status)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
