from __future__ import annotations

import re
from typing import Iterable, Set

from literature_retrieval_engine.core.identifiers import normalize_title


def title_tokens(title: str | None) -> Set[str]:
    """Tokenize a title into a normalized set of lowercase terms."""

    if not title:
        return set()

    normalized = normalize_title(title)
    return {token for token in re.split(r"[\W_]+", normalized) if token}


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Compute the Jaccard similarity between two collections of tokens."""

    set_a = set(a)
    set_b = set(b)

    if not set_a and not set_b:
        return 1.0

    union = set_a | set_b
    if not union:
        return 0.0

    return len(set_a & set_b) / len(union)
