from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


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
    url: Optional[str] = None
    authors: List[str] = field(default_factory=list)


@dataclass
class Citation:
    """Simple citation representation from OpenCitations."""

    citing: str
    cited: str
    creation: Optional[str] = None
