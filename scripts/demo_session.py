#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Iterable, List, Tuple

from retrieval.core.models import Paper
from retrieval.providers.clients.base import ClientError
from retrieval.providers.clients.semanticscholar import DEFAULT_FIELDS
from retrieval.services.search_service import PaperSearchService

SAMPLE_QUERIES = [
    "contrastive self-supervised pre-training",
    "semi-supervised learning with graph neural networks",
    "data-driven discovery of differential equations",
    "large language model retrieval augmented generation",
    "protein structure prediction with transformers",
]


def _format_paper(paper: Paper, rank: int) -> str:
    title = paper.title or "(untitled)"
    year = f" ({paper.year})" if paper.year else ""
    doi = f" DOI: {paper.doi}" if paper.doi else ""
    return f"{rank:>2}. {title}{year} [{paper.source}]{doi}"


def _print_results(results: Iterable[Paper]) -> None:
    for idx, paper in enumerate(results, start=1):
        print(_format_paper(paper, idx))


def _count_groups(service: PaperSearchService, papers: List[Paper]) -> Tuple[int, int]:
    grouped: dict[str, list[Paper]] = {}
    order: list[str] = []
    service._append_to_groups(papers, grouped, order)
    return len(grouped), len(papers)


def _debug_counts(
    service: PaperSearchService,
    query: str,
    *,
    k: int,
    min_year: int | None,
    max_year: int | None,
) -> None:
    per_pass = k * service.candidate_multiplier
    date_filters = service._build_openalex_filters(min_year=min_year, max_year=max_year)
    quoted_query = service._quote_phrase(query)

    try:
        openalex_results, _ = service.openalex.search_works(
            quoted_query, per_page=per_pass, filters=date_filters or None
        )
    except ClientError as exc:
        print(f"OpenAlex base pass failed: {exc}")
        openalex_results = []
    print(f"OpenAlex base pass: {len(openalex_results)}")

    if service.enable_openalex_no_stem_pass:
        openalex_no_stem_filters = {
            **date_filters,
            "title_and_abstract.search.no_stem": quoted_query,
        }
        try:
            openalex_no_stem, _ = service.openalex.search_works(
                "", per_page=per_pass, filters=openalex_no_stem_filters
            )
        except ClientError as exc:
            print(f"OpenAlex no-stem pass failed: {exc}")
            openalex_no_stem = []
        print(f"OpenAlex no-stem pass: {len(openalex_no_stem)}")
    else:
        print("OpenAlex no-stem pass: disabled")

    try:
        if hasattr(service.semanticscholar, "search_papers_advanced"):
            semantic_records = service.semanticscholar.search_papers_advanced(
                quoted_query,
                limit=per_pass,
                min_year=min_year,
                max_year=max_year,
                fields=DEFAULT_FIELDS,
            )
        else:
            semantic_records = service.semanticscholar.search_papers(
                quoted_query,
                limit=per_pass,
                min_year=min_year,
                max_year=max_year,
                fields=DEFAULT_FIELDS,
            )
    except ClientError as exc:
        print(f"Semantic Scholar base pass failed: {exc}")
        semantic_records = []
    print(f"Semantic Scholar base pass: {len(semantic_records)}")

    if service.enable_semanticscholar_hyphen_pass and "-" in query:
        normalized_phrase = service._quote_phrase(service._normalize_hyphens(query))
        try:
            if hasattr(service.semanticscholar, "search_papers_advanced"):
                semantic_normalized = service.semanticscholar.search_papers_advanced(
                    normalized_phrase,
                    limit=per_pass,
                    min_year=min_year,
                    max_year=max_year,
                    fields=DEFAULT_FIELDS,
                )
            else:
                semantic_normalized = service.semanticscholar.search_papers(
                    normalized_phrase,
                    limit=per_pass,
                    min_year=min_year,
                    max_year=max_year,
                    fields=DEFAULT_FIELDS,
                )
        except ClientError as exc:
            print(f"Semantic Scholar hyphen pass failed: {exc}")
            semantic_normalized = []
        print(f"Semantic Scholar hyphen pass: {len(semantic_normalized)}")
    elif "-" in query:
        print("Semantic Scholar hyphen pass: disabled")


def run_demo(args: argparse.Namespace) -> None:
    service = PaperSearchService(
        candidate_multiplier=args.candidate_multiplier,
        enable_openalex_no_stem_pass=not args.disable_openalex_no_stem,
        enable_semanticscholar_hyphen_pass=not args.disable_semantic_hyphen,
    )

    queries = args.queries or SAMPLE_QUERIES
    for query in queries:
        print("=" * 80)
        print(f"Query: {query}")
        results, raw_results = service.search_with_raw(
            query,
            k=args.k,
            min_year=args.min_year,
            max_year=args.max_year,
            include_raw=True,
        )
        print("Top reranked results:")
        _print_results(results)
        merged_count, raw_count = _count_groups(service, raw_results)
        print(f"Merged groups: {merged_count} from {raw_count} raw records")

        if args.debug:
            print("-- Debug pass counts --")
            _debug_counts(
                service,
                query,
                k=args.k,
                min_year=args.min_year,
                max_year=args.max_year,
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo retrieval search session")
    parser.add_argument("queries", nargs="*", help="Queries to run")
    parser.add_argument("--k", type=int, default=5, help="Number of results to keep")
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=5,
        help="Multiplier for upstream candidate fetches",
    )
    parser.add_argument("--min-year", type=int, help="Minimum publication year")
    parser.add_argument("--max-year", type=int, help="Maximum publication year")
    parser.add_argument(
        "--disable-openalex-no-stem",
        action="store_true",
        help="Disable OpenAlex no-stem pass",
    )
    parser.add_argument(
        "--disable-semantic-hyphen",
        action="store_true",
        help="Disable Semantic Scholar hyphen pass",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print per-pass counts and merged group totals",
    )
    return parser


if __name__ == "__main__":
    run_demo(build_parser().parse_args())
