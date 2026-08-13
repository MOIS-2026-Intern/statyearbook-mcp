# -*- coding: utf-8 -*-
"""Shared publication kind identifiers used by ingestion and MCP tools."""
from typing import Literal


PublicationKind = Literal["yearbook", "major_statistics"]

DEFAULT_PUBLICATION_KIND: PublicationKind = "yearbook"
MAJOR_STATISTICS_KIND: PublicationKind = "major_statistics"
PUBLICATION_KINDS: tuple[PublicationKind, ...] = (
    DEFAULT_PUBLICATION_KIND,
    MAJOR_STATISTICS_KIND,
)


def normalize_publication_kind(value: str | None) -> PublicationKind:
    kind = (value or DEFAULT_PUBLICATION_KIND).strip()
    if kind not in PUBLICATION_KINDS:
        supported = ", ".join(PUBLICATION_KINDS)
        raise ValueError(f"unsupported publication kind: {kind}; supported: {supported}")
    return kind  # type: ignore[return-value]
