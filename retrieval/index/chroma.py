"""Wrapper around the ``chromadb`` package for local vector search."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from retrieval.index.export import ChunkRow

ChromaSearchResult = Tuple[str, float]


@dataclass
class ChromaIndex:
    """Build and search a ChromaDB collection.

    The heavy ``chromadb`` dependency is imported lazily so that modules can be
    imported in environments where it is not available. Any operation that
    requires Chroma will raise :class:`IndexError` with installation
    instructions when the dependency is missing.
    """

    index_dir: Path
    collection_name: str
    chroma_url: str
    embedding_function: object | None = None

    def __post_init__(self) -> None:
        self.index_dir = Path(self.index_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_index(self, chunks: Iterable[ChunkRow]) -> Path:
        """Persist chunks and rebuild the Chroma collection."""

        Client, DefaultEmbeddingFunction, errors_mod = self._import_chromadb()

        # Use HTTP client for remote ChromaDB server
        client = Client(host=self.chroma_url)

        try:
            client.delete_collection(self.collection_name)
        except getattr(errors_mod, "InvalidCollectionException", Exception):
            # If the collection does not yet exist, nothing to delete.
            pass

        collection = client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function or DefaultEmbeddingFunction(),
        )

        chunk_list = list(chunks)
        if chunk_list:
            ids = [chunk_id for chunk_id, _text in chunk_list]
            documents = [text for _chunk_id, text in chunk_list]
            metadatas = [{"chunk_id": chunk_id} for chunk_id in ids]
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        return self.index_dir

    def add_documents(self, chunks: Iterable[ChunkRow]) -> None:
        """Add or update chunks in the Chroma collection without rebuilding."""

        Client, DefaultEmbeddingFunction, _errors_mod = self._import_chromadb()

        # Use HTTP client for remote ChromaDB server
        client = Client(host=self.chroma_url)
        collection = client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function or DefaultEmbeddingFunction(),
        )

        chunk_list = list(chunks)
        if chunk_list:
            ids = [chunk_id for chunk_id, _text in chunk_list]
            documents = [text for _chunk_id, text in chunk_list]
            metadatas = [{"chunk_id": chunk_id} for chunk_id in ids]
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def search(self, query: str, *, top_k: int = 10) -> List[ChromaSearchResult]:
        """Search the Chroma collection and return ``(chunk_id, score)`` pairs."""

        Client, DefaultEmbeddingFunction, _errors_mod = self._import_chromadb()

        # Use HTTP client for remote ChromaDB server
        client = Client(host=self.chroma_url)
        collection = client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function or DefaultEmbeddingFunction(),
        )

        results = collection.query(query_texts=[query], n_results=top_k)
        ids: Sequence[str] = results.get("ids", [[]])[0] if results.get("ids") else []
        distances: Sequence[float] = (
            results.get("distances", [[]])[0] if results.get("distances") else []
        )

        scores: List[ChromaSearchResult] = []
        for chunk_id, distance in zip(ids, distances):
            # Convert distance to similarity score in (0, 1]
            # Using 1/(1+d) ensures positive scores for any non-negative distance
            similarity = 1.0 / (1.0 + float(distance)) if distance is not None else 0.0
            scores.append((chunk_id, similarity))
        return scores

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _import_chromadb(self):
        try:
            chromadb = importlib.import_module("chromadb")
            embedding_functions = importlib.import_module(
                "chromadb.utils.embedding_functions"
            )
            errors_mod = importlib.import_module("chromadb.errors")
            
            # Always use HttpClient for remote ChromaDB server
            Client = getattr(chromadb, "HttpClient")
            
            DefaultEmbeddingFunction = getattr(
                embedding_functions, "DefaultEmbeddingFunction"
            )
            return Client, DefaultEmbeddingFunction, errors_mod
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised in tests
            raise IndexError(
                "ChromaDB backend requires the 'chromadb' package. Install with "
                "`pip install chromadb sentence-transformers` to enable indexing and search."
            ) from exc
