"""Retrieval engine package scaffold.

This module ensures environment variables from a local `.env` file are
loaded early via `python-dotenv` so downstream modules and `pydantic`
settings can pick them up.
"""

from dotenv import load_dotenv

# Load environment variables from a `.env` file in the repository root.
# Do not override existing environment variables unless explicitly needed.
load_dotenv(dotenv_path=".env", override=False)

from .models import Citation, Paper
from .api import (
    clear_papers_and_evidence,
    gather_evidence,
    search_citations,
    search_paper_by_doi,
    search_paper_by_title,
    search_papers,
)

__all__ = [
    "Paper",
    "Citation",
    "search_papers",
    "search_paper_by_doi",
    "search_paper_by_title",
    "gather_evidence",
    "search_citations",
    "clear_papers_and_evidence",
]
