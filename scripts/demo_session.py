#!/usr/bin/env python3
"""Demo script to exercise the `retrieval` package functions.

This script calls the high-level functions exported by the package and prints
concise summaries of their outputs. It's intended for interactive testing.
"""

from __future__ import annotations

import argparse
from typing import Any, Optional

from retrieval import (
    search_papers,
    search_paper_by_doi,
    search_paper_by_title,
    gather_evidence,
    search_citations,
    clear_papers_and_evidence,
)


def short_print_papers(papers: Any, label: str) -> None:
    print(f"--- {label}: {len(papers) if papers is not None else 0} results ---")
    if not papers:
        print("No results.")
        print()
        return
    for i, p in enumerate(papers[:5], start=1):
        title = getattr(p, "title", "<no title>")
        doi = getattr(p, "doi", "<no doi>")
        source = getattr(p, "source", "<no source>")
        print(f"{i}. {title} — DOI: {doi} — source: {source}")
    print()


def short_print_paper(paper: Optional[Any], label: str) -> None:
    print(f"--- {label}: {1 if paper else 0} result ---")
    if not paper:
        print("No results.")
        print()
        return
    title = getattr(paper, "title", "<no title>")
    doi = getattr(paper, "doi", "<no doi>")
    source = getattr(paper, "source", "<no source>")
    print(f"1. {title} — DOI: {doi} — source: {source}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo the retrieval package functions.")
    parser.add_argument("--query", default="graph neural networks", help="Free-text query for `search_papers` and `gather_evidence`")
    parser.add_argument("--doi", default="10.1038/nrn3241", help="Sample DOI for DOI-based calls and citation lookup")
    parser.add_argument("--title", default="Attention is all you need", help="Sample title for title lookup")
    args = parser.parse_args()

    # search_papers
    try:
        papers = search_papers(args.query, k=5)
        short_print_papers(papers, f"search_papers('{args.query}')")
    except Exception as e:  # pragma: no cover - demo runner
        print("search_papers error:", e)

    # search_paper_by_doi
    try:
        doi_res = search_paper_by_doi(args.doi)
        short_print_paper(doi_res, f"search_paper_by_doi('{args.doi}')")
    except Exception as e:  # pragma: no cover - demo runner
        print("search_paper_by_doi error:", e)

    # search_paper_by_title
    try:
        title_res = search_paper_by_title(args.title)
        short_print_paper(title_res, f"search_paper_by_title('{args.title}')")
    except Exception as e:  # pragma: no cover - demo runner
        print("search_paper_by_title error:", e)

    # gather_evidence
    try:
        evidence = gather_evidence(args.query)
        print(f"--- gather_evidence('{args.query}') returned {len(evidence) if evidence else 0} items ---")
        if evidence:
            for i, ev in enumerate(evidence[:5], start=1):
                print(f"{i}. {ev}")
        print()
    except Exception as e:  # pragma: no cover - demo runner
        print("gather_evidence error:", e)

    # search_citations
    try:
        citations = search_citations(args.doi)
        print(f"--- search_citations('{args.doi}') returned {len(citations) if citations else 0} items ---")
        if citations:
            for i, c in enumerate(citations[:5], start=1):
                title = getattr(c, "title", "<no title>")
                doi = getattr(c, "doi", "<no doi>")
                year = getattr(c, "year", "<no year>")
                authors = ", ".join(getattr(c, "authors", []) or [])
                print(f"{i}. {title} ({year}) — DOI: {doi} — Authors: {authors or '<no authors>'}")
        print()
    except Exception as e:  # pragma: no cover - demo runner
        print("search_citations error:", e)

    # clear_papers_and_evidence
    try:
        clear_papers_and_evidence()
        print("Cleared in-memory papers and evidence for this session.")
    except Exception as e:  # pragma: no cover - demo runner
        print("clear_papers_and_evidence error:", e)


if __name__ == "__main__":
    main()
