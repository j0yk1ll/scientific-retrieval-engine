"""Utilities for extracting inline citation markers from text."""

from __future__ import annotations

import re
from itertools import chain
from typing import Iterable, List

_CITATION_PATTERN = re.compile(r"\[(?P<body>[^\]]+)\]")
_RANGE_PATTERN = re.compile(r"^(?P<start>\d+)\s*-\s*(?P<end>\d+)$")


def _expand_range(token: str) -> Iterable[str]:
    match = _RANGE_PATTERN.match(token)
    if not match:
        return []

    start = int(match.group("start"))
    end = int(match.group("end"))
    if start > end:
        start, end = end, start
    return (str(value) for value in range(start, end + 1))


def extract_citations(text: str) -> List[str]:
    """Return a de-duplicated list of inline citation markers found in *text*.

    The function currently targets numeric citation markers enclosed in square
    brackets (e.g., ``[3]``, ``[2, 5]``, or ``[7-9]``). Ranges are expanded and
    the original ordering of first appearance is preserved.
    """

    seen: set[str] = set()
    citations: list[str] = []

    for match in _CITATION_PATTERN.finditer(text):
        body = match.group("body")
        tokens = [token.strip() for token in re.split(r",|;", body) if token.strip()]

        expanded_tokens = chain.from_iterable(
            _expand_range(token) if _RANGE_PATTERN.match(token) else [token]
            for token in tokens
        )

        for token in expanded_tokens:
            if not token.isdigit():
                continue
            if token in seen:
                continue
            seen.add(token)
            citations.append(token)

    return citations
