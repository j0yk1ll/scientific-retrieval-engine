from __future__ import annotations

from typing import List, Optional

import requests

from .clients.openalex import OpenAlexClient
from .clients.unpaywall import FullTextCandidate, UnpaywallClient, resolve_full_text
from .models import Citation, Paper
from .services.opencitations_service import OpenCitationsService
from .services.search_service import PaperSearchService
from .services.openalex_service import OpenAlexService
from .services.semanticscholar_service import SemanticScholarService
from .settings import RetrievalSettings
from .session import SessionIndex


class RetrievalClient:
    """Facade around search and citation workflows with configurable settings."""

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

        semanticscholar_service = SemanticScholarService(
            session=self.session,
            timeout=self.settings.timeout,
            base_url=self.settings.semanticscholar_base_url,
        )

        self._search_service = search_service or PaperSearchService(
            openalex=openalex_service,
            semanticscholar=semanticscholar_service,
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

    def search_papers(
        self, query: str, k: int = 5, min_year: Optional[int] = None, max_year: Optional[int] = None
    ) -> List[Paper]:
        """Search OpenAlex and Semantic Scholar for papers matching ``query``."""

        papers = self._search_service.search(query, k=k, min_year=min_year, max_year=max_year)
        self.session_index.add_papers(papers)
        return papers

    def search_paper_by_doi(self, doi: str) -> List[Paper]:
        """Search for a paper by DOI across configured services."""

        papers = self._search_service.search_by_doi(doi)
        self.session_index.add_papers(papers)
        return papers

    def search_paper_by_title(self, title: str) -> List[Paper]:
        """Search for a paper by title."""

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
