from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Paper:
    """Normalized representation of a paper returned by any search service.

    ``source`` records the upstream provider that produced this specific record
    (e.g., ``"crossref"`` or ``"openalex"``). When multiple records are merged,
    ``primary_source`` reflects the provider whose metadata won the merge and is
    duplicated into ``source`` to preserve compatibility with existing callers.
    """

    paper_id: str
    title: str
    doi: Optional[str]
    abstract: Optional[str]
    year: Optional[int]
    venue: Optional[str]
    source: str
    primary_source: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    resolved_pdf_url: Optional[str] = None
    is_oa: Optional[bool] = None
    authors: List[str] = field(default_factory=list)


@dataclass
class EvidenceChunk:
    """A citeable evidence unit: chunk text + the paper it came from."""

    chunk_id: str
    paper_id: str
    paper_title: str
    paper_doi: Optional[str]
    paper_authors: List[str] = field(default_factory=list)
    paper_year: Optional[int] = None
    section: Optional[str] = None
    content: str = ""
    paper_url: Optional[str] = None
    pdf_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


__all__ = ["Paper", "EvidenceChunk"]
