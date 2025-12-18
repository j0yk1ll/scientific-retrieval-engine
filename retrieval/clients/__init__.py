"""HTTP clients used by the retrieval service layer."""

from .openalex import OpenAlexClient, OpenAlexWork
from .unpaywall import FullTextCandidate, OpenAccessLocation, UnpaywallClient, UnpaywallRecord

__all__ = [
    "FullTextCandidate",
    "OpenAccessLocation",
    "OpenAlexClient",
    "OpenAlexWork",
    "UnpaywallClient",
    "UnpaywallRecord",
]
