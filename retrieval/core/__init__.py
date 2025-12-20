"""Core data models, identifiers, and configuration for retrieval."""

from .identifiers import normalize_doi, normalize_title
from .matching import jaccard, title_tokens
from .models import Paper
from .session import SessionIndex
from .settings import RetrievalSettings, load_dotenv_from_root

__all__ = [
    "Paper",
    "SessionIndex",
    "RetrievalSettings",
    "load_dotenv_from_root",
    "normalize_doi",
    "normalize_title",
    "jaccard",
    "title_tokens",
]
