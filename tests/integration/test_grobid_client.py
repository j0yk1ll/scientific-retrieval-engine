from pathlib import Path

import pytest
import requests

from retrieval.exceptions import ParseError
from retrieval.parsing import GrobidClient


PDF_PATH = Path(__file__).parent.parent / "fixtures" / "tei" / "sample.pdf"
DEFAULT_GROBID_URL = "http://localhost:8070"


def _grobid_available(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/api/isalive", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


@pytest.mark.integration
@pytest.mark.skipif(
    not _grobid_available(DEFAULT_GROBID_URL),
    reason="GROBID is not reachable at the default URL",
)
def test_grobid_process_fulltext_returns_xml() -> None:
    client = GrobidClient(DEFAULT_GROBID_URL, timeout=15.0)
    xml = client.process_fulltext(PDF_PATH)

    assert "<TEI" in xml
    assert "<text" in xml


def test_invalid_path_raises_parse_error() -> None:
    client = GrobidClient(DEFAULT_GROBID_URL)
    with pytest.raises(ParseError):
        client.process_fulltext(Path("/nonexistent.pdf"))
