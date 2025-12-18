from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from retrieval.chunking import GrobidChunker
from retrieval.hybrid import Chunk, Embedder
from retrieval.identifiers import normalize_doi
from retrieval.models import Paper, PaperEvidence, PaperProvenance


@dataclass
class CachedPaperArtifacts:
    """Container for cached paper assets."""

    paper: Paper
    tei_xml: str
    chunks: List[Chunk]
    embeddings: List[Sequence[float]]


class DoiFileCache:
    """Lightweight filesystem cache scoped by DOI."""

    def __init__(
        self, base_dir: Path | str = ".cache", *, chunk_encoding_name: str | None = None
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_encoding_name = chunk_encoding_name

    def load_metadata(self, doi: str) -> Optional[Paper]:
        path = self._metadata_path(doi)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        provenance = self._deserialize_provenance(data.get("provenance"))
        if provenance:
            data["provenance"] = provenance
        return Paper(**data)

    def store_metadata(self, doi: str, paper: Paper) -> None:
        path = self._metadata_path(doi)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(paper)
        if paper.provenance:
            payload["provenance"] = self._serialize_provenance(paper.provenance)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def load_tei(self, doi: str) -> Optional[str]:
        path = self._tei_path(doi)
        if not path.exists():
            return None
        return path.read_text()

    def store_tei(self, doi: str, tei_xml: str) -> None:
        path = self._tei_path(doi)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tei_xml)

    def load_chunks(self, doi: str) -> Optional[List[Chunk]]:
        path = self._chunks_path(doi)
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return [Chunk(**item) for item in payload]

    def store_chunks(self, doi: str, chunks: Iterable[Chunk]) -> None:
        path = self._chunks_path(doi)
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [asdict(chunk) for chunk in chunks]
        path.write_text(json.dumps(serialized, indent=2, sort_keys=True))

    def load_embeddings(self, doi: str) -> Optional[List[Sequence[float]]]:
        path = self._embeddings_path(doi)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def store_embeddings(self, doi: str, embeddings: Iterable[Sequence[float]]) -> None:
        path = self._embeddings_path(doi)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(list(embeddings), indent=2))

    def build_chunks(self, *, doi: str, tei_xml: str, paper_id: str, title: Optional[str]) -> List[Chunk]:
        chunker = GrobidChunker(
            paper_id=paper_id, tei_xml=tei_xml, encoding_name=self.chunk_encoding_name
        )
        grobid_chunks = chunker.chunk()
        return [Chunk.from_grobid(item, title=title) for item in grobid_chunks]

    def _doi_dir(self, doi: str) -> Path:
        normalized = normalize_doi(doi) or doi.strip().lower()
        safe = normalized.replace("/", "_")
        return self.base_dir / safe

    def _metadata_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "metadata.json"

    def _tei_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "tei.xml"

    def _chunks_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "chunks.json"

    def _embeddings_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "embeddings.json"

    def _deserialize_provenance(self, data: Optional[Dict[str, object]]) -> Optional[PaperProvenance]:
        if not data:
            return None
        field_sources = {
            key: PaperEvidence(**value) for key, value in (data.get("field_sources") or {}).items()
        }
        return PaperProvenance(
            sources=list(data.get("sources", [])),
            source_records=dict(data.get("source_records", {})),
            field_sources=field_sources,
        )

    def _serialize_provenance(self, provenance: PaperProvenance) -> Dict[str, object]:
        return {
            "sources": list(provenance.sources),
            "source_records": dict(provenance.source_records),
            "field_sources": {
                key: asdict(value) for key, value in provenance.field_sources.items()
            },
        }


class CachedPaperPipeline:
    """Orchestrate metadata lookup, TEI parsing, chunking, and embedding with caching."""

    def __init__(
        self,
        *,
        cache: DoiFileCache,
        metadata_service: "OpenAlexService",
        grobid_client: "GrobidClient",
        embedder: Embedder,
    ) -> None:
        self.cache = cache
        self.metadata_service = metadata_service
        self.grobid_client = grobid_client
        self.embedder = embedder

    def ingest(self, doi: str, *, pdf: str | bytes | Path) -> CachedPaperArtifacts:
        metadata = self.cache.load_metadata(doi)
        if metadata is None:
            metadata = self.metadata_service.get_by_doi(doi)
            if metadata is None:
                raise ValueError(f"No metadata found for DOI '{doi}'")
            self.cache.store_metadata(doi, metadata)

        tei_xml = self.cache.load_tei(doi)
        if tei_xml is None:
            tei_xml = self.grobid_client.process_fulltext(pdf, consolidate_header=True)
            self.cache.store_tei(doi, tei_xml)

        chunks = self.cache.load_chunks(doi)
        if chunks is None:
            chunks = self.cache.build_chunks(
                doi=doi, tei_xml=tei_xml, paper_id=metadata.paper_id, title=metadata.title
            )
            self.cache.store_chunks(doi, chunks)

        embeddings = self.cache.load_embeddings(doi)
        if embeddings is None:
            embeddings = list(self.embedder.embed([chunk.text for chunk in chunks]))
            self.cache.store_embeddings(doi, embeddings)

        return CachedPaperArtifacts(
            paper=metadata, tei_xml=tei_xml, chunks=chunks, embeddings=embeddings
        )


__all__ = ["CachedPaperArtifacts", "CachedPaperPipeline", "DoiFileCache"]
