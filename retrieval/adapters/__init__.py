"""Adapters for mapping provider responses into retrieval models."""

from .paper_adapters import (
    crossref_work_to_paper,
    datacite_work_to_paper,
    openalex_work_to_paper,
    semanticscholar_paper_to_paper,
)

__all__ = [
    "crossref_work_to_paper",
    "datacite_work_to_paper",
    "openalex_work_to_paper",
    "semanticscholar_paper_to_paper",
]
