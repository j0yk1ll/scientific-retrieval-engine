from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import EvidenceChunk, Paper


@dataclass
class SessionIndex:
    """In-memory storage for a retrieval client session."""

    papers: Dict[str, Paper] = field(default_factory=dict)
    evidence_chunks: Dict[str, List[EvidenceChunk]] = field(default_factory=dict)

    def reset(self) -> None:
        self.papers.clear()
        self.evidence_chunks.clear()

    def _make_key(self, paper: Paper) -> Optional[str]:
        if paper.doi:
            return f"doi:{paper.doi}"
        return None

    def add_papers(self, items: List[Paper]) -> None:
        for paper in items:
            key = self._make_key(paper)
            if not key:
                continue
            self.papers[key] = paper

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        if not paper_id:
            return None
        if paper_id.startswith("doi:"):
            return self.papers.get(paper_id)
        return self.papers.get(f"doi:{paper_id}")
