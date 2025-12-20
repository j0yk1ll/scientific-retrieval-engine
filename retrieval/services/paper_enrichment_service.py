from __future__ import annotations

from typing import Optional

from retrieval.core.models import Paper
from retrieval.services.full_text_resolver_service import FullTextResolverService


class PaperEnrichmentService:
    """Enrich papers with optional metadata from external services."""

    def __init__(self, *, resolver: Optional[FullTextResolverService] = None) -> None:
        self.resolver = resolver

    def enrich(self, paper: Paper) -> Paper:
        """Attempt to enrich a paper with open-access metadata."""

        if not self.resolver:
            return paper

        return self.resolver.apply(paper)
