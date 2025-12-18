from __future__ import annotations

from typing import List, Optional

import requests

from .clients.crossref import CrossrefClient
from .clients.datacite import DataCiteClient
from .clients.openalex import OpenAlexClient
from .clients.unpaywall import FullTextCandidate, UnpaywallClient, resolve_full_text
from .clients.semanticscholar import SemanticScholarClient
from .models import Citation, Paper
from .services.crossref_service import CrossrefService
from .services.datacite_service import DataCiteService
from .services.doi_resolver_service import DoiResolverService
from .services.opencitations_service import OpenCitationsService
from .services.paper_enrichment_service import PaperEnrichmentService
from .services.paper_merge_service import PaperMergeService
from .services.search_service import PaperSearchService
from .services.openalex_service import OpenAlexService
from .services.semanticscholar_service import SemanticScholarService
from .services.unpaywall_service import UnpaywallService
from .settings import RetrievalSettings
from .session import SessionIndex


class RetrievalClient:
    """Facade around search and citation workflows with configurable settings.

    The public contract is intentionally narrow: inputs are limited to DOIs and
    titles. Arbitrary URL lookups, direct server scraping, and preprint-server
    (e.g., arXiv) requests are not part of the supported pipeline.
    """

    def __init__(
        self,
        settings: Optional[RetrievalSettings] = None,
        *,
        session: Optional[requests.Session] = None,
        search_service: Optional[PaperSearchService] = None,
        opencitations_service: Optional[OpenCitationsService] = None,
        session_index: Optional[SessionIndex] = None,
        unpaywall_client: Optional[UnpaywallClient] = None,
    ) -> None:
        self.settings = settings or RetrievalSettings()
        client_session = self.settings.build_session() if session is None else session
        if session is not None and self.settings.user_agent:
            session.headers.setdefault("User-Agent", self.settings.user_agent)
        self.session = client_session
        self.session_index = session_index or SessionIndex()

        openalex_client = OpenAlexClient(
            session=self.session,
            base_url=self.settings.openalex_base_url,
            timeout=self.settings.timeout,
        )
        openalex_service = OpenAlexService(openalex_client)

        crossref_client = CrossrefClient(
            session=self.session,
            timeout=self.settings.timeout,
            base_url=self.settings.crossref_base_url,
        )
        crossref_service = CrossrefService(crossref_client)

        datacite_client = DataCiteClient(
            session=self.session,
            timeout=self.settings.timeout,
            base_url=self.settings.datacite_base_url,
        )
        datacite_service = DataCiteService(datacite_client)

        doi_resolver = DoiResolverService(crossref=crossref_service, datacite=datacite_service)

        semanticscholar_client = SemanticScholarClient(
            session=self.session,
            base_url=self.settings.semanticscholar_base_url,
            timeout=self.settings.timeout,
        )
        semanticscholar_service = SemanticScholarService(semanticscholar_client)

        merge_service = PaperMergeService(
            source_priority=["crossref", "datacite", "openalex", "semanticscholar"]
        )

        self._search_service = search_service or PaperSearchService(
            openalex=openalex_service,
            semanticscholar=semanticscholar_service,
            crossref=crossref_service,
            datacite=datacite_service,
            doi_resolver=doi_resolver,
            merge_service=merge_service,
        )

        self._opencitations_service = opencitations_service or OpenCitationsService(
            session=self.session,
            timeout=self.settings.timeout,
            base_url=self.settings.opencitations_base_url,
        )

        if unpaywall_client is not None:
            self._unpaywall_client = unpaywall_client
        elif self.settings.enable_unpaywall:
            self._unpaywall_client = UnpaywallClient(
                self.settings.unpaywall_email or "",
                session=self.session,
                base_url=self.settings.unpaywall_base_url,
                timeout=self.settings.timeout,
            )
        else:
            self._unpaywall_client = None

        self._unpaywall_service = (
            UnpaywallService(client=self._unpaywall_client)
            if self._unpaywall_client
            else None
        )
        self._paper_enrichment_service = (
            PaperEnrichmentService(unpaywall=self._unpaywall_service)
            if self._unpaywall_service
            else None
        )

    def search_papers(
        self, query: str, k: int = 5, min_year: Optional[int] = None, max_year: Optional[int] = None
    ) -> List[Paper]:
        """Search OpenAlex and Semantic Scholar for papers matching a title-like ``query``.

        Queries are treated as bibliographic text; URL-based lookups are out of scope.
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

        Preprint lookups and URL parsing are deliberately excluded.
        """

        papers = self._search_service.search_by_title(title)
        self.session_index.add_papers(papers)
        return papers

    def gather_evidence(self, query: str) -> List[Paper]:
        """Gather evidence by searching and caching the resulting papers."""

        papers = self.search_papers(query)
        self.session_index.evidence[query] = papers
        return papers

    def search_citations(self, paper_id: str) -> List[Citation]:
        """Search OpenCitations for citations of the given paper identifier (e.g., DOI)."""

        return self._opencitations_service.citations(paper_id)

    def resolve_full_text(self, *, doi: str, title: str) -> Optional[FullTextCandidate]:
        """Attempt to resolve full-text sources when Unpaywall is enabled."""

        if self._unpaywall_client is None:
            return None
        return resolve_full_text(doi=doi, title=title, unpaywall_client=self._unpaywall_client)

    def clear_papers_and_evidence(self) -> None:
        """Clear all cached papers and evidence for the current session."""

        self.session_index.reset()
