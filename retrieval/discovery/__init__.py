"""Discovery clients for external metadata sources."""

from .openalex import OpenAlexClient, OpenAlexWork

__all__ = [
    "OpenAlexClient",
    "OpenAlexWork",
]
