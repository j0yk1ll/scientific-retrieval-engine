"""Service layer for the retrieval package."""

from .crossref_service import CrossrefService
from .doi_resolver_service import DoiResolverService
from .openalex_service import OpenAlexService
from .opencitations_service import OpenCitationsService
from .search_service import PaperSearchService
from .semanticscholar_service import SemanticScholarService
from .paper_enrichment_service import PaperEnrichmentService
from .unpaywall_service import UnpaywallService

__all__ = [
    "CrossrefService",
    "DoiResolverService",
    "OpenAlexService",
    "OpenCitationsService",
    "PaperSearchService",
    "SemanticScholarService",
    "PaperEnrichmentService",
    "UnpaywallService",
]
