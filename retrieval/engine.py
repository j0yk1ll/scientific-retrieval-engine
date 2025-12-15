"""Primary entrypoint for the retrieval system."""

from pathlib import Path
from typing import Iterable, List, Sequence

from .config import RetrievalConfig
from .exceptions import ConfigError


class RetrievalEngine:
    """Coordinates acquisition, parsing, indexing, and retrieval."""

    def __init__(self, config: RetrievalConfig) -> None:
        self.config = config
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for path in (self.config.data_dir, self.config.index_dir):
            if path.exists() and not path.is_dir():
                raise ConfigError(f"Configured path is not a directory: {path}")
            path.mkdir(parents=True, exist_ok=True)

    def discover(self, query: str) -> Sequence[str]:
        """Discover candidate papers using metadata sources."""

        raise NotImplementedError

    def acquire_full_text(self, work_identifier: str) -> Path:
        """Download full-text content for a work and return the saved path."""

        raise NotImplementedError

    def parse_document(self, pdf_path: Path) -> str:
        """Convert a PDF to TEI XML using GROBID."""

        raise NotImplementedError

    def chunk_document(self, tei_xml: str) -> List[str]:
        """Chunk TEI XML into deterministic passages ready for indexing."""

        raise NotImplementedError

    def index_chunks(self, chunks: Iterable[str]) -> None:
        """Index chunks using ColBERT."""

        raise NotImplementedError

    def search(self, query: str, top_k: int = 10) -> Sequence[str]:
        """Search the ColBERT index and return results."""

        raise NotImplementedError
