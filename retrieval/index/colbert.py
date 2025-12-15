"""Wrapper around the ``colbert-ai`` package."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, List, Sequence, Tuple

from retrieval.index.export import ChunkRow, export_chunks_tsv

ColbertSearchResult = Tuple[str, float]


@dataclass
class ColbertIndex:
    """Thin wrapper to build and search a ColBERT index.

    The heavy ``colbert-ai`` dependency is imported lazily so that modules can
    be imported in environments where it is not available. Any operation that
    requires ColBERT will raise :class:`IndexError` with installation
    instructions when the dependency is missing.
    """

    index_dir: Path
    index_name: str
    checkpoint: str = "colbert-ir/colbertv2.0"

    def __post_init__(self) -> None:
        self.index_dir = Path(self.index_dir)
        self.collection_path = self.index_dir / f"{self.index_name}.tsv"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_index(self, chunks: Iterable[ChunkRow]) -> Path:
        """Export chunks to TSV and trigger ColBERT indexing."""

        Indexer, _Searcher, Run, RunConfig, ColBERTConfig = self._import_colbert()

        export_chunks_tsv(chunks, self.collection_path)

        colbert_config = ColBERTConfig(
            root=str(self.index_dir),
            index_root=str(self.index_dir),
        )
        run_config = RunConfig(experiment="colbert-index", nranks=1)

        self.index_dir.mkdir(parents=True, exist_ok=True)

        with Run().context(run_config):
            indexer = Indexer(checkpoint=self.checkpoint, config=colbert_config)
            indexer.index(
                name=self.index_name,
                collection=str(self.collection_path),
                overwrite=True,
            )

        return self.index_dir / self.index_name

    def search(self, query: str, *, top_k: int = 10) -> List[ColbertSearchResult]:
        """Search the ColBERT index and return ``(chunk_id, score)`` pairs."""

        _Indexer, Searcher, Run, RunConfig, ColBERTConfig = self._import_colbert()

        colbert_config = ColBERTConfig(
            root=str(self.index_dir),
            index_root=str(self.index_dir),
        )
        run_config = RunConfig(experiment="colbert-search", nranks=1)

        chunk_ids = self._load_chunk_ids()

        with Run().context(run_config):
            searcher = Searcher(index=self.index_name, config=colbert_config)
            ranking = searcher.search(query, k=top_k)

        docids, scores = self._extract_results(ranking)
        results: List[ColbertSearchResult] = []
        for doc_id, score in zip(docids, scores):
            if doc_id < 0 or doc_id >= len(chunk_ids):
                continue
            results.append((chunk_ids[doc_id], float(score)))
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _import_colbert(self):
        try:
            colbert = importlib.import_module("colbert")
            infra = importlib.import_module("colbert.infra")
            Indexer = getattr(colbert, "Indexer")
            Searcher = getattr(colbert, "Searcher")
            Run = getattr(infra, "Run")
            RunConfig = getattr(infra, "RunConfig")
            ColBERTConfig = getattr(infra, "ColBERTConfig")
            return Indexer, Searcher, Run, RunConfig, ColBERTConfig
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised in tests
            raise IndexError(
                "ColBERT backend requires the 'colbert-ai' package. Install with "
                "`pip install colbert-ai` to enable indexing and search."
            ) from exc

    def _load_chunk_ids(self) -> List[str]:
        if not self.collection_path.exists():
            raise FileNotFoundError(
                f"Collection file not found. Expected at: {self.collection_path}"
            )

        chunk_ids: List[str] = []
        with self.collection_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                chunk_id, _text = line.rstrip("\n").split("\t", maxsplit=1)
                chunk_ids.append(chunk_id)
        return chunk_ids

    @staticmethod
    def _extract_results(ranking: object) -> Tuple[Sequence[int], Sequence[float]]:
        """Best-effort extraction of docids/scores from ColBERT ranking output."""

        if isinstance(ranking, SimpleNamespace):
            docids = getattr(ranking, "docids", None)
            scores = getattr(ranking, "scores", None)
        else:
            docids = getattr(ranking, "docids", None)
            scores = getattr(ranking, "scores", None)

        if docids is None or scores is None:
            raise ValueError("Unsupported ranking format returned by ColBERT")

        return list(docids), list(scores)
