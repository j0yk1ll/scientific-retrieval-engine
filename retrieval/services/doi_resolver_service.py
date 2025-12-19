"""Title-to-DOI resolution backed by Crossref and DataCite.

Example
-------
```python
from retrieval.services.doi_resolver_service import DoiResolverService

resolver = DoiResolverService()
doi = resolver.resolve_doi_from_title(
    "Attention is all you need", expected_authors=["Ashish Vaswani", "Noam Shazeer"]
)
```
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set

from retrieval.identifiers import normalize_title
from retrieval.matching import jaccard, title_tokens
from retrieval.clients.crossref import CrossrefClient
from retrieval.clients.datacite import DataCiteClient

logger = logging.getLogger(__name__)


class DoiResolverService:
    """Resolve DOIs from titles using Crossref and DataCite heuristics.

    The service searches both registries, applies token-level similarity, and
    optionally filters on overlapping author names to avoid over-eager matches.
    """

    def __init__(
        self,
        *,
        crossref: Optional[CrossrefClient] = None,
        datacite: Optional[DataCiteClient] = None,
        min_similarity: float = 0.9,
    ) -> None:
        self.crossref = crossref or CrossrefClient()
        self.datacite = datacite if datacite is not None else DataCiteClient()
        self.min_similarity = min_similarity

    def resolve_doi_from_title(
        self, title: str, expected_authors: Optional[List[str]] = None
    ) -> Optional[str]:
        normalized_target = normalize_title(title)
        target_tokens = title_tokens(title)
        if not normalized_target:
            return None

        resolver_candidates = [("crossref", self.crossref.search_by_title(title, rows=5))]
        if self.datacite:
            resolver_candidates.append(("datacite", self.datacite.search_by_title(title, rows=5)))
        expected_author_set: Set[str] = set()
        if expected_authors:
            expected_author_set = {normalize_title(author) for author in expected_authors if author}

        for source, candidates in resolver_candidates:
            best_doi: Optional[str] = None
            best_score = -1.0
            best_similarity = 0.0
            best_author_overlap = 0

            for candidate in candidates:
                if not candidate.doi or not candidate.title:
                    continue

                normalized_candidate = normalize_title(candidate.title)
                if not normalized_candidate:
                    continue

                candidate_tokens = title_tokens(candidate.title)
                similarity = (
                    1.0 if normalized_candidate == normalized_target else jaccard(target_tokens, candidate_tokens)
                )

                if similarity < self.min_similarity:
                    continue

                author_overlap = 0
                if expected_author_set:
                    author_overlap = sum(
                        1 for author in candidate.authors if normalize_title(author) in expected_author_set
                    )

                    if similarity < 1.0 and author_overlap == 0:
                        continue

                # Limit the influence of author overlap so weak title matches
                # do not outrank strong similarities.
                score = similarity + min(author_overlap, 1)
                if score > best_score:
                    best_score = score
                    best_doi = candidate.doi
                    best_similarity = similarity
                    best_author_overlap = author_overlap

            if best_doi:
                logger.info(
                    "Resolved DOI from title",
                    extra={
                        "title": title,
                        "doi": best_doi,
                        "source": source,
                        "similarity": best_similarity,
                        "author_overlap": best_author_overlap,
                    },
                )
                return best_doi

        return None
