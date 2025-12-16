"""Utilities for exporting chunk text for indexing pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

ChunkRow = Tuple[str, str]


def export_chunks_tsv(chunks: Iterable[ChunkRow], output_path: Path) -> Path:
    """Write chunk identifiers and text to a TSV file.

    The file layout is ``chunk_id<TAB>text`` per line, matching the legacy
    collection format and remaining useful for debugging.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        for chunk_id, text in chunks:
            sanitized_text = text.replace("\n", " ").strip()
            handle.write(f"{chunk_id}\t{sanitized_text}\n")

    return output_path
