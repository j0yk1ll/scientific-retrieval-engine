from __future__ import annotations

from typing import Protocol, Sequence


class Embedder(Protocol):
    """Simple embedding interface for pluggable models."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return vector representations for the provided texts."""


__all__ = ["Embedder"]
