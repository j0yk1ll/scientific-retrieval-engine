"""Core data models, identifiers, and configuration for retrieval."""

from .identifiers import normalize_doi, normalize_title
from .matching import jaccard, title_tokens
from .models import Citation, Paper, PaperEvidence, PaperProvenance
from .session import SessionIndex
from .settings import RetrievalSettings, load_dotenv_from_root

__all__ = [
    "Citation",
    "Paper",
    "PaperEvidence",
    "PaperProvenance",
    "SessionIndex",
    "RetrievalSettings",
    "load_dotenv_from_root",
    "normalize_doi",
    "normalize_title",
    "jaccard",
    "title_tokens",
]
