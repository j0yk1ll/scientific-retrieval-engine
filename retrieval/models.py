from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Paper:
    """Normalized representation of a paper returned by any search service."""

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
    is_oa: Optional[bool] = None
    authors: List[str] = field(default_factory=list)
    provenance: Optional["PaperProvenance"] = None


@dataclass
class Citation:
    """Simple citation representation from OpenCitations."""

    citing: str
    cited: str
    creation: Optional[str] = None


@dataclass
class PaperEvidence:
    """Represents the source and raw value used for a specific field."""

    source: str
    value: Any


@dataclass
class PaperProvenance:
    """Tracks how a merged Paper was constructed."""

    sources: List[str] = field(default_factory=list)
    source_records: Dict[str, str] = field(default_factory=dict)
    field_sources: Dict[str, PaperEvidence] = field(default_factory=dict)


__all__ = ["Paper", "Citation", "PaperEvidence", "PaperProvenance"]
