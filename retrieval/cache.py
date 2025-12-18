from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, TYPE_CHECKING

from retrieval.chunking import GrobidChunker
from retrieval.hybrid.embeddings import Embedder
from retrieval.hybrid.models import Chunk
from retrieval.identifiers import normalize_doi
from retrieval.models import Paper, PaperEvidence, PaperProvenance
from retrieval.services.paper_merge_service import PaperMergeService

if TYPE_CHECKING:  # pragma: no cover
    from retrieval.api import RetrievalClient
    from retrieval.services.paper_enrichment_service import PaperEnrichmentService
    from retrieval.services.search_service import PaperSearchService

CACHE_VERSION = "1"
MANIFEST_FILE = "manifest.json"


def _atomic_write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


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
        self,
        base_dir: Path | str = ".cache",
        *,
        chunk_encoding_name: str | None = None,
        chunker_version: str | None = None,
        embedder_model_name: str | None = None,
        embedder_dimension: int | None = None,
        embedder_normalized: bool | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_cache_version()
        self.chunk_encoding_name = chunk_encoding_name
        self.chunker_version = chunker_version or getattr(GrobidChunker, "VERSION", "unknown")
        self.embedder_model_name = embedder_model_name
        self.embedder_dimension = embedder_dimension
        self.embedder_normalized = embedder_normalized

    def load_metadata(self, doi: str) -> Optional[Paper]:
        if not self._version_matches:
            return None
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
        payload = asdict(paper)
        if paper.provenance:
            payload["provenance"] = self._serialize_provenance(paper.provenance)
        _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))

    def load_tei(self, doi: str) -> Optional[str]:
        if not self._version_matches:
            return None
        path = self._tei_path(doi)
        if not path.exists():
            return None
        return path.read_text()

    def store_tei(self, doi: str, tei_xml: str) -> None:
        path = self._tei_path(doi)
        _atomic_write_text(path, tei_xml)

    def load_chunks(self, doi: str) -> Optional[List[Chunk]]:
        if not self._version_matches:
            return None
        if not self._manifest_chunks_match(doi):
            return None
        path = self._chunks_path(doi)
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return [Chunk(**item) for item in payload]

    def store_chunks(self, doi: str, chunks: Iterable[Chunk]) -> None:
        path = self._chunks_path(doi)
        serialized = [asdict(chunk) for chunk in chunks]
        _atomic_write_text(path, json.dumps(serialized, indent=2, sort_keys=True))
        self._write_manifest(
            doi,
            {
                "cache_version": CACHE_VERSION,
                "chunker_version": self.chunker_version,
                "encoding": self.chunk_encoding_name,
            },
        )

    def load_embeddings(self, doi: str) -> Optional[List[Sequence[float]]]:
        if not self._version_matches:
            return None
        if not self._manifest_embeddings_match(doi):
            return None
        path = self._embeddings_path(doi)
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        if isinstance(payload, dict) and "embeddings" in payload:
            return payload["embeddings"]
        return payload

    def store_embeddings(
        self,
        doi: str,
        embeddings: Iterable[Sequence[float]],
        *,
        embedding_metadata: Dict[str, object],
    ) -> None:
        path = self._embeddings_path(doi)
        payload = {"metadata": embedding_metadata, "embeddings": list(embeddings)}
        _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))
        manifest = self._load_manifest(doi) or {}
        manifest.update(
            {
                "cache_version": CACHE_VERSION,
                "chunker_version": self.chunker_version,
                "encoding": self.chunk_encoding_name,
                "embedder": {
                    "model": embedding_metadata.get("model"),
                    "dimension": embedding_metadata.get("dimension"),
                    "normalized": embedding_metadata.get("normalized"),
                },
            }
        )
        self._write_manifest(doi, manifest)

    def build_chunks(self, *, doi: str, tei_xml: str, paper_id: str, title: Optional[str]) -> List[Chunk]:
        chunker = GrobidChunker(
            paper_id=paper_id, tei_xml=tei_xml, encoding_name=self.chunk_encoding_name
        )
        grobid_chunks = chunker.chunk()
        return [Chunk.from_grobid(item, title=title) for item in grobid_chunks]

    def _doi_dir(self, doi: str) -> Path:
        normalized = normalize_doi(doi) or doi.strip().lower()
        safe = re.sub(r"[^a-z0-9._-]", "-", normalized.lower())
        safe = re.sub(r"-+", "-", safe).strip("-_.")
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        slug = f"{safe[:64]}-{digest[:12]}" if safe else digest[:12]
        slug = re.sub(r"[^a-z0-9._-]", "-", slug)
        return self.base_dir / slug

    def _metadata_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "metadata.json"

    def _tei_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "tei.xml"

    def _chunks_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "chunks.json"

    def _embeddings_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / "embeddings.json"

    def _manifest_path(self, doi: str) -> Path:
        return self._doi_dir(doi) / MANIFEST_FILE

    def _ensure_cache_version(self) -> None:
        version_file = self.base_dir / "cache_version"
        if not version_file.exists():
            _atomic_write_text(version_file, CACHE_VERSION)
            self._version_matches = True
            return

        current_version = version_file.read_text().strip()
        if current_version == CACHE_VERSION:
            self._version_matches = True
            return

        for child in self.base_dir.iterdir():
            if child == version_file:
                continue
            if child.is_dir():
                for sub in sorted(child.rglob("*"), reverse=True):
                    if sub.is_file():
                        sub.unlink()
                    elif sub.is_dir():
                        sub.rmdir()
                child.rmdir()
            else:
                child.unlink()
        _atomic_write_text(version_file, CACHE_VERSION)
        self._version_matches = True

    def _load_manifest(self, doi: str) -> Optional[Dict[str, object]]:
        path = self._manifest_path(doi)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None

    def _write_manifest(self, doi: str, manifest: Dict[str, object]) -> None:
        manifest = dict(manifest)
        manifest.setdefault("cache_version", CACHE_VERSION)
        _atomic_write_text(self._manifest_path(doi), json.dumps(manifest, indent=2, sort_keys=True))

    def _manifest_chunks_match(self, doi: str) -> bool:
        manifest = self._load_manifest(doi)
        if not manifest:
            self._invalidate_chunks(doi, include_embeddings=True)
            return False
        if manifest.get("cache_version") != CACHE_VERSION:
            self._invalidate_chunks(doi, include_embeddings=True)
            return False
        if manifest.get("chunker_version") != self.chunker_version:
            self._invalidate_chunks(doi, include_embeddings=True)
            return False
        if manifest.get("encoding") != self.chunk_encoding_name:
            self._invalidate_chunks(doi, include_embeddings=True)
            return False
        return True

    def _manifest_embeddings_match(self, doi: str) -> bool:
        manifest = self._load_manifest(doi)
        if not manifest:
            self._invalidate_embeddings(doi)
            return False
        if manifest.get("cache_version") != CACHE_VERSION:
            self._invalidate_embeddings(doi)
            return False
        embedder_manifest = manifest.get("embedder") or {}
        if embedder_manifest and self.embedder_model_name:
            if embedder_manifest.get("model") != self.embedder_model_name:
                self._invalidate_embeddings(doi)
                return False
        if embedder_manifest and self.embedder_dimension is not None:
            if embedder_manifest.get("dimension") != self.embedder_dimension:
                self._invalidate_embeddings(doi)
                return False
        if embedder_manifest and self.embedder_normalized is not None:
            if embedder_manifest.get("normalized") != self.embedder_normalized:
                self._invalidate_embeddings(doi)
                return False
        if not embedder_manifest and any(
            value is not None
            for value in (self.embedder_model_name, self.embedder_dimension, self.embedder_normalized)
        ):
            self._invalidate_embeddings(doi)
            return False
        return True

    def _invalidate_chunks(self, doi: str, *, include_embeddings: bool = False) -> None:
        self._chunks_path(doi).unlink(missing_ok=True)
        self._manifest_path(doi).unlink(missing_ok=True)
        if include_embeddings:
            self._invalidate_embeddings(doi)

    def _invalidate_embeddings(self, doi: str) -> None:
        self._embeddings_path(doi).unlink(missing_ok=True)

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
        search_service: "PaperSearchService" | None = None,
        retrieval_client: "RetrievalClient" | None = None,
        merge_service: PaperMergeService | None = None,
        enrichment_service: "PaperEnrichmentService" | None = None,
        grobid_client: "GrobidClient",
        embedder: Embedder,
    ) -> None:
        self.cache = cache
        if search_service and retrieval_client:
            raise ValueError("Provide either search_service or retrieval_client, not both")
        if not search_service and not retrieval_client:
            raise ValueError("A search_service or retrieval_client is required")

        self.retrieval_client = retrieval_client
        self.search_service = (
            search_service
            if search_service is not None
            else retrieval_client._search_service  # type: ignore[attr-defined]
        )
        self.merge_service = merge_service or self.search_service.merge_service
        self.enrichment_service = (
            enrichment_service
            if enrichment_service is not None
            else getattr(retrieval_client, "_paper_enrichment_service", None)
        )
        self.grobid_client = grobid_client
        self.embedder = embedder
        self._configure_cache_embedder_requirements()

    def ingest(self, doi: str, *, pdf: str | bytes | Path) -> CachedPaperArtifacts:
        metadata = self.cache.load_metadata(doi)
        if metadata is None:
            candidates = self._search_by_doi(doi)
            if not candidates:
                raise ValueError(f"No metadata found for DOI '{doi}'")
            metadata = self.merge_service.merge(candidates)
            if self.enrichment_service:
                metadata = self.enrichment_service.enrich(metadata)
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
            metadata = self._build_embedding_metadata(embeddings)
            self.cache.store_embeddings(doi, embeddings, embedding_metadata=metadata)

        return CachedPaperArtifacts(
            paper=metadata, tei_xml=tei_xml, chunks=chunks, embeddings=embeddings
        )

    def _search_by_doi(self, doi: str) -> List[Paper]:
        if self.retrieval_client:
            return self.retrieval_client.search_paper_by_doi(doi)
        return self.search_service.search_by_doi(doi)

    def _build_embedding_metadata(self, embeddings: List[Sequence[float]]) -> Dict[str, object]:
        dimension = self.cache.embedder_dimension
        if dimension is None:
            dimension = len(embeddings[0]) if embeddings else 0
        model_name = getattr(self.embedder, "model_name", None) or self.embedder.__class__.__name__
        normalized = self.cache.embedder_normalized
        if normalized is None:
            normalized = getattr(self.embedder, "normalized", None)
        if normalized is None:
            normalized = getattr(self.embedder, "normalize", None)
        return {
            "model": model_name,
            "dimension": dimension,
            "normalized": bool(normalized) if normalized is not None else False,
            "chunker_version": self.cache.chunker_version,
        }

    def _configure_cache_embedder_requirements(self) -> None:
        model_name = getattr(self.embedder, "model_name", None) or self.embedder.__class__.__name__
        normalized = getattr(self.embedder, "normalized", None)
        if normalized is None:
            normalized = getattr(self.embedder, "normalize", None)
        for candidate in ("dimension", "embedding_dimension", "embedding_size", "output_dim", "dim"):
            dimension_value = getattr(self.embedder, candidate, None)
            if dimension_value is not None:
                break
        else:
            dimension_value = None

        self.cache.embedder_model_name = model_name
        self.cache.embedder_normalized = bool(normalized) if normalized is not None else None
        self.cache.embedder_dimension = (
            int(dimension_value) if isinstance(dimension_value, (int, float)) else None
        )


__all__ = ["CachedPaperArtifacts", "CachedPaperPipeline", "DoiFileCache"]
