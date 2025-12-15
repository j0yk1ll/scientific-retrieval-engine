import responses

from retrieval.acquisition.preprints.arxiv import ArxivClient
from retrieval.acquisition.preprints.chemrxiv import ChemRxivClient
from retrieval.acquisition.preprints.medrxiv import MedRxivClient
from retrieval.acquisition.preprints.base import PreprintResult
from retrieval.acquisition.title_match import TitleMatcher
from retrieval.acquisition.unpaywall import UnpaywallClient, resolve_full_text


@responses.activate
def test_unpaywall_parses_best_pdf_and_sets_email_param():
    doi = "10.1234/example"
    email = "test@example.com"
    client = UnpaywallClient(email=email, timeout=3.0)

    responses.add(
        responses.GET,
        f"https://api.unpaywall.org/v2/{doi}",
        json={
            "doi": doi,
            "title": "Sample Work",
            "best_oa_location": {
                "url": "https://host/paper",
                "url_for_pdf": "https://host/paper.pdf",
                "license": "cc-by",
                "version": "publishedVersion",
                "host_type": "publisher",
                "is_best": True,
            },
            "oa_locations": [
                {
                    "url": "https://host/paper",
                    "url_for_pdf": "https://host/paper.pdf",
                    "license": "cc-by",
                    "version": "publishedVersion",
                    "host_type": "publisher",
                    "is_best": True,
                }
            ],
        },
        status=200,
    )

    record = client.get_record(doi)

    assert record.best_pdf_url == "https://host/paper.pdf"
    assert record.best_oa_location is not None
    assert record.best_oa_location.license == "cc-by"

    request = responses.calls[0].request
    assert "email=test%40example.com" in request.url


@responses.activate
def test_title_matcher_picks_best_candidate():
    matcher = TitleMatcher(threshold=0.5)
    query_title = "Deep Learning for Genomics"
    candidates = [
        PreprintResult(provider="chemrxiv", title="Deep learning in chemistry", url="http://chemrxiv"),
        PreprintResult(provider="arxiv", title="Deep Learning for Genomics", url="http://arxiv", pdf_url="http://arxiv/pdf"),
        PreprintResult(provider="medrxiv", title="Genomic analyses", url="http://medrxiv"),
    ]

    best = matcher.pick_best(query_title, candidates)

    assert best is not None
    assert best.provider == "arxiv"
    assert best.pdf_url == "http://arxiv/pdf"


@responses.activate
def test_arxiv_request_shape_and_parsing():
    client = ArxivClient(timeout=2.0)
    title = "Neural Networks"
    feed = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/1234.5678</id>
        <title>Neural Networks for NLP</title>
        <author><name>Alice</name></author>
        <link rel="alternate" href="http://arxiv.org/abs/1234.5678" />
        <link rel="related" type="application/pdf" href="http://arxiv.org/pdf/1234.5678.pdf" />
      </entry>
    </feed>
    """

    responses.add(responses.GET, "http://export.arxiv.org/api/query", body=feed, status=200)

    results = client.search(title, max_results=1)

    assert len(results) == 1
    result = results[0]
    assert result.provider == "arxiv"
    assert result.pdf_url == "http://arxiv.org/pdf/1234.5678.pdf"

    request = responses.calls[0].request
    assert "search_query=ti%3A%22Neural+Networks%22" in request.url


@responses.activate
def test_medrxiv_parsing():
    client = MedRxivClient(timeout=2.0)
    title = "COVID-19 vaccine"
    responses.add(
        responses.GET,
        "https://api.biorxiv.org/details/medrxiv",
        json={
            "collection": [
                {
                    "title": "COVID-19 vaccine effectiveness",
                    "doi": "10.1101/medrxiv.2020.01.01",
                    "link": "https://www.medrxiv.org/content/10.1101/medrxiv.2020.01.01",
                    "pdf_url": "https://www.medrxiv.org/content/10.1101/medrxiv.2020.01.01.pdf",
                    "date": "2020-01-01",
                }
            ]
        },
        status=200,
    )

    results = client.search(title, max_results=1)
    assert results[0].pdf_url.endswith(".pdf")
    assert results[0].url.startswith("https://www.medrxiv.org/content")


@responses.activate
def test_chemrxiv_parsing():
    client = ChemRxivClient(timeout=2.0)
    title = "Organic synthesis"
    responses.add(
        responses.GET,
        "https://chemrxiv.org/engage/chemrxiv/public-api/v1/items",
        json={
            "items": [
                {
                    "title": "Organic synthesis advances",
                    "id": "chemrxiv-123",
                    "pdf_url": "https://chemrxiv.org/chemrxiv-123.pdf",
                }
            ]
        },
        status=200,
    )

    results = client.search(title, max_results=1)
    assert results[0].provider == "chemrxiv"
    assert results[0].pdf_url.endswith(".pdf")


@responses.activate
def test_resolve_full_text_falls_back_to_preprint_when_unpaywall_missing_pdf():
    doi = "10.5678/xyz"
    title = "A study on quantum widgets"
    email = "contact@example.com"

    responses.add(
        responses.GET,
        f"https://api.unpaywall.org/v2/{doi}",
        json={"doi": doi, "title": title, "oa_locations": []},
        status=200,
    )

    responses.add(
        responses.GET,
        "http://export.arxiv.org/api/query",
        body="""
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/9999.8888</id>
            <title>A study on quantum widgets</title>
            <link rel="related" type="application/pdf" href="http://arxiv.org/pdf/9999.8888.pdf" />
          </entry>
        </feed>
        """,
        status=200,
    )

    unpaywall_client = UnpaywallClient(email=email)
    arxiv_client = ArxivClient()

    candidate = resolve_full_text(
        doi=doi,
        title=title,
        unpaywall_client=unpaywall_client,
        preprint_clients=[arxiv_client],
    )

    assert candidate is not None
    assert candidate.source == "arxiv"
    assert candidate.pdf_url == "http://arxiv.org/pdf/9999.8888.pdf"
