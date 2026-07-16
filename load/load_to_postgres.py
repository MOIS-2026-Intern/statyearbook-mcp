#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys

from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from load.yearbook_dml import LOAD_MODES, build_load_dml, execute_dml  # noqa: E402


load_dotenv()
ROOT_DIR = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and execute cumulative yearbook DML.")
    parser.add_argument("parsed_json")
    parser.add_argument("--dsn", default=os.environ.get("STATYEARBOOK_DSN") or os.environ.get("DATABASE_URL"))
    parser.add_argument("--emit-sql", default=str(ROOT_DIR / "db" / "seeds" / "load_yearbook.sql"))
    parser.add_argument("--mode", choices=LOAD_MODES, default="reject")
    parser.add_argument("--no-db", action="store_true")
    return parser


def run(args) -> None:
    data = json.loads(Path(args.parsed_json).read_text(encoding="utf-8"))
    dml = build_load_dml(data, args.mode)
    if args.emit_sql:
        output = Path(args.emit_sql)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(dml, encoding="utf-8")
        print(f"DML 저장: {output}")
    if args.no_db:
        print("--no-db: DB 적재를 건너뜁니다.")
        return
    if not args.dsn:
        raise RuntimeError("STATYEARBOOK_DSN 또는 --dsn 이 필요합니다.")
    execute_dml(args.dsn, dml)
    print(f"누적 적재 완료: {data['publication']['year']}년")


def main() -> None:
    try:
        run(build_parser().parse_args())
    except (ValueError, RuntimeError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
