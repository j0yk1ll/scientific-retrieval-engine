from __future__ import annotations

from literature_retrieval_engine.core.identifiers import normalize_doi
from literature_retrieval_engine.core.models import Paper
from literature_retrieval_engine.providers.clients.crossref import CrossrefWork
from literature_retrieval_engine.providers.clients.datacite import DataCiteWork
from literature_retrieval_engine.providers.clients.openalex import OpenAlexWork
from literature_retrieval_engine.providers.clients.semanticscholar import SemanticScholarPaper


def crossref_work_to_paper(work: CrossrefWork) -> Paper:
    return Paper(
        paper_id=work.doi or work.title or "",
        title=work.title or "",
        doi=normalize_doi(work.doi),
        abstract=None,
        year=work.year,
        venue=work.venue,
        source="crossref",
        url=work.url,
        authors=work.authors,
    )


def datacite_work_to_paper(work: DataCiteWork) -> Paper:
    return Paper(
        paper_id=work.doi or work.title or "",
        title=work.title or "",
        doi=normalize_doi(work.doi),
        abstract=None,
        year=work.year,
        venue=work.venue,
        source="datacite",
        url=work.url,
        authors=work.authors,
    )


def openalex_work_to_paper(work: OpenAlexWork) -> Paper:
    return Paper(
        paper_id=work.openalex_id or work.doi or work.title or "",
        title=work.title or "",
        doi=normalize_doi(work.doi),
        abstract=work.abstract,
        year=work.year,
        venue=work.venue,
        source="openalex",
        url=work.openalex_url,
        pdf_url=work.pdf_url,
        is_oa=work.is_oa,
        authors=work.authors,
    )


def semanticscholar_paper_to_paper(record: SemanticScholarPaper) -> Paper:
    return Paper(
        paper_id=record.paper_id or record.doi or record.title or "",
        title=record.title or "",
        doi=normalize_doi(record.doi),
        abstract=record.abstract,
        year=record.year,
        venue=record.venue,
        source="semanticscholar",
        url=record.url,
        pdf_url=record.pdf_url,
        is_oa=bool(record.pdf_url),
        authors=record.authors,
    )
