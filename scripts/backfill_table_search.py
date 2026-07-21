#!/usr/bin/env python3
"""기존 stat_tables.body에서 검색 청크와 선택적 임베딩을 재생성한다."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import psycopg
from psycopg.rows import dict_row

from admin.backend.config import settings
from admin.backend.repositories.postgres_dml import PostgresDmlRepository
from admin.backend.repositories.table_search_embeddings import TableSearchEmbeddingRepository
from admin.backend.services.load_embedding import EmbeddingRunner
from admin.backend.services.load_schema import SCHEMA_PATH
from shared.embedding import (
    TABLE_SEARCH_CONTENT_VERSION,
    EmbeddingSettings,
    create_embedding_profile,
    create_embedding_provider,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("local", "production"), default="local")
    parser.add_argument("--year", type=int)
    parser.add_argument("--embedding", choices=("bge-m3", "skip"), default="bge-m3")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dsn = settings.target_dsn(args.target)
    PostgresDmlRepository().execute_dml_file(dsn, SCHEMA_PATH)
    source = TableSearchEmbeddingRepository(args.year)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        chunk_count = source.rebuild_chunks(conn)
        print(f"table_search_chunks={chunk_count}")
        if args.embedding == "skip":
            return

        model = settings.embedding_model(args.embedding)
        embed_settings = EmbeddingSettings(
            provider=str(model.provider),
            model=str(model.model),
            dimension=int(model.dimension),
            batch_size=16,
            device=model.device,
            max_length=512,
            revision=model.revision,
        )
        profile = create_embedding_profile(embed_settings, TABLE_SEARCH_CONTENT_VERSION)
        runner = EmbeddingRunner(
            create_embedding_provider(embed_settings),
            profile,
            source,
        )
        result = runner.run(
            conn,
            batch_size=embed_settings.batch_size,
            progress=lambda done, total: print(f"embedded={done}/{total}"),
        )
        print(f"profile_key={result.profile_key}")


if __name__ == "__main__":
    main()
