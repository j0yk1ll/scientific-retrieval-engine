"""Core data models, identifiers, and configuration for literature_retrieval_engine."""

from .identifiers import normalize_doi, normalize_title
from .matching import jaccard, title_tokens
from .models import Paper
from .session import SessionIndex
from .settings import RetrievalSettings

__all__ = [
    "Paper",
    "SessionIndex",
    "RetrievalSettings",
    "normalize_doi",
    "normalize_title",
    "jaccard",
    "title_tokens",
]
