#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json

from pathlib import Path


DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
DEFAULT_DIMENSION = 1024
MODEL_FILES = (
    "1_Pooling/*",
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "pytorch_model.bin",
    "sentence_bert_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download a revision-pinned embedding model for offline operation."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--dimension", type=int, default=DEFAULT_DIMENSION)
    parser.add_argument("--output", type=Path, default=Path("models/bge-m3"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    from huggingface_hub import snapshot_download

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=args.model,
        revision=args.revision,
        local_dir=output,
        allow_patterns=list(MODEL_FILES),
    )
    manifest = {
        "source_model": args.model,
        "revision": args.revision,
        "dimension": args.dimension,
    }
    (output / ".statyearbook-model.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"offline model prepared: {output}")


if __name__ == "__main__":
    main()
