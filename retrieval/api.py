"""High-level retrieval API constrained to DOI and title inputs.

This module exposes the :class:`RetrievalClient` facade and the functional
helpers defined in :mod:`retrieval.__init__`. Inputs are limited to DOIs and
title-like queries; the client intentionally avoids arbitrary URL lookups or
other identifier types so downstream services remain focused on curated
bibliographic metadata.

Example: lookup by DOI
----------------------
```python
from retrieval.api import RetrievalClient

client = RetrievalClient()
papers = client.search_paper_by_doi("10.5555/example.doi")
for paper in papers:
    print(paper.title, paper.doi, paper.source)
```
"""

from __future__ import annotations

from typing import List, Optional

import requests

from .core.models import Citation, EvidenceChunk, Paper
from .core.identifiers import normalize_doi
from .core.session import SessionIndex
from .core.settings import RetrievalSettings
from .providers.clients.crossref import CrossrefClient
from .providers.clients.datacite import DataCiteClient
from .providers.clients.grobid import GrobidClient
from .providers.clients.openalex import OpenAlexClient
from .providers.clients.opencitations import OpenCitationsClient
from .providers.clients.semanticscholar import SemanticScholarClient
from .providers.clients.base import ClientError
from .providers.clients.unpaywall import FullTextCandidate, UnpaywallClient, resolve_full_text
from .services.doi_resolver_service import DoiResolverService
from .services.evidence_service import EvidenceConfig, EvidenceService
from .services.paper_enrichment_service import PaperEnrichmentService
from .services.paper_merge_service import PaperMergeService
from .services.search_service import PaperSearchService


