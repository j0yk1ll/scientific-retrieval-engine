"""HTTP clients used by the retrieval service layer."""

from .base import (
    BaseHttpClient,
    ClientError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    RequestRejectedError,
    UnauthorizedError,
    UpstreamError,
)
from .crossref import CrossrefClient, CrossrefWork
from .datacite import DataCiteClient, DataCiteWork
from .grobid import GrobidClient
from .openalex import OpenAlexClient, OpenAlexWork
from .semanticscholar import DEFAULT_FIELDS as SEMANTICSCHOLAR_DEFAULT_FIELDS
from .semanticscholar import SemanticScholarClient, SemanticScholarPaper
from .unpaywall import (
    OpenAccessLocation,
    UnpaywallClient,
    UnpaywallFullTextCandidate,
    UnpaywallRecord,
)

__all__ = [
    "BaseHttpClient",
    "ClientError",
    "CrossrefClient",
    "CrossrefWork",
    "DataCiteClient",
    "DataCiteWork",
    "GrobidClient",
    "NotFoundError",
    "OpenAccessLocation",
    "OpenAlexClient",
    "OpenAlexWork",
    "RateLimitedError",
    "RequestRejectedError",
    "SEMANTICSCHOLAR_DEFAULT_FIELDS",
    "SemanticScholarClient",
    "SemanticScholarPaper",
    "UnauthorizedError",
    "UnpaywallClient",
    "UnpaywallFullTextCandidate",
    "UnpaywallRecord",
    "ForbiddenError",
    "UpstreamError",
]
