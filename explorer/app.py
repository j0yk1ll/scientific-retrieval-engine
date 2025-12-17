"""Streamlit explorer for retrieval database contents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import streamlit as st

from retrieval.discovery.openalex import OpenAlexClient
from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine
from retrieval.parsing.citations import extract_citations
from retrieval.retrieval.types import ChunkSearchResult
from retrieval.storage.dao import get_all_papers, get_chunks_for_paper, get_papers_by_ids
from retrieval.storage.db import get_connection


@dataclass
class PaperDisplay:
    id: int
    title: str
    doi: str | None
    abstract: str | None
    published_at: str | None
    raw_data: dict[str, Any]


@dataclass
class ChunkDisplay:
    id: int
    chunk_order: int
    content: str
    citations: list[str]
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class CitationDisplay:
    index: str
    text: str
    url: str | None


@st.cache_resource
def get_config() -> RetrievalConfig:
    return RetrievalConfig()


@st.cache_resource
def get_engine() -> RetrievalEngine:
    return RetrievalEngine(get_config())


@st.cache_resource
def get_openalex_client() -> OpenAlexClient:
    return OpenAlexClient()


@st.cache_data(show_spinner=False)
def load_papers() -> list[PaperDisplay]:
    config = get_config()
    with get_connection(config.db_dsn) as conn:
        papers = get_all_papers(conn)
    return [
        PaperDisplay(
            id=paper.id,
            title=paper.title,
            doi=paper.doi,
            abstract=paper.abstract,
            published_at=paper.published_at.isoformat() if paper.published_at else None,
            raw_data=paper.model_dump(mode="json"),
        )
        for paper in papers
        if paper.id is not None
    ]


@st.cache_data(show_spinner=False)
def load_chunks(paper_id: int) -> list[ChunkDisplay]:
    config = get_config()
    with get_connection(config.db_dsn) as conn:
        chunks = get_chunks_for_paper(conn, paper_id)
    return [
        ChunkDisplay(
            id=chunk.id or idx,
            chunk_order=chunk.chunk_order,
            content=chunk.content,
            citations=extract_citations(chunk.content),
            raw_data=chunk.model_dump(mode="json"),
        )
        for idx, chunk in enumerate(chunks)
        if chunk.id is not None
    ]


def _format_citation_text(work_title: str | None, authors: list[str], venue: str | None, year: int | None, doi: str | None) -> str:
    parts: list[str] = []
    if authors:
        if len(authors) > 4:
            author_str = ", ".join(authors[:4]) + ", et al."
        else:
            author_str = ", ".join(authors)
        parts.append(author_str)
    if work_title:
        parts.append(work_title)

    venue_bits = [bit for bit in [venue, str(year) if year else None] if bit]
    if venue_bits:
        parts.append(" ".join(venue_bits))

    if doi:
        parts.append(f"doi:{doi}")

    return ", ".join(parts)


def _resolve_citations_via_openalex(doi: str | None, citation_indices: set[str]) -> dict[str, CitationDisplay]:
    if not doi or not citation_indices:
        return {}

    client = get_openalex_client()
    try:
        works, _ = client.search_works(doi, per_page=1, filters={"doi": doi})
    except Exception as exc:  # pragma: no cover - defensive against transient HTTP failures
        st.warning(f"Unable to query OpenAlex for citations: {exc}")
        return {}

    if not works:
        return {}

    try:
        source_work = client.get_work(works[0].openalex_id)
    except Exception as exc:  # pragma: no cover - defensive
        st.warning(f"Unable to load OpenAlex metadata for DOI {doi}: {exc}")
        return {}

    if not source_work.referenced_works:
        return {}

    index_to_id: dict[int, str] = {}
    for index_str in citation_indices:
        if not index_str.isdigit():
            continue
        index = int(index_str)
        if index < 1 or index > len(source_work.referenced_works):
            continue
        index_to_id[index] = source_work.referenced_works[index - 1]

    resolved: dict[str, CitationDisplay] = {}
    for index, ref_id in index_to_id.items():
        try:
            ref_work = client.get_work(ref_id)
        except Exception:  # pragma: no cover - defensive
            continue

        citation_text = _format_citation_text(
            ref_work.title,
            ref_work.authors,
            ref_work.venue,
            ref_work.year,
            ref_work.doi,
        )
        target_url = f"https://doi.org/{ref_work.doi}" if ref_work.doi else ref_work.openalex_url or None
        resolved[str(index)] = CitationDisplay(index=str(index), text=citation_text, url=target_url)

    return resolved


def _render_citation_list(citations: Sequence[str], citation_lookup: Mapping[str, CitationDisplay]) -> None:
    if not citations:
        return

    st.markdown("**Citations:**")
    for citation in citations:
        citation_info = citation_lookup.get(citation)
        if citation_info:
            label = f"[{citation_info.index}] {citation_info.text}"
            if citation_info.url:
                st.markdown(f"- [{label}]({citation_info.url})")
            else:
                st.markdown(f"- {label}")
        else:
            st.markdown(f"- [{citation}]")


def _render_chunk_list(chunks: Sequence[ChunkDisplay], citation_lookup: Mapping[str, CitationDisplay]) -> None:
    st.subheader("Chunks")
    if not chunks:
        st.info("No chunks have been generated for this paper yet.")
        return

    for chunk in chunks:
        with st.expander(f"Chunk {chunk.chunk_order + 1}"):
            st.markdown(f"**Chunk ID:** {chunk.id}")
            _render_citation_list(chunk.citations, citation_lookup)
            st.write(chunk.content)
            st.markdown("**Raw chunk JSON**")
            st.json(chunk.raw_data)


def _render_search_results(results: Iterable[ChunkSearchResult]) -> None:
    results = list(results)
    if not results:
        st.info("No results for this query yet.")
        return

    paper_ids = {result.paper_id for result in results}
    config = get_config()
    with get_connection(config.db_dsn) as conn:
        papers = get_papers_by_ids(conn, list(paper_ids))

    paper_lookup = {paper.id: paper for paper in papers if paper.id is not None}

    citation_cache: dict[int, dict[str, CitationDisplay]] = {}

    for result in results:
        paper = paper_lookup.get(result.paper_id)
        title = paper.title if paper else "Unknown paper"
        with st.expander(f"Paper {result.paper_id} · {title}"):
            st.markdown(f"**Chunk ID:** {result.chunk_id}")
            st.markdown(f"**Score:** {result.score:.4f}")
            st.markdown(f"**Chunk order:** {result.chunk_order}")

            citation_lookup: Mapping[str, CitationDisplay] = {}
            if result.citations and paper:
                citation_lookup = citation_cache.get(result.paper_id, {})
                if not citation_lookup:
                    citation_lookup = _resolve_citations_via_openalex(
                        paper.doi,
                        set(result.citations),
                    )
                    citation_cache[result.paper_id] = citation_lookup
            _render_citation_list(result.citations, citation_lookup)
            st.write(result.content)


def render_ingest_tab() -> None:
    """Render the paper ingestion tab."""
    st.header("Ingest Paper from URL")
    st.markdown("Index a paper by providing a direct PDF URL (e.g., from arXiv, bioRxiv, or any accessible PDF).")
    
    engine = get_engine()
    
    with st.form("ingest_form"):
        pdf_url = st.text_input(
            "PDF URL",
            placeholder="https://arxiv.org/pdf/2301.12345.pdf",
            help="Direct link to a PDF file"
        )
        
        st.markdown("**Optional Metadata**")
        col1, col2 = st.columns(2)
        
        with col1:
            title = st.text_input("Title", help="Leave blank to auto-detect from URL")
            doi = st.text_input("DOI", placeholder="10.1234/example")
        
        with col2:
            published_at = st.date_input("Publication Date", value=None)
            authors = st.text_input("Authors", placeholder="Comma-separated list")
        
        abstract = st.text_area("Abstract", height=100)
        
        submit = st.form_submit_button("Ingest Paper", type="primary")
        
        if submit:
            if not pdf_url.strip():
                st.error("Please provide a PDF URL")
            else:
                try:
                    with st.spinner("Ingesting paper... This may take a few minutes."):
                        author_list = [a.strip() for a in authors.split(",")] if authors.strip() else None
                        
                        paper = engine.ingest_from_url(
                            pdf_url=pdf_url.strip(),
                            title=title.strip() or None,
                            abstract=abstract.strip() or None,
                            doi=doi.strip() or None,
                            published_at=published_at if published_at else None,
                            authors=author_list,
                        )
                        
                        st.success(f"✅ Successfully ingested paper: **{paper.title}** (ID: {paper.id})")
                        st.info("The paper has been indexed and is now available for search.")
                        
                        # Clear the cache so the new paper shows up
                        load_papers.clear()
                        
                except Exception as e:
                    st.error(f"Failed to ingest paper: {str(e)}")
                    st.exception(e)


def render_app() -> None:
    st.set_page_config(page_title="Scientific Retrieval Explorer", layout="wide")
    st.title("Scientific Retrieval Explorer")
    st.caption("Index papers, inspect ingested content, and perform semantic search.")

    engine = get_engine()

    ingest_tab, paper_tab, search_tab = st.tabs(["Ingest Paper", "Papers & Chunks", "Semantic Search"])

    with ingest_tab:
        render_ingest_tab()

    with paper_tab:
        st.header("Papers")
        papers = load_papers()
        if not papers:
            st.warning("No papers have been ingested yet. Use the 'Ingest Paper' tab to add papers.")
        else:
            selection = st.selectbox(
                "Select a paper",
                options=papers,
                format_func=lambda p: f"{p.title} (ID {p.id})",
            )

            st.markdown(f"**Title:** {selection.title}")
            if selection.doi:
                st.markdown(f"**DOI:** {selection.doi}")
            if selection.published_at:
                st.markdown(f"**Published:** {selection.published_at}")
            if selection.abstract:
                st.markdown("**Abstract:**")
                st.write(selection.abstract)

            st.markdown("**Raw paper JSON**")
            st.json(selection.raw_data)

            chunks = load_chunks(selection.id)
            paper_citations = sorted({c for chunk in chunks for c in chunk.citations})
            citation_lookup = _resolve_citations_via_openalex(selection.doi, set(paper_citations))
            if paper_citations:
                st.markdown(
                    f"**Detected citations across chunks:** {', '.join(paper_citations)}"
                )
            else:
                st.markdown("**Detected citations across chunks:** None")
            _render_chunk_list(chunks, citation_lookup)

    with search_tab:
        st.header("Semantic search")
        query = st.text_input("Enter a query")
        top_k = st.slider("Top K results", min_value=1, max_value=20, value=5)
        if st.button("Search", type="primary"):
            with st.spinner("Searching index..."):
                results = engine.search(query, top_k=top_k)
            _render_search_results(results)


if __name__ == "__main__":
    render_app()
