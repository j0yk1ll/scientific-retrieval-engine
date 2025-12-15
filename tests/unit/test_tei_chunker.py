from pathlib import Path

import pytest

from retrieval.parsing.tei_chunker import TEIChunker
from retrieval.exceptions import ParseError


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "tei" / "sample.tei.xml"


def test_chunker_orders_sections_and_respects_max_chars() -> None:
    xml = FIXTURE_PATH.read_text()
    chunker = TEIChunker(max_chars=60)

    chunks = chunker.chunk(xml)

    assert [chunk.section for chunk in chunks] == [
        "Introduction",
        "Introduction",
        "Methods",
        "Methods > Data",
    ]
    assert chunks[0].text == "First paragraph text with extra whitespace."
    assert chunks[1].text == "Second paragraph text to combine."
    assert chunks[2].text == "Detailed methods paragraph."
    assert chunks[3].text == "Nested paragraph that should be kept with its section."


def test_chunker_raises_for_missing_body() -> None:
    chunker = TEIChunker()
    with pytest.raises(ParseError):
        chunker.chunk("<TEI></TEI>")
