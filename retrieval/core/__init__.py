"""Core data models, identifiers, and configuration for retrieval."""

from .identifiers import normalize_doi, normalize_title
from .matching import jaccard, title_tokens
from .models import Citation, Paper, FieldEvidence, PaperProvenance
from .session import SessionIndex
from .settings import RetrievalSettings, load_dotenv_from_root

__all__ = [
    "Citation",
    "Paper",
    "FieldEvidence",
    "PaperProvenance",
    "SessionIndex",
    "RetrievalSettings",
    "load_dotenv_from_root",
    "normalize_doi",
    "normalize_title",
    "jaccard",
    "title_tokens",
]
