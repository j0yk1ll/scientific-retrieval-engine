from __future__ import annotations

import json
from pathlib import Path

import responses

from retrieval.cache import CachedPaperPipeline, DoiFileCache
from retrieval.clients import GrobidClient, OpenAlexClient
from retrieval.services import OpenAlexService


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[float(len(text)), float(len(text.split()))] for text in texts]


@responses.activate
def test_cached_pipeline_round_trip(tmp_path: Path):
    doi = "10.1234/example"
    cache = DoiFileCache(tmp_path / "cache")
    embedder = CountingEmbedder()

    metadata_payload = json.loads(
        (Path(__file__).parent / "fixtures" / "openalex_work_sample.json").read_text()
    )
    tei_xml = (Path(__file__).parent / "fixtures" / "grobid_sample.xml").read_text()

    responses.add(
        responses.GET,
        "http://openalex.test/works/https://doi.org/10.1234/example",
        json=metadata_payload,
        status=200,
    )
    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body=tei_xml,
        status=200,
        content_type="application/xml",
    )

    pipeline = CachedPaperPipeline(
        cache=cache,
        metadata_service=OpenAlexService(OpenAlexClient(base_url="http://openalex.test")),
        grobid_client=GrobidClient(base_url="http://grobid.test"),
        embedder=embedder,
    )

    first = pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")

    assert cache.load_metadata(doi) is not None
    assert cache.load_tei(doi) is not None
    assert cache.load_chunks(doi)
    assert cache.load_embeddings(doi)
    assert first.embeddings
    assert len(responses.calls) == 2
    assert embedder.calls == 1

    second = pipeline.ingest(doi, pdf=b"%PDF-1.4 sample")

    assert len(responses.calls) == 2  # No additional HTTP requests on cache hit
    assert embedder.calls == 1  # Embeddings loaded from cache
    assert second.paper.title == first.paper.title
    assert second.embeddings == first.embeddings
