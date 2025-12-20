from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Optional, Protocol, Sequence

from retrieval.core.models import Paper
from retrieval.providers.clients.base import ClientError
from retrieval.providers.clients.unpaywall import OpenAccessLocation, UnpaywallClient


@dataclass(frozen=True)
class FullTextCandidate:
    pdf_url: str
    source: str
    license: Optional[str] = None
    version: Optional[str] = None
    host_type: Optional[str] = None
    is_best: Optional[bool] = None


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


class UnpaywallResolver:
    name_best = "unpaywall_best"
    name_location = "unpaywall_location"

    def __init__(self, unpaywall_client: UnpaywallClient) -> None:
        self.unpaywall_client = unpaywall_client

    def resolve(self, paper: Paper) -> List[FullTextCandidate]:
        doi = (paper.doi or "").strip()
        if not doi:
            return []
        try:
            record = self.unpaywall_client.get_record(doi)
        except ClientError:
            return []
        if not record:
            return []

        locations = record.oa_locations
        if record.best_oa_location:
            return self._candidates_with_best(record.best_oa_location, locations)
        if not locations:
            return []
        return self._candidates_with_best(locations[0], locations[1:])

    def _candidates_with_best(
        self,
        best_location: OpenAccessLocation,
        locations: Sequence[OpenAccessLocation],
    ) -> List[FullTextCandidate]:
        candidates: List[FullTextCandidate] = []
        best_candidate = self._to_candidate(best_location, self.name_best)
        if best_candidate:
            candidates.append(best_candidate)
        for location in locations:
            if location == best_location:
                continue
            candidate = self._to_candidate(location, self.name_location)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _to_candidate(
        self, location: OpenAccessLocation, source: str
    ) -> Optional[FullTextCandidate]:
        pdf_url = location.pdf_url
        if not pdf_url:
            return None
        return FullTextCandidate(
            pdf_url=pdf_url,
            source=source,
            license=location.license,
            version=location.version,
            host_type=location.host_type,
            is_best=location.is_best,
        )


class FullTextResolverService:
    def __init__(
        self,
        resolvers: Optional[Sequence[FullTextResolver]] = None,
        *,
        unpaywall_client: Optional[UnpaywallClient] = None,
    ) -> None:
        self.resolvers = (
            list(resolvers)
            if resolvers is not None
            else self._default_resolvers(unpaywall_client=unpaywall_client)
        )

    def resolve(self, paper: Paper) -> FullTextResolution:
        candidates: List[FullTextCandidate] = []
        for resolver in self.resolvers:
            candidates.extend(resolver.resolve(paper))
        ordered = self._order_candidates(candidates)
        return FullTextResolution(candidates=ordered)

    @staticmethod
    def _order_candidates(candidates: List[FullTextCandidate]) -> List[FullTextCandidate]:
        source_rank = {
            UnpaywallResolver.name_best: 0,
            UnpaywallResolver.name_location: 1,
            UpstreamFieldsResolver.name: 2,
            ArxivDeterministicResolver.name: 3,
        }
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                source_rank.get(candidate.source, len(source_rank)),
                candidate.source,
                candidate.pdf_url,
            ),
        )
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
    def _default_resolvers(
        *, unpaywall_client: Optional[UnpaywallClient]
    ) -> List[FullTextResolver]:
        resolvers: List[FullTextResolver] = [
            UpstreamFieldsResolver(),
            ArxivDeterministicResolver(),
        ]
        if unpaywall_client is not None:
            resolvers.insert(0, UnpaywallResolver(unpaywall_client))
        return resolvers
