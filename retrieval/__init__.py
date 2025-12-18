"""Session-scoped retrieval functions for paper discovery and evidence collection."""

from __future__ import annotations

from typing import List, Optional

import atexit

from .api import RetrievalClient
from .models import Citation, Paper

_default_client = RetrievalClient()
atexit.register(_default_client.clear_papers_and_evidence)


def search_papers(
    query: str,
    k: int = 5,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
) -> List[Paper]:
    """Search OpenAlex and Semantic Scholar for papers matching a query.

    Running this multiple times with the same query can yield novel papers as
    upstream sources evolve.
    """

    return _default_client.search_papers(query, k=k, min_year=min_year, max_year=max_year)


def search_paper_by_doi(doi: str) -> List[Paper]:
    """Search for a paper by DOI across supported services."""

    return _default_client.search_paper_by_doi(doi)


def search_paper_by_title(title: str) -> List[Paper]:
    """Search for a paper by title."""

    return _default_client.search_paper_by_title(title)


def gather_evidence(query: str) -> List[Paper]:
    """Gather evidence from papers given a specific query."""

    return _default_client.gather_evidence(query)


def search_citations(paper_id: str) -> List[Citation]:
    """Search OpenCitations for paper citations."""

    return _default_client.search_citations(paper_id)


def clear_papers_and_evidence() -> None:
    """Clear all current papers and evidence from the session index."""

    _default_client.clear_papers_and_evidence()


__all__ = [
    "search_papers",
    "search_paper_by_doi",
    "search_paper_by_title",
    "gather_evidence",
    "search_citations",
    "clear_papers_and_evidence",
]
