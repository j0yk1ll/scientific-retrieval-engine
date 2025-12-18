"""HTTP clients used by the retrieval service layer."""

from .base import BaseHttpClient, ClientError, NotFoundError, RateLimitedError, UpstreamError
from .crossref import CrossrefClient, CrossrefWork
from .datacite import DataCiteClient, DataCiteWork
from .grobid import GrobidClient
from .openalex import OpenAlexClient, OpenAlexWork
from .semanticscholar import DEFAULT_FIELDS as SEMANTICSCHOLAR_DEFAULT_FIELDS
from .semanticscholar import SemanticScholarClient, SemanticScholarPaper
from .unpaywall import FullTextCandidate, OpenAccessLocation, UnpaywallClient, UnpaywallRecord

__all__ = [
    "BaseHttpClient",
    "ClientError",
    "CrossrefClient",
    "CrossrefWork",
    "DataCiteClient",
    "DataCiteWork",
    "FullTextCandidate",
    "GrobidClient",
    "NotFoundError",
    "OpenAccessLocation",
    "OpenAlexClient",
    "OpenAlexWork",
    "RateLimitedError",
    "SEMANTICSCHOLAR_DEFAULT_FIELDS",
    "SemanticScholarClient",
    "SemanticScholarPaper",
    "UnpaywallClient",
    "UnpaywallRecord",
    "UpstreamError",
]
