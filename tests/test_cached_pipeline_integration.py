from __future__ import annotations

import json
from pathlib import Path

import responses

from retrieval.cache import CachedPaperPipeline, DoiFileCache
from retrieval.clients import GrobidClient
from retrieval.models import Paper
from retrieval.services import PaperMergeService


class CountingEmbedder:
    def __init__(self, dimension: int = 2) -> None:
        self.calls = 0
        self.dimension = dimension
        self.model_name = "counting"

    def embed(self, texts):
        self.calls += 1
        return [[float(len(text))] * self.dimension for text in texts]


@responses.activate
def test_cached_pipeline_round_trip(tmp_path: Path):
    doi = "10.1234/example"
    cache = DoiFileCache(tmp_path / "cache")
    embedder = CountingEmbedder()

    paper = Paper(
        paper_id=doi,
        title="Example Paper",
        doi=doi,
        abstract="An example abstract",
        year=2024,
        venue="Example Venue",
        source="crossref",
    )

    class StubSearchService:
        def __init__(self) -> None:
            self.calls = 0
            self.merge_service = PaperMergeService()

        def search_by_doi(self, incoming_doi: str):
            self.calls += 1
            return [paper] if incoming_doi == doi else []

    tei_xml = (Path(__file__).parent / "fixtures" / "grobid_sample.xml").read_text()

    search_service = StubSearchService()
    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body=tei_xml,
        status=200,
        content_type="application/xml",
    )

    pipeline = CachedPaperPipeline(
        cache=cache,
        search_service=search_service,
        grobid_client=GrobidClient(base_url="http://grobid.test"),
        embedder=embedder,
    )

    first = pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")

    assert cache.load_metadata(doi) is not None
    assert cache.load_tei(doi) is not None
    assert cache.load_chunks(doi)
    assert cache.load_embeddings(doi)
    assert first.embeddings
    assert len(responses.calls) == 1
    assert embedder.calls == 1
    assert search_service.calls == 1

    second = pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")

    assert len(responses.calls) == 1  # No additional HTTP requests on cache hit
    assert embedder.calls == 1  # Embeddings loaded from cache
    assert search_service.calls == 1  # Metadata loaded from cache
    assert second.paper.title == first.paper.title
    assert second.embeddings == first.embeddings


@responses.activate
def test_embedder_dimension_change_forces_reembedding(tmp_path: Path):
    doi = "10.1234/example"
    cache = DoiFileCache(tmp_path / "cache")
    first_embedder = CountingEmbedder(dimension=2)

    paper = Paper(
        paper_id=doi,
        title="Example Paper",
        doi=doi,
        abstract="An example abstract",
        year=2024,
        venue="Example Venue",
        source="crossref",
    )

    class StubSearchService:
        def __init__(self) -> None:
            self.calls = 0
            self.merge_service = PaperMergeService()

        def search_by_doi(self, incoming_doi: str):
            self.calls += 1
            return [paper] if incoming_doi == doi else []

    tei_xml = (Path(__file__).parent / "fixtures" / "grobid_sample.xml").read_text()

    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body=tei_xml,
        status=200,
        content_type="application/xml",
    )

    search_service = StubSearchService()
    pipeline = CachedPaperPipeline(
        cache=cache,
        search_service=search_service,
        grobid_client=GrobidClient(base_url="http://grobid.test"),
        embedder=first_embedder,
    )

    first = pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")
    assert len(responses.calls) == 1
    assert first_embedder.calls == 1

    second_embedder = CountingEmbedder(dimension=3)
    second_pipeline = CachedPaperPipeline(
        cache=cache,
        search_service=StubSearchService(),
        grobid_client=GrobidClient(base_url="http://grobid.test"),
        embedder=second_embedder,
    )

    second = second_pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")

    assert len(responses.calls) == 1  # TEI served from cache
    assert second_embedder.calls == 1  # Re-embedded after dimension change
    assert all(len(vec) == 3 for vec in second.embeddings)


@responses.activate
def test_chunk_encoding_change_forces_rechunk(tmp_path: Path):
    doi = "10.1234/example"
    base_cache = tmp_path / "cache"
    cache = DoiFileCache(base_cache, chunk_encoding_name="utf-8")
    embedder = CountingEmbedder()

    paper = Paper(
        paper_id=doi,
        title="Example Paper",
        doi=doi,
        abstract="An example abstract",
        year=2024,
        venue="Example Venue",
        source="crossref",
    )

    class StubSearchService:
        def __init__(self) -> None:
            self.calls = 0
            self.merge_service = PaperMergeService()

        def search_by_doi(self, incoming_doi: str):
            self.calls += 1
            return [paper] if incoming_doi == doi else []

    tei_xml = (Path(__file__).parent / "fixtures" / "grobid_sample.xml").read_text()

    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body=tei_xml,
        status=200,
        content_type="application/xml",
    )

    search_service = StubSearchService()
    pipeline = CachedPaperPipeline(
        cache=cache,
        search_service=search_service,
        grobid_client=GrobidClient(base_url="http://grobid.test"),
        embedder=embedder,
    )

    first = pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")
    assert embedder.calls == 1

    new_cache = DoiFileCache(base_cache, chunk_encoding_name="latin-1")
    new_embedder = CountingEmbedder()
    second_pipeline = CachedPaperPipeline(
        cache=new_cache,
        search_service=StubSearchService(),
        grobid_client=GrobidClient(base_url="http://grobid.test"),
        embedder=new_embedder,
    )

    second = second_pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")

    assert len(responses.calls) == 1  # TEI served from cache
    assert new_embedder.calls == 1  # Rechunking triggered new embeddings
    assert second.chunks
    assert second.embeddings


@responses.activate
def test_cached_pipeline_merges_and_records_provenance(tmp_path: Path):
    doi = "10.1234/example"
    cache = DoiFileCache(tmp_path / "cache")
    embedder = CountingEmbedder()

    crossref_paper = Paper(
        paper_id="cr-1",
        title="Merged Title",
        doi=doi,
        abstract=None,
        year=2020,
        venue="Journal A",
        source="crossref",
        url="https://doi.org/10.1234/example",
        authors=["Alice"],
    )
    openalex_paper = Paper(
        paper_id="oa-1",
        title="Merged Title",
        doi=doi,
        abstract="OA abstract",
        year=2021,
        venue="Conference B",
        source="openalex",
        url="https://openalex.org/oa-1",
        pdf_url="https://example.org/pdf",
        is_oa=True,
        authors=["Alice", "Bob"],
    )

    class StubSearchService:
        def __init__(self) -> None:
            self.merge_service = PaperMergeService()

        def search_by_doi(self, incoming_doi: str):
            return [crossref_paper, openalex_paper] if incoming_doi == doi else []

    tei_xml = (Path(__file__).parent / "fixtures" / "grobid_sample.xml").read_text()

    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body=tei_xml,
        status=200,
        content_type="application/xml",
    )

    pipeline = CachedPaperPipeline(
        cache=cache,
        search_service=StubSearchService(),
        grobid_client=GrobidClient(base_url="http://grobid.test"),
        embedder=embedder,
    )

    artifacts = pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")

    metadata = json.loads((cache._metadata_path(doi)).read_text())

    assert artifacts.paper.abstract == "OA abstract"
    assert artifacts.paper.year == 2020
    assert metadata["provenance"]["sources"] == ["crossref", "openalex"]
    assert metadata["provenance"]["field_sources"]["abstract"]["source"] == "openalex"
    assert metadata["provenance"]["field_sources"]["year"]["source"] == "crossref"
    assert metadata["provenance"]["field_sources"]["authors"]["source"] == "openalex"
