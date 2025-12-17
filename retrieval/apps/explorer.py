"""Streamlit explorer for retrieval database contents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import streamlit as st

from retrieval import RetrievalConfig, RetrievalEngine
from retrieval.retrieval.types import ChunkSearchResult
from retrieval.storage.dao import get_all_papers, get_chunks_for_paper, get_papers_by_ids
from retrieval.storage.db import get_connection


@dataclass
class PaperDisplay:
    id: int
    title: str
    doi: str | None
    abstract: str | None


@st.cache_resource
def get_config() -> RetrievalConfig:
    return RetrievalConfig()


@st.cache_resource
def get_engine() -> RetrievalEngine:
    return RetrievalEngine(get_config())


@st.cache_data(show_spinner=False)
def load_papers() -> list[PaperDisplay]:
    config = get_config()
    with get_connection(config.db_dsn) as conn:
        papers = get_all_papers(conn)
    return [
        PaperDisplay(id=paper.id, title=paper.title, doi=paper.doi, abstract=paper.abstract)
        for paper in papers
        if paper.id is not None
    ]


@st.cache_data(show_spinner=False)
def load_chunks(paper_id: int) -> Sequence[str]:
    config = get_config()
    with get_connection(config.db_dsn) as conn:
        chunks = get_chunks_for_paper(conn, paper_id)
    return [chunk.content for chunk in chunks]


def _render_chunk_list(chunks: Sequence[str]) -> None:
    st.subheader("Chunks")
    if not chunks:
        st.info("No chunks have been generated for this paper yet.")
        return

    for idx, chunk in enumerate(chunks, start=1):
        with st.expander(f"Chunk {idx}"):
            st.write(chunk)


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

    for result in results:
        paper = paper_lookup.get(result.paper_id)
        title = paper.title if paper else "Unknown paper"
        with st.expander(f"Paper {result.paper_id} · {title}"):
            st.markdown(f"**Chunk ID:** {result.chunk_id}")
            st.markdown(f"**Score:** {result.score:.4f}")
            st.markdown(f"**Chunk order:** {result.chunk_order}")
            st.write(result.content)


def render_app() -> None:
    st.set_page_config(page_title="Scientific Retrieval Explorer", layout="wide")
    st.title("Scientific Retrieval Explorer")
    st.caption("Inspect ingested papers, their chunks, and semantic search results.")

    engine = get_engine()

    paper_tab, search_tab = st.tabs(["Papers & Chunks", "Semantic Search"])

    with paper_tab:
        st.header("Papers")
        papers = load_papers()
        if not papers:
            st.warning("No papers have been ingested yet.")
        else:
            selection = st.selectbox(
                "Select a paper",
                options=papers,
                format_func=lambda p: f"{p.title} (ID {p.id})",
            )

            st.markdown(f"**Title:** {selection.title}")
            if selection.doi:
                st.markdown(f"**DOI:** {selection.doi}")
            if selection.abstract:
                st.markdown("**Abstract:**")
                st.write(selection.abstract)

            chunks = load_chunks(selection.id)
            _render_chunk_list(chunks)

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