class RetrievalClient:
    """Facade around search and citation workflows with configurable settings.

    The public contract is intentionally narrow: inputs are limited to DOIs and
    titles. Arbitrary URL lookups and direct server scraping are not part of the
    supported pipeline so that queries stay aligned with upstream metadata
    providers.
    """

    def __init__(
        self,
        settings: Optional[RetrievalSettings] = None,
        *,
        session: Optional[requests.Session] = None,
        search_service: Optional[PaperSearchService] = None,
        opencitations_client: Optional[OpenCitationsClient] = None,
        openalex_client: Optional[OpenAlexClient] = None,
        semanticscholar_client: Optional[SemanticScholarClient] = None,
        session_index: Optional[SessionIndex] = None,
        unpaywall_client: Optional[UnpaywallClient] = None,
    ) -> None:
        self.settings = settings or RetrievalSettings()
        client_session = self.settings.build_session() if session is None else session
        if session is not None and self.settings.user_agent:
            session.headers.setdefault("User-Agent", self.settings.user_agent)
        self.session = client_session
        self.session_index = session_index or SessionIndex()

        openalex_client = openalex_client or OpenAlexClient(
            session=self.session,
            base_url=self.settings.openalex_base_url,
            timeout=self.settings.timeout,
        )

        crossref_client = CrossrefClient(
            session=self.session,
            timeout=self.settings.timeout,
            base_url=self.settings.crossref_base_url,
        )

        datacite_client = DataCiteClient(
            session=self.session,
            timeout=self.settings.timeout,
            base_url=self.settings.datacite_base_url,
        )

        doi_resolver = DoiResolverService(crossref=crossref_client, datacite=datacite_client)

        semanticscholar_client = semanticscholar_client or SemanticScholarClient(
            session=self.session,
            base_url=self.settings.semanticscholar_base_url,
            timeout=self.settings.timeout,
            api_key=self.settings.semanticscholar_api_key,
        )

        merge_service = PaperMergeService(
            source_priority=["crossref", "datacite", "openalex", "semanticscholar"]
        )

        self._search_service = search_service or PaperSearchService(
            openalex=openalex_client,
            semanticscholar=semanticscholar_client,
            crossref=crossref_client,
            datacite=datacite_client,
            doi_resolver=doi_resolver,
            merge_service=merge_service,
        )
        self._openalex_client = openalex_client
        self._semanticscholar_client = semanticscholar_client

        self._opencitations_client = opencitations_client or OpenCitationsClient(
            session=self.session,
            timeout=self.settings.timeout,
            base_url=self.settings.opencitations_base_url,
        )

        if unpaywall_client is not None:
            self._unpaywall_client = unpaywall_client
        elif self.settings.enable_unpaywall:
            if not self.settings.unpaywall_email:
                raise ValueError("Unpaywall email is required when enable_unpaywall is True")
            self._unpaywall_client = UnpaywallClient(
                self.settings.unpaywall_email,
                session=self.session,
                base_url=self.settings.unpaywall_base_url,
                timeout=self.settings.timeout,
            )
        else:
            self._unpaywall_client = None

        self._paper_enrichment_service = (
            PaperEnrichmentService(unpaywall_client=self._unpaywall_client)
            if self._unpaywall_client
            else None
        )

        # Optional: only useful if a GROBID service is running.
        # If you do not want full-text chunking, leave this as None.
        self._grobid_client: GrobidClient | None = GrobidClient(session=self.session)
        self._evidence_service = EvidenceService(
            session=self.session,
            grobid=self._grobid_client,
            config=EvidenceConfig(),
        )

    def search_papers(
        self, query: str, k: int = 5, min_year: Optional[int] = None, max_year: Optional[int] = None
    ) -> List[Paper]:
        """Search OpenAlex and Semantic Scholar for papers matching a title-like ``query``.

        Queries are treated as bibliographic text; URL-based lookups are out of scope
        to keep inputs aligned with DOI/title-centric workflows.
        """

        papers = self._search_service.search(query, k=k, min_year=min_year, max_year=max_year)
        self.session_index.add_papers(papers)
        return papers

    def search_paper_by_doi(self, doi: str) -> List[Paper]:
        """Search for a paper by DOI across configured services.

        The input should be a DOI string (a ``https://doi.org/`` prefix is optional);
        arbitrary URLs are not resolved.
        """

        papers = self._search_service.search_by_doi(doi)
        if self._paper_enrichment_service:
            papers = [self._paper_enrichment_service.enrich(paper) for paper in papers]
        self.session_index.add_papers(papers)
        return papers

    def search_paper_by_title(self, title: str) -> List[Paper]:
        """Search for a paper by title.

        URL parsing and non-bibliographic identifiers are deliberately excluded.
        """

        papers = self._search_service.search_by_title(title)
        self.session_index.add_papers(papers)
        return papers

    def gather_evidence(self, query: str) -> List[EvidenceChunk]:
        """Gather citeable evidence chunks (chunk text + originating paper reference)."""

        papers = self.search_papers(query)

        # If Unpaywall is enabled, enrich papers so pdf_url is populated when possible.
        if self._paper_enrichment_service:
            papers = [self._paper_enrichment_service.enrich(paper) for paper in papers]

        chunks = self._evidence_service.gather(papers)
        self.session_index.evidence_chunks[query] = chunks
        return chunks

    def search_citations(self, paper_id: str) -> List[Citation]:
        """Search OpenCitations for citations of the given paper identifier (e.g., DOI)."""

        citations = self._opencitations_client.citations(paper_id)
        if citations:
            return citations

        normalized_doi = normalize_doi(paper_id)
        cited_id = normalized_doi or (paper_id.strip() if paper_id else "")
        if not cited_id:
            return []

        if self.settings.enable_semanticscholar_citation_fallback:
            fallback = self._search_semanticscholar_citations(cited_id, normalized_doi)
            if fallback:
                return fallback

        if self.settings.enable_openalex_citation_fallback:
            fallback = self._search_openalex_citations(cited_id, normalized_doi)
            if fallback:
                return fallback

        return []

    def _search_semanticscholar_citations(
        self, cited_id: str, normalized_doi: Optional[str]
    ) -> List[Citation]:
        if not cited_id:
            return []

        paper_identifier = f"DOI:{normalized_doi}" if normalized_doi else cited_id
        try:
            citing_papers = self._semanticscholar_client.get_citations(
                paper_identifier,
                limit=getattr(self.settings, "citation_limit", 500),
            )
        except ClientError:
            return []

        citations: List[Citation] = []
        seen = set()
        for paper in citing_papers:
            citing_id = paper.doi or paper.paper_id
            if not citing_id:
                continue
            key = (citing_id, cited_id)
            if key in seen:
                continue
            seen.add(key)
            citations.append(Citation(citing=citing_id, cited=cited_id, creation=None))
        return citations

    def _search_openalex_citations(
        self, cited_id: str, normalized_doi: Optional[str]
    ) -> List[Citation]:
        if not normalized_doi:
            return []

        try:
            work = self._openalex_client.get_work_by_doi(normalized_doi)
            if not work or not work.openalex_id:
                return []
            citing_works = self._openalex_client.get_citing_works(
                work.openalex_id,
                max_pages=getattr(self.settings, "openalex_citation_max_pages", 5),
            )
        except ClientError:
            return []

        citations: List[Citation] = []
        seen = set()
        for citing_work in citing_works:
            citing_id = citing_work.doi or citing_work.openalex_id
            if not citing_id:
                continue
            key = (citing_id, cited_id)
            if key in seen:
                continue
            seen.add(key)
            citations.append(Citation(citing=citing_id, cited=cited_id, creation=None))
        return citations

    def resolve_full_text(self, *, doi: str, title: str) -> Optional[FullTextCandidate]:
        """Attempt to resolve full-text sources when Unpaywall is enabled."""

        if self._unpaywall_client is None:
            return None
        return resolve_full_text(doi=doi, title=title, unpaywall_client=self._unpaywall_client)

    def clear_papers_and_evidence(self) -> None:
        """Clear all papers and evidence for the current session."""

        self.session_index.reset()
