from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover
    from retrieval.chunking import GrobidChunk


@dataclass
class Chunk:
    """Lightweight representation of a retrievable text chunk."""

    chunk_id: str
    paper_id: str
    text: str
    title: Optional[str] = None
    section: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_grobid(
        cls, grobid_chunk: "GrobidChunk", *, title: Optional[str] = None
    ) -> "Chunk":
        """Adapt a :class:`~retrieval.chunking.GrobidChunk` into a retrievable chunk."""

        metadata: Dict[str, Any] = {
            "start_char": grobid_chunk.start_char,
            "end_char": grobid_chunk.end_char,
            "token_count": grobid_chunk.token_count,
        }

        return cls(
            chunk_id=grobid_chunk.chunk_id,
            paper_id=grobid_chunk.paper_id,
            text=grobid_chunk.content,
            title=title,
            section=grobid_chunk.section,
            metadata=metadata,
        )


@dataclass
class RetrievedChunk:
    """Enriched retrieval output including fused and per-modality scores."""

    chunk: Chunk
    fused_score: float
    lexical_score: Optional[float] = None
    vector_score: Optional[float] = None
