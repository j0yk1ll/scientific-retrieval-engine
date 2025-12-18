"""HTTP clients used by the retrieval service layer."""

from .base import BaseHttpClient, ClientError, NotFoundError, RateLimitedError, UpstreamError
from .openalex import OpenAlexClient, OpenAlexWork
from .unpaywall import FullTextCandidate, OpenAccessLocation, UnpaywallClient, UnpaywallRecord

__all__ = [
    "BaseHttpClient",
    "ClientError",
    "FullTextCandidate",
    "NotFoundError",
    "OpenAccessLocation",
    "OpenAlexClient",
    "OpenAlexWork",
    "RateLimitedError",
    "UnpaywallClient",
    "UnpaywallRecord",
    "UpstreamError",
]
