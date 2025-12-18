from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import Paper


@dataclass
class SessionIndex:
    """In-memory storage for a retrieval client session."""

    papers: Dict[str, Paper] = field(default_factory=dict)
    evidence: Dict[str, List[Paper]] = field(default_factory=dict)

    def reset(self) -> None:
        self.papers.clear()
        self.evidence.clear()

    def add_papers(self, items: List[Paper]) -> None:
        for paper in items:
            key = paper.doi or paper.paper_id or paper.title
            if not key:
                continue
            self.papers[key] = paper

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        return self.papers.get(paper_id)
