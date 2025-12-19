from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Callable, Dict, Iterable, List, Set, Tuple

from .models import Chunk

TokenizeFn = Callable[[str], List[str]]


def default_tokenizer(
    text: str, *, stopwords: Set[str] | None = None, drop_empty: bool = True
) -> List[str]:
    tokens = re.split(r"[\W_]+", text.lower())

    if drop_empty:
        tokens = [token for token in tokens if token]

    if stopwords:
        tokens = [token for token in tokens if token not in stopwords]

    return tokens


class BM25Index:
    """Minimal BM25 implementation over a corpus of chunks."""

    def __init__(
        self,
        *,
        tokenizer: TokenizeFn | None = None,
        stopwords: Set[str] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
        include_query_term_frequency: bool = False,
    ) -> None:
        self.tokenizer: TokenizeFn = tokenizer or (
            lambda text: default_tokenizer(text, stopwords=stopwords)
        )
        self.k1 = k1
        self.b = b
        self.include_query_term_frequency = include_query_term_frequency
        self._chunks: List[Chunk] = []
        self._term_freqs: List[Counter[str]] = []
        self._doc_lengths: List[int] = []
        self._doc_freqs: Dict[str, int] = defaultdict(int)
        self._avg_doc_len: float = 0.0
        self._total_doc_len: int = 0

    def add(self, chunk: Chunk) -> None:
        tokens = self.tokenizer(chunk.text)
        term_freq = Counter(tokens)

        self._chunks.append(chunk)
        self._term_freqs.append(term_freq)
        doc_len = len(tokens)
        self._doc_lengths.append(doc_len)
        self._total_doc_len += doc_len

        for token in term_freq:
            self._doc_freqs[token] += 1

        self._avg_doc_len = self._total_doc_len / len(self._doc_lengths)

    def add_many(self, chunks: Iterable[Chunk]) -> None:
        for chunk in chunks:
            self.add(chunk)

    def search(self, query: str, *, k: int = 10) -> List[Tuple[Chunk, float]]:
        if not query or not self._chunks:
            return []

        query_tokens = self.tokenizer(query)
        token_counts = (
            Counter(query_tokens) if self.include_query_term_frequency else set(query_tokens)
        )
        scores: List[Tuple[Chunk, float]] = []

        for idx, chunk in enumerate(self._chunks):
            score = 0.0
            if isinstance(token_counts, Counter):
                for token, query_tf in token_counts.items():
                    score += self._score_token(token, idx) * query_tf
            else:
                for token in token_counts:
                    score += self._score_token(token, idx)
            if score:
                scores.append((chunk, score))

        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:k]

    def _score_token(self, token: str, doc_idx: int) -> float:
        tf = self._term_freqs[doc_idx].get(token, 0)
        if tf == 0:
            return 0.0

        df = self._doc_freqs.get(token, 0)
        if df == 0:
            return 0.0

        idf = math.log(1 + (len(self._chunks) - df + 0.5) / (df + 0.5))
        doc_len = self._doc_lengths[doc_idx]
        denom = tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_len)
        return idf * (tf * (self.k1 + 1)) / denom


__all__ = ["BM25Index", "default_tokenizer"]
