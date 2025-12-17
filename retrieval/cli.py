"""Command-line utilities for the retrieval engine."""

from __future__ import annotations

import argparse
from datetime import date
from typing import Any

from retrieval import RetrievalConfig, RetrievalEngine


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - user input validation
        raise argparse.ArgumentTypeError(
            "Dates must use ISO format (YYYY-MM-DD)"
        ) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Utilities for the Scientific Retrieval Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_url = subparsers.add_parser(
        "ingest-url", help="Ingest a paper directly from a PDF URL"
    )
    ingest_url.add_argument("url", help="Direct URL to a PDF (e.g., https://arxiv.org/pdf/...)")
    ingest_url.add_argument("--title", help="Optional title to store for the paper", default=None)
    ingest_url.add_argument("--doi", help="Optional DOI metadata", default=None)
    ingest_url.add_argument("--abstract", help="Optional abstract metadata", default=None)
    ingest_url.add_argument(
        "--published-at",
        help="Publication date in YYYY-MM-DD format",
        type=_parse_date,
        default=None,
    )
    ingest_url.add_argument(
        "--author",
        help="Repeatable author metadata entries",
        action="append",
        dest="authors",
        default=None,
    )

    return parser


def _run_ingest_url(args: argparse.Namespace) -> None:
    config = RetrievalConfig()
    engine = RetrievalEngine(config)
    paper = engine.ingest_from_url(
        args.url,
        title=args.title,
        abstract=args.abstract,
        doi=args.doi,
        published_at=args.published_at,
        authors=args.authors,
    )
    print(f"Ingested paper ID {paper.id}: {paper.title}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    commands: dict[str, Any] = {
        "ingest-url": _run_ingest_url,
    }

    handler = commands.get(args.command)
    if handler is None:
        parser.error("Unknown command")
        return 1

    handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
