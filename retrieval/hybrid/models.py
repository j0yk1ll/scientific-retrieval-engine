from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover
    from retrieval.chunking import PaperChunk


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
    def from_paper_chunk(
        cls, paper_chunk: "PaperChunk", *, title: Optional[str] = None
    ) -> "Chunk":
        """Adapt a :class:`~retrieval.chunking.PaperChunk` into a retrievable chunk.

        The chunk metadata uses chunk-stream offsets rather than raw TEI character
        positions to avoid implying direct mapping back to the source XML.
        """

        metadata: Dict[str, Any] = {
            "chunk_stream_start_char": paper_chunk.stream_start_char,
            "chunk_stream_end_char": paper_chunk.stream_end_char,
            "token_count": paper_chunk.token_count,
            "section_index": paper_chunk.section_index,
        }

        return cls(
            chunk_id=paper_chunk.chunk_id,
            paper_id=paper_chunk.paper_id,
            text=paper_chunk.content,
            title=title,
            section=paper_chunk.section,
            metadata=metadata,
        )


@dataclass
class RetrievedChunk:
    """Enriched retrieval output including fused and per-modality scores."""

    chunk: Chunk
    fused_score: float
    lexical_raw_score: Optional[float] = None
    vector_raw_score: Optional[float] = None
    lexical_rank: Optional[int] = None
    vector_rank: Optional[int] = None
