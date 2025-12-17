"""Filesystem utilities for deterministic storage paths and safe writes."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def pdf_path(data_dir: Path, paper_id: str) -> Path:
    """Return the canonical PDF path for a paper within ``data_dir``."""

    return data_dir / "papers" / f"{paper_id}.pdf"


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Atomically write ``data`` to ``path`` using a temporary file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=target.name, dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path`` using UTF-8 by default."""

    atomic_write_bytes(path, text.encode(encoding))


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest for the given ``data``."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = 8192) -> str:
    """Return the SHA-256 hex digest for the file at ``path``."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
