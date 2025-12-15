"""Utilities for normalizing and matching titles across providers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from .preprints.base import PreprintResult


def _normalize(title: str) -> list[str]:
    sanitized = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    return [token for token in sanitized.split() if token]


def token_ratio(query_tokens: list[str], candidate_tokens: list[str]) -> float:
    """Compute a symmetric token overlap ratio between two token lists."""

    if not query_tokens or not candidate_tokens:
        return 0.0

    query_set = set(query_tokens)
    candidate_set = set(candidate_tokens)
    overlap = len(query_set & candidate_set)
    union = len(query_set | candidate_set)
    return overlap / union if union else 0.0


@dataclass
class TitleMatchResult:
    title: str
    score: float
    candidate: PreprintResult


class TitleMatcher:
    """Lightweight token-based matcher for selecting preprints by title."""

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold

    def score(self, query_title: str, candidate_title: str) -> float:
        return token_ratio(_normalize(query_title), _normalize(candidate_title))

    def pick_best(self, query_title: str, candidates: Iterable[PreprintResult]) -> Optional[PreprintResult]:
        best_match: Optional[TitleMatchResult] = None
        for candidate in candidates:
            score = self.score(query_title, candidate.title)
            if score < self.threshold:
                continue
            if best_match is None or score > best_match.score:
                best_match = TitleMatchResult(title=candidate.title, score=score, candidate=candidate)
        return best_match.candidate if best_match else None
