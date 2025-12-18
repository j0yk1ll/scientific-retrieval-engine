from __future__ import annotations

from typing import List, Optional

from .session import SESSION_INDEX
from .services.models import Citation, Paper
from .services.opencitations_service import OpenCitationsService
from .services.search_service import PaperSearchService

_search_service = PaperSearchService()
_opencitations_service = OpenCitationsService()


def search_papers(
    query: str, k: int = 5, min_year: Optional[int] = None, max_year: Optional[int] = None
) -> List[Paper]:
    """Search OpenAlex and Semantic Scholar for papers matching ``query``."""

    papers = _search_service.search(query, k=k, min_year=min_year, max_year=max_year)
    SESSION_INDEX.add_papers(papers)
    return papers


def search_paper_by_doi(doi: str) -> List[Paper]:
    """Search for a paper by DOI across configured services."""

    papers = _search_service.search_by_doi(doi)
    SESSION_INDEX.add_papers(papers)
    return papers


def search_paper_by_title(title: str) -> List[Paper]:
    """Search for a paper by title."""

    papers = _search_service.search_by_title(title)
    SESSION_INDEX.add_papers(papers)
    return papers


def gather_evidence(query: str) -> List[Paper]:
    """Gather evidence by searching and caching the resulting papers."""

    papers = search_papers(query)
    SESSION_INDEX.evidence[query] = papers
    return papers


def search_citations(paper_id: str) -> List[Citation]:
    """Search OpenCitations for citations of the given paper identifier (e.g., DOI)."""

    return _opencitations_service.citations(paper_id)


def clear_papers_and_evidence() -> None:
    """Clear all cached papers and evidence for the current session."""

    SESSION_INDEX.reset()
