import requests

from literature_retrieval_engine.services.full_text_validation import validate_pdf_url


def _response(status_code: int, *, content_type: str | None = None, body: bytes = b""):
    response = requests.Response()
    response.status_code = status_code
    response._content = body
    if content_type is not None:
        response.headers["Content-Type"] = content_type
    return response


def test_validate_pdf_url_prefers_head_content_type(mocker):
    session = mocker.Mock()
    session.head.return_value = _response(200, content_type="application/pdf")

    result = validate_pdf_url(session, "https://example.org/paper.pdf", timeout=0.5)

    assert result.is_pdf is True
    assert result.content_type == "application/pdf"
    session.head.assert_called_once_with(
        "https://example.org/paper.pdf", allow_redirects=True, timeout=0.5
    )
    session.get.assert_not_called()


def test_validate_pdf_url_falls_back_to_get_content_type(mocker):
    session = mocker.Mock()
    session.head.return_value = _response(200, content_type="text/html")
    session.get.return_value = _response(200, content_type="application/pdf")

    result = validate_pdf_url(session, "https://example.org/paper.pdf", timeout=1.0)

    assert result.is_pdf is True
    assert result.content_type == "application/pdf"
    session.get.assert_called_once_with(
        "https://example.org/paper.pdf",
        headers={"Range": "bytes=0-2047"},
        allow_redirects=True,
        timeout=1.0,
    )


def test_validate_pdf_url_uses_magic_header_when_no_content_type(mocker):
    session = mocker.Mock()
    session.head.side_effect = requests.RequestException("timeout")
    session.get.return_value = _response(206, body=b"%PDF-1.7 something")

    result = validate_pdf_url(session, "https://example.org/paper.pdf", timeout=2.0)

    assert result.is_pdf is True
    assert result.content_type is None


def test_validate_pdf_url_returns_false_on_request_failure(mocker):
    session = mocker.Mock()
    session.head.return_value = _response(404, content_type="text/html")
    session.get.side_effect = requests.RequestException("timeout")

    result = validate_pdf_url(session, "https://example.org/paper.pdf", timeout=0.2)

    assert result.is_pdf is False
    assert result.status_code == 404
