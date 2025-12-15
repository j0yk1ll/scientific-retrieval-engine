import pytest
import responses

from retrieval.acquisition.downloader import DownloadError, PDFDownloader


@responses.activate
def test_download_pdf_returns_bytes_and_metadata():
    url = "http://example.com/sample.pdf"
    body = b"%PDF-1.4\nexample content"
    headers = {
        "Content-Type": "application/pdf",
        "ETag": "etag-value",
        "Last-Modified": "Tue, 10 Dec 2024 10:00:00 GMT",
        "Content-Length": str(len(body)),
    }
    responses.add(responses.GET, url, body=body, status=200, headers=headers)

    downloader = PDFDownloader(max_size=1024)
    result = downloader.download(url)

    assert result.content == body
    assert result.metadata.etag == "etag-value"
    assert result.metadata.last_modified.startswith("Tue")
    assert result.metadata.content_type == "application/pdf"
    assert result.metadata.content_length == len(body)


@responses.activate
def test_download_allows_pdf_signature_when_content_type_missing():
    url = "http://example.com/no-header.pdf"
    body = b"%PDF-1.4\ncontent"
    responses.add(
        responses.GET,
        url,
        body=body,
        status=200,
        headers={"Content-Type": "text/plain"},
    )

    downloader = PDFDownloader(max_size=1024)
    result = downloader.download(url)

    assert result.content.startswith(b"%PDF-")
    assert result.metadata.content_type == "text/plain"
    assert result.metadata.content_length == len(body)


@responses.activate
def test_download_rejects_non_pdf_payload():
    url = "http://example.com/not-pdf"
    body = b"<html>oops</html>"
    responses.add(
        responses.GET,
        url,
        body=body,
        status=200,
        headers={"Content-Type": "text/html"},
    )

    downloader = PDFDownloader(max_size=1024)

    with pytest.raises(DownloadError):
        downloader.download(url)


@responses.activate
def test_download_rejects_when_content_length_exceeds_max():
    url = "http://example.com/too-large.pdf"
    body = b"%PDF-1.4\n" + b"0" * 2048
    responses.add(
        responses.GET,
        url,
        body=body,
        status=200,
        headers={"Content-Type": "application/pdf", "Content-Length": "2048"},
    )

    downloader = PDFDownloader(max_size=1024)

    with pytest.raises(DownloadError):
        downloader.download(url)


@responses.activate
def test_download_rejects_when_stream_exceeds_max_without_header():
    url = "http://example.com/chunked.pdf"
    body = b"%PDF-1.4\n" + b"1" * 2048
    responses.add(
        responses.GET,
        url,
        body=body,
        status=200,
        headers={"Content-Type": "application/pdf"},
    )

    downloader = PDFDownloader(max_size=1024, chunk_size=256)

    with pytest.raises(DownloadError):
        downloader.download(url)


@responses.activate
def test_download_retries_on_failure_then_succeeds():
    url = "http://example.com/retry.pdf"
    body = b"%PDF-1.4\nretry"
    responses.add(responses.GET, url, status=500)
    responses.add(responses.GET, url, status=502)
    responses.add(responses.GET, url, body=body, status=200, headers={"Content-Type": "application/pdf"})

    downloader = PDFDownloader(max_size=1024, max_retries=3)
    result = downloader.download(url)

    assert result.content == body
    assert len(responses.calls) == 3
