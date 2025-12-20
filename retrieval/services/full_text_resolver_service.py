from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Optional, Protocol, Sequence

from retrieval.core.models import Paper


@dataclass(frozen=True)
class FullTextCandidate:
    pdf_url: str
    source: str


@dataclass(frozen=True)
class FullTextResolution:
    candidates: List[FullTextCandidate]


class FullTextResolver(Protocol):
    def resolve(self, paper: Paper) -> List[FullTextCandidate]:
        ...


class UpstreamFieldsResolver:
    name = "upstream_fields"

    def resolve(self, paper: Paper) -> List[FullTextCandidate]:
        if not paper.pdf_url:
            return []
        return [FullTextCandidate(pdf_url=paper.pdf_url, source=self.name)]


class ArxivDeterministicResolver:
    name = "arxiv_deterministic"

    _ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(?P<id>.+)$", re.IGNORECASE)

    def resolve(self, paper: Paper) -> List[FullTextCandidate]:
        doi = (paper.doi or "").strip()
        if doi:
            match = self._ARXIV_DOI_RE.match(doi)
            if match:
                arxiv_id = match.group("id")
                return [
                    FullTextCandidate(
                        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                        source=self.name,
                    )
                ]
        url = (paper.url or "").strip()
        if "arxiv.org/abs/" in url:
            arxiv_id = url.split("arxiv.org/abs/", 1)[1].split("?", 1)[0]
            if arxiv_id:
                return [
                    FullTextCandidate(
                        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                        source=self.name,
                    )
                ]
        return []


class FullTextResolverService:
    def __init__(self, resolvers: Optional[Sequence[FullTextResolver]] = None) -> None:
        self.resolvers = list(resolvers) if resolvers is not None else self._default_resolvers()

    def resolve(self, paper: Paper) -> FullTextResolution:
        candidates: List[FullTextCandidate] = []
        for resolver in self.resolvers:
            candidates.extend(resolver.resolve(paper))
        ordered = self._order_candidates(candidates)
        return FullTextResolution(candidates=ordered)

    @staticmethod
    def _order_candidates(candidates: List[FullTextCandidate]) -> List[FullTextCandidate]:
        ordered = sorted(candidates, key=lambda candidate: (candidate.source, candidate.pdf_url))
        seen: set[tuple[str, str]] = set()
        deduped: List[FullTextCandidate] = []
        for candidate in ordered:
            key = (candidate.source, candidate.pdf_url)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    @staticmethod
    def _default_resolvers() -> List[FullTextResolver]:
        return [UpstreamFieldsResolver(), ArxivDeterministicResolver()]
