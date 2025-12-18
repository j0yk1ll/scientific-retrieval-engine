from __future__ import annotations

import logging
from typing import List, Optional, Set

from retrieval.identifiers import normalize_title
from retrieval.services.crossref_service import CrossrefService

logger = logging.getLogger(__name__)


class DoiResolverService:
    """Resolve DOIs from titles using Crossref with simple heuristics."""

    def __init__(self, *, crossref: Optional[CrossrefService] = None) -> None:
        self.crossref = crossref or CrossrefService()

    def resolve_doi_from_title(
        self, title: str, expected_authors: Optional[List[str]] = None
    ) -> Optional[str]:
        normalized_target = normalize_title(title)
        if not normalized_target:
            return None

        candidates = self.crossref.search_by_title(title, rows=5)
        expected_author_set: Set[str] = set()
        if expected_authors:
            expected_author_set = {normalize_title(author) for author in expected_authors if author}

        best_doi: Optional[str] = None
        best_score = -1
        for candidate in candidates:
            if not candidate.doi or not candidate.title:
                continue

            if normalize_title(candidate.title) != normalized_target:
                continue

            overlap = 0
            if expected_author_set:
                overlap = sum(
                    1 for author in candidate.authors if normalize_title(author) in expected_author_set
                )

            score = 1 + overlap  # base score for exact title match
            if score > best_score:
                best_score = score
                best_doi = candidate.doi

        if best_doi:
            logger.info(
                "Resolved DOI from title via Crossref",
                extra={"title": title, "doi": best_doi, "source": "crossref"},
            )

        return best_doi
