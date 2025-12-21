from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

from literature_retrieval_engine.core.models import EvidenceChunk, Paper
from literature_retrieval_engine.providers.clients.grobid import GrobidClient
from literature_retrieval_engine.services.full_text_resolver_service import FullTextResolverService
from literature_retrieval_engine.services.paper_chunker_service import PaperChunkerService

logger = logging.getLogger(__name__)


@dataclass
class EvidenceConfig:
    max_tokens: int = 400
    max_chars: int = 2000
    max_chunks_per_paper: Optional[int] = None


class EvidenceService:
    """
    Turn papers into citeable evidence chunks.

    If a PDF + GROBID are available, we chunk full text.
    Otherwise we fall back to a single chunk made from title + abstract.
    """

    def __init__(
        self,
        *,
        session: requests.Session,
        grobid: Optional[GrobidClient] = None,
        full_text_resolver: Optional[FullTextResolverService] = None,
        config: Optional[EvidenceConfig] = None,
    ) -> None:
        self.session = session
        self.grobid = grobid
        self.full_text_resolver = full_text_resolver
        self.config = config or EvidenceConfig()

    def gather(self, papers: List[Paper]) -> List[EvidenceChunk]:
        out: List[EvidenceChunk] = []
        for paper in papers:
            out.extend(self._paper_to_evidence(paper))
        return out

    def _paper_to_evidence(self, paper: Paper) -> List[EvidenceChunk]:
        resolved_pdf_url = paper.resolved_pdf_url
        if not resolved_pdf_url and self.full_text_resolver:
            resolution = self.full_text_resolver.resolve(paper)
            best = resolution.best
            if best:
                resolved_pdf_url = best.pdf_url or getattr(best, "url", None)
        if not resolved_pdf_url:
            resolved_pdf_url = paper.pdf_url

        # Full-text path (PDF -> GROBID -> TEI -> chunks)
        if self.grobid and resolved_pdf_url:
            pdf_bytes = self._download_pdf(resolved_pdf_url)
            if pdf_bytes:
                try:
                    tei = self.grobid.process_fulltext(pdf_bytes)
                    chunker = PaperChunkerService(paper.paper_id or (paper.doi or paper.title), tei)
                    paper_chunks = chunker.chunk(
                        max_tokens=self.config.max_tokens,
                        max_chars=self.config.max_chars,
                    )
                    if self.config.max_chunks_per_paper is not None:
                        paper_chunks = paper_chunks[: self.config.max_chunks_per_paper]

                    return [
                        EvidenceChunk(
                            chunk_id=pc.chunk_id,
                            paper_id=paper.paper_id,
                            paper_title=paper.title,
                            paper_doi=paper.doi,
                            paper_authors=paper.authors,
                            paper_year=paper.year,
                            section=pc.section,
                            content=pc.content,
                            paper_url=paper.url,
                            pdf_url=resolved_pdf_url,
                            metadata={
                                "token_count": pc.token_count,
                                "section_index": pc.section_index,
                                "stream_start_char": pc.stream_start_char,
                                "stream_end_char": pc.stream_end_char,
                                "chunker_version": PaperChunkerService.VERSION,
                            },
                        )
                        for pc in paper_chunks
                    ]
                except Exception as exc:
                    logger.debug(
                        "Full-text chunking failed (%s); falling back to title/abstract",
                        type(exc).__name__,
                        extra={
                            "doi": paper.doi,
                            "title": paper.title,
                            "pdf_url": resolved_pdf_url,
                        },
                        exc_info=exc,
                    )

        # Fallback path: title + abstract (still citeable)
        title = (paper.title or "").strip()
        abstract = (paper.abstract or "").strip()
        content = "\n\n".join([part for part in (title, abstract) if part]).strip()
        if not content:
            return []

        return [
            EvidenceChunk(
                chunk_id=f"{paper.paper_id or paper.doi or 'paper'}-fallback-1",
                paper_id=paper.paper_id,
                paper_title=paper.title,
                paper_doi=paper.doi,
                paper_authors=paper.authors,
                paper_year=paper.year,
                section="Title/Abstract",
                content=content,
                paper_url=paper.url,
                pdf_url=resolved_pdf_url,
                metadata={"fallback": True},
            )
        ]

    def _download_pdf(self, url: str) -> Optional[bytes]:
        try:
            resp = self.session.get(
                url,
                timeout=20,
                headers={"Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1"},
                allow_redirects=True,
            )
            resp.raise_for_status()
            if not resp.content:
                return None
            # Best-effort PDF check: either header says PDF, or bytes start with %PDF
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "pdf" in ctype or resp.content[:4] == b"%PDF":
                return resp.content
        except Exception:
            return None
        return None
