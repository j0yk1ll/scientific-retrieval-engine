"""High-level retrieval API constrained to DOI and title inputs.

This module exposes the :class:`RetrievalClient` facade and the functional
helpers defined in :mod:`literature_retrieval_engine.__init__`. Inputs are limited to DOIs and
title-like queries; the client intentionally avoids arbitrary URL lookups or
other identifier types so downstream services remain focused on curated
bibliographic metadata.

Example: lookup by DOI
----------------------
```python
from literature_retrieval_engine.api import RetrievalClient

client = RetrievalClient()
paper = client.search_paper_by_doi("10.5555/example.doi")
if paper:
    print(paper.title, paper.doi, paper.source)
```
"""

from __future__ import annotations

from typing import List, Optional, Set

import requests

from .core.identifiers import normalize_doi
from .core.models import EvidenceChunk, Paper
from .core.session import SessionIndex
from .core.settings import RetrievalSettings
from .providers.adapters import openalex_work_to_paper, semanticscholar_paper_to_paper
from .providers.clients.base import ClientError
from .providers.clients.crossref import CrossrefClient
from .providers.clients.datacite import DataCiteClient
from .providers.clients.grobid import GrobidClient
from .providers.clients.openalex import OpenAlexClient
from .providers.clients.semanticscholar import DEFAULT_FIELDS, SemanticScholarClient
from .providers.clients.unpaywall import UnpaywallClient
from .services.doi_resolver_service import DoiResolverService
from .services.evidence_service import EvidenceConfig, EvidenceService
from .services.full_text_resolver_service import FullTextResolverService
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
        self._openalex_client = openalex_client

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

        doi_resolver = DoiResolverService(
            crossref=crossref_client, datacite=datacite_client
        )

        semanticscholar_client = semanticscholar_client or SemanticScholarClient(
            session=self.session,
            base_url=self.settings.semanticscholar_base_url,
            timeout=self.settings.timeout,
            api_key=self.settings.semanticscholar_api_key,
        )
        self._semanticscholar_client = semanticscholar_client

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

        if unpaywall_client is not None:
            self._unpaywall_client = unpaywall_client
        else:
            if not self.settings.unpaywall_email:
                raise ValueError("Unpaywall email is required")
            self._unpaywall_client = UnpaywallClient(
                self.settings.unpaywall_email,
                session=self.session,
                base_url=self.settings.unpaywall_base_url,
                timeout=self.settings.timeout,
            )

        self._full_text_resolver = FullTextResolverService(
            unpaywall_client=self._unpaywall_client
        )
        self._paper_enrichment_service = PaperEnrichmentService(
            resolver=self._full_text_resolver
        )

        self._grobid_client: GrobidClient = GrobidClient(
            session=self.session, base_url=self.settings.grobid_base_url
        )
        self._evidence_service = EvidenceService(
            session=self.session,
            grobid=self._grobid_client,
            full_text_resolver=self._full_text_resolver,
            config=EvidenceConfig(),
        )

    def search_citations(self, doi: str) -> List[Paper]:
        normalized = normalize_doi(doi)
        if not normalized:
            return []

        # 1) Prefer OpenAlex citing works
        try:
            work = self._openalex_client.get_work_by_doi(normalized)
            if work and work.openalex_id:
                citing_works = self._openalex_client.get_citing_works(
                    work.openalex_id,
                    max_pages=getattr(self.settings, "openalex_citation_max_pages", 5),
                )
                citing_papers = [openalex_work_to_paper(w) for w in citing_works]
                citing_papers = self._dedupe_citing_papers(citing_papers)
                citing_papers = self._enforce_doi_backed_citing_papers(citing_papers)
                return citing_papers
        except ClientError:
            pass

        # 2) Fallback to Semantic Scholar citing papers
        try:
            seed = self._semanticscholar_client.get_by_doi(
                normalized, fields=DEFAULT_FIELDS
            )
            if seed:
                paper_identifier = f"DOI:{normalized}"
                citing_records = self._semanticscholar_client.get_citations(
                    paper_identifier,
                    limit=getattr(self.settings, "citation_limit", 500),
                )
                citing_papers = [
                    semanticscholar_paper_to_paper(p) for p in citing_records
                ]
                citing_papers = self._dedupe_citing_papers(citing_papers)
                citing_papers = self._enforce_doi_backed_citing_papers(citing_papers)
                return citing_papers
        except ClientError:
            pass

        return []

    def search_papers(
        self,
        query: str,
        k: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[Paper]:
        """Search OpenAlex and Semantic Scholar for papers matching a title-like ``query``.

        Queries are treated as bibliographic text; URL-based lookups are out of scope
        to keep inputs aligned with DOI/title-centric workflows.
        """

        papers = self._search_service.search(
            query, k=k, min_year=min_year, max_year=max_year
        )
        self.session_index.add_papers(papers)
        return papers

    def search_paper_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI across configured services.

        The input should be a DOI string (a ``https://doi.org/`` prefix is optional);
        arbitrary URLs are not resolved.
        """

        paper = self._search_service.search_by_doi(doi)
        if not paper:
            return None
        if self._paper_enrichment_service:
            paper = self._paper_enrichment_service.enrich(paper)
        self.session_index.add_papers([paper])
        return paper

    def search_paper_by_title(self, title: str) -> Optional[Paper]:
        """Search for a paper by title.

        URL parsing and non-bibliographic identifiers are deliberately excluded.
        """

        paper = self._search_service.search_by_title(title)
        if not paper:
            return None
        self.session_index.add_papers([paper])
        return paper

    def gather_evidence(self, query: str) -> List[EvidenceChunk]:
        """Gather citeable evidence chunks (chunk text + originating paper reference)."""

        papers = self.search_papers(query)

        # If Unpaywall is enabled, enrich papers so pdf_url is populated when possible.
        if self._paper_enrichment_service:
            papers = [self._paper_enrichment_service.enrich(paper) for paper in papers]

        chunks = self._evidence_service.gather(papers)
        self.session_index.evidence_chunks[query] = chunks
        return chunks

    def clear_papers_and_evidence(self) -> None:
        """Clear all papers and evidence for the current session."""

        self.session_index.reset()

    def _dedupe_citing_papers(self, papers: List[Paper]) -> List[Paper]:
        out: List[Paper] = []
        seen: Set[str] = set()

        for p in papers:
            doi = normalize_doi(p.doi)
            if doi:
                key = f"doi:{doi}"
            else:
                key = (
                    f"{(p.title or '').strip().lower()}|{p.year or ''}|"
                    f"{(p.authors[0] if p.authors else '').strip().lower()}"
                )

            if key in seen:
                continue
            seen.add(key)
            out.append(p)

        return out

    def _enforce_doi_backed_citing_papers(self, papers: List[Paper]) -> List[Paper]:
        """
        Ensure each citing paper has a DOI if possible; drop those without DOI after bounded upgrade attempts.
        """
        out: List[Paper] = []
        seen_dois: Set[str] = set()
        max_upgrade_attempts = 50
        attempts = 0

        for p in papers:
            doi = normalize_doi(p.doi)
            if doi:
                if doi not in seen_dois:
                    seen_dois.add(doi)
                    out.append(p)
                continue

            if attempts >= max_upgrade_attempts:
                continue
            attempts += 1

            title = (p.title or "").strip()
            if not title:
                continue

            resolved = self._search_service.doi_resolver.resolve_doi_from_title(
                title, expected_authors=p.authors or None
            )
            if not resolved:
                continue

            canonical = self._search_service._fetch_canonical_by_doi(resolved)
            if not canonical:
                continue

            canonical_doi = normalize_doi(canonical.doi)
            if not canonical_doi or canonical_doi in seen_dois:
                continue

            seen_dois.add(canonical_doi)
            out.append(canonical)

        return out
