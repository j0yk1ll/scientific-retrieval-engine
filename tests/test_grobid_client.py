import responses

from retrieval.providers.clients import GrobidClient


@responses.activate
def test_process_fulltext_with_bytes():
    client = GrobidClient(base_url="http://grobid.test")
    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body="<TEI>ok</TEI>",
        status=200,
        content_type="application/xml",
    )

    tei = client.process_fulltext(b"%PDF-1.4 test")

    assert tei == "<TEI>ok</TEI>"
    request = responses.calls[0].request
    assert request.headers.get("Accept") == "application/xml"


@responses.activate
def test_process_fulltext_with_path(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    client = GrobidClient(base_url="http://grobid.test")
    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body="<TEI>ok</TEI>",
        status=200,
        content_type="application/xml",
    )

    tei = client.process_fulltext(pdf_path, consolidate_header=True)

    assert tei == "<TEI>ok</TEI>"
    request_body = responses.calls[0].request.body
    assert pdf_path.name.encode() in request_body
