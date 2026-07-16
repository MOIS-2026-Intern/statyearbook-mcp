#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import math
import os

from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load and test an embedding model without network access."
    )
    parser.add_argument("--model", type=Path, default=Path("models/bge-m3"))
    parser.add_argument("--dimension", type=int, default=1024)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max-length", type=int, default=512)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    model_path = args.model.expanduser().resolve()
    manifest_path = model_path / ".statyearbook-model.json"
    if not manifest_path.is_file():
        raise SystemExit(f"model manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dimension") != args.dimension:
        raise SystemExit(
            f"manifest dimension {manifest.get('dimension')} != expected {args.dimension}"
        )

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        str(model_path),
        device=args.device,
        local_files_only=True,
    )
    model.max_seq_length = args.max_length
    vector = model.encode(
        ["행정안전통계연보 임베딩 오프라인 검증"],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )[0]
    if len(vector) != args.dimension:
        raise SystemExit(f"embedding dimension {len(vector)} != expected {args.dimension}")
    norm = math.sqrt(sum(float(value) ** 2 for value in vector))
    if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
        raise SystemExit(f"embedding is not normalized: norm={norm}")
    print(
        f"offline model verified: path={model_path} "
        f"revision={manifest.get('revision')} dimension={len(vector)} norm={norm:.6f}"
    )


if __name__ == "__main__":
    main()
