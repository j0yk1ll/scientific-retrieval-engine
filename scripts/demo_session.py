#!/usr/bin/env python3
"""Demo script to exercise the `literature-retrieval-engine` package functions.

This script calls the high-level functions exported by the package and prints
concise summaries of their outputs. It's intended for interactive testing.
"""

from __future__ import annotations

import argparse
import pprint
from typing import Any, Optional

from literature_retrieval_engine import (
    search_papers,
    search_paper_by_doi,
    search_paper_by_title,
    gather_evidence,
    search_citations,
    clear_papers_and_evidence,
)


def _truncate_string(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _normalize_for_print(obj: Any, max_len: int) -> Any:
    """Recursively convert the object into primitives and truncate long strings.

    - Strings get truncated to `max_len` characters.
    - dicts/lists/tuples are walked recursively.
    - objects with `__dict__` are converted to their dict.
    - other objects are converted via `repr()` and truncated.
    """
    if isinstance(obj, str):
        return _truncate_string(obj, max_len)
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, dict):
        return {k: _normalize_for_print(v, max_len) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        seq = [_normalize_for_print(v, max_len) for v in obj]
        return type(obj)(seq) if not isinstance(obj, set) else set(seq)
    # Try to use __dict__ for custom objects
    try:
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            return {type(obj).__name__: _normalize_for_print(d, max_len)}
    except Exception:
        pass
    # Fallback to repr()
    return _truncate_string(repr(obj), max_len)


def print_raw_truncated(obj: Any, label: str, max_len: int = 200) -> None:
    """Print a 'raw' view of `obj` while truncating long strings for readability."""
    print(f"--- {label}: {len(obj) if hasattr(obj, '__len__') and obj is not None else 0} results ---")
    norm = _normalize_for_print(obj, max_len)
    print(pprint.pformat(norm, width=120))
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


def _format_author(name: str) -> str:
    """Convert various author name formats into 'Last, I. I.' style.

    Handles names like 'First Middle Last' and 'Last, First Middle'.
    """
    if not name or not name.strip():
        return ""
    name = name.strip()
    # If already in 'Last, First' form
    if "," in name:
        last, rest = [p.strip() for p in name.split(",", 1)]
        parts = rest.split()
        initials = " ".join((p[0].upper() + ".") for p in parts if p)
        return f"{last}, {initials}" if initials else last

    parts = name.split()
    if len(parts) == 1:
        return parts[0]
    last = parts[-1]
    given = parts[:-1]
    initials = " ".join((p[0].upper() + ".") for p in given if p)
    return f"{last}, {initials}" if initials else last


def _format_authors(authors: list[str]) -> str:
    """Join formatted authors with commas and an Oxford comma + ampersand before last."""
    if not authors:
        return "<no authors>"
    formatted = [_format_author(a) for a in authors if a]
    if not formatted:
        return "<no authors>"
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]} & {formatted[1]}"
    return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo the retrieval package functions.")
    parser.add_argument("--query", default="graph neural networks", help="Free-text query for `search_papers` and `gather_evidence`")
    parser.add_argument("--doi", default="10.1038/nrn3241", help="Sample DOI for DOI-based calls and citation lookup")
    parser.add_argument("--title", default="Attention is all you need", help="Sample title for title lookup")
    args = parser.parse_args()

    # search_papers
    try:
        papers = search_papers(args.query, k=5)
        print_raw_truncated(papers, f"search_papers('{args.query}')")
    except Exception as e:  # pragma: no cover - demo runner
        print("search_papers error:", e)

    # search_paper_by_doi
    try:
        doi_res = search_paper_by_doi(args.doi)
        print(f"--- search_paper_by_doi('{args.doi}'): {1 if doi_res else 0} result ---")
        pprint.pprint(doi_res, width=120)
        print()
    except Exception as e:  # pragma: no cover - demo runner
        print("search_paper_by_doi error:", e)

    # search_paper_by_title
    try:
        title_res = search_paper_by_title(args.title)
        print(f"--- search_paper_by_title('{args.title}'): {1 if title_res else 0} result ---")
        pprint.pprint(title_res, width=120)
        print()
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
                year = getattr(c, "year", None)
                venue = getattr(c, "venue", None) or getattr(c, "source", None) or ""
                authors = getattr(c, "authors", []) or []
                auth_str = _format_authors(authors)
                year_part = f" ({year})" if year else ""
                venue_part = f" {venue}," if venue else ""
                # Compose citation similar to: Authors (Year). Title. Venue, volume, page. DOI: ...
                print(f"{i}. {auth_str}{year_part}. {title}.{venue_part} DOI: {doi}")
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
