#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import sys

from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.embedding import (  # noqa: E402
    BGE_M3_REVISION,
    STATISTICS_CONTENT_VERSION,
    EmbeddingConfigurationError,
    EmbeddingSettings,
    create_embedding_profile,
    create_embedding_provider,
)
from load.embedding_pipeline import EmbeddingJobRepository, EmbeddingRunner  # noqa: E402
from load.embedding_dml import EmbeddingDmlWriter  # noqa: E402
from load.statistics_embedding_source import StatisticsEmbeddingSource  # noqa: E402


load_dotenv()

DSN = os.environ.get("STATYEARBOOK_DSN") or os.environ.get("DATABASE_URL")


def build_parser() -> argparse.ArgumentParser:
    defaults = EmbeddingSettings.from_env()
    parser = argparse.ArgumentParser(
        description="Incrementally embed new or outdated statistics rows."
    )
    parser.add_argument("--all", action="store_true",
                        help="현재 profile과 같아도 전체 재임베딩")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB를 변경하지 않고 대상 건수와 profile만 확인")
    parser.add_argument("--status", action="store_true",
                        help="현재 profile 적용 현황과 최근 작업 이력 확인")
    parser.add_argument("--provider", choices=("openai", "local"),
                        default=defaults.provider, help="임베딩 provider")
    parser.add_argument("--model", default=defaults.model,
                        help="OpenAI 모델명 또는 로컬 모델 디렉터리")
    parser.add_argument("--dimension", type=int, default=defaults.dimension,
                        help="임베딩 차원")
    parser.add_argument("--revision", default=defaults.revision,
                        help="로컬 모델 artifact revision")
    parser.add_argument("--batch", type=int, default=defaults.batch_size,
                        help="한 번에 처리할 통계표 수")
    parser.add_argument("--dsn", default=DSN,
                        help="DB 접속 문자열(기본 .env 의 STATYEARBOOK_DSN)")
    parser.add_argument("--year", type=int, default=None,
                        help="특정 발간연도만 임베딩")
    parser.add_argument("--emit-sql", default=None,
                        help="생성된 embedding UPDATE DML 저장 경로")
    return parser


def settings_from_args(args) -> EmbeddingSettings:
    defaults = EmbeddingSettings.from_env()
    revision = args.revision
    if args.provider == "local" and not revision and Path(args.model).name == "bge-m3":
        revision = BGE_M3_REVISION
    return replace(
        defaults,
        provider=args.provider,
        model=args.model,
        dimension=args.dimension,
        batch_size=args.batch,
        revision=revision,
    )


def validate_args(args) -> None:
    if not args.dsn:
        raise EmbeddingConfigurationError(
            "DSN 미지정: .env 의 STATYEARBOOK_DSN 또는 --dsn 을 설정하세요."
        )
    if args.batch <= 0:
        raise EmbeddingConfigurationError("--batch 는 1 이상이어야 합니다.")
    if args.dimension <= 0:
        raise EmbeddingConfigurationError("--dimension 은 1 이상이어야 합니다.")
    if args.status and (args.all or args.dry_run):
        raise EmbeddingConfigurationError("--status 는 --all/--dry-run 과 함께 쓸 수 없습니다.")


def print_status(conn, profile, source) -> None:
    source.validate_dimension(conn, profile.dimension)
    status = source.status(conn, profile.profile_key)
    print(
        f"전체 {status['total_count']} · 임베딩 있음 {status['embedded_count']} · "
        f"현재 profile {status['current_count']} · 처리 필요 {status['pending_count']}"
    )
    jobs = EmbeddingJobRepository().latest_jobs(conn, source.name)
    if not jobs:
        print("최근 embedding job 없음")
        return
    print("최근 embedding jobs:")
    for job in jobs:
        print(
            f"  #{job['job_id']} {job['status']} "
            f"{job['processed_count']}/{job['target_count']} "
            f"started={job['started_at']} finished={job['finished_at']}"
        )


def run(args):
    validate_args(args)
    settings = settings_from_args(args)
    profile = create_embedding_profile(settings, STATISTICS_CONTENT_VERSION)

    import psycopg
    from psycopg.rows import dict_row

    source = StatisticsEmbeddingSource(args.year)
    if args.status:
        with psycopg.connect(args.dsn, row_factory=dict_row) as conn:
            print_status(conn, profile, source)
        return None

    provider = create_embedding_provider(settings)
    runner = EmbeddingRunner(
        provider=provider,
        profile=profile,
        source=source,
    )
    writer = EmbeddingDmlWriter(args.emit_sql, profile) if args.emit_sql and not args.dry_run else None
    try:
        with psycopg.connect(args.dsn, row_factory=dict_row) as conn:
            result = runner.run(
                conn,
                batch_size=settings.batch_size,
                force=args.all,
                dry_run=args.dry_run,
                progress=lambda done, total: print(f"  {done}/{total}"),
                on_batch=writer.write_batch if writer else None,
            )
        if writer:
            writer.complete()
    except Exception as exc:
        if writer:
            writer.abort(exc)
        raise

    mode = "dry-run" if result.dry_run else f"job {result.job_id}"
    print(
        f"{mode} 완료 · 대상 {result.target_count} · 처리 {result.processed_count} · "
        f"profile {result.profile_key}"
    )
    return result


def main() -> None:
    try:
        run(build_parser().parse_args())
    except (EmbeddingConfigurationError, RuntimeError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
