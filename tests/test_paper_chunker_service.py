from pathlib import Path

from retrieval.chunking import PaperChunkerService


def load_sample_tei() -> str:
    fixture = Path(__file__).parent / "fixtures" / "grobid_sample.xml"
    return fixture.read_text()


def test_parse_document_structure():
    tei_xml = load_sample_tei()
    chunker = PaperChunkerService(paper_id="paper-123", tei_xml=tei_xml)

    document = chunker.document
    assert document.title == "Sample Paper Title"
    assert document.abstract[0].startswith("This paper presents")
    assert len(document.sections) == 2
    assert document.sections[0].title == "Introduction"
    assert document.references == ["Reference Title One", "Reference Title Two"]


def test_chunking_preserves_section_headers_and_limits():
    tei_xml = load_sample_tei()
    chunker = PaperChunkerService(paper_id="paper-123", tei_xml=tei_xml)

    chunks = chunker.chunk(max_tokens=200, max_chars=220)

    assert chunks[0].chunk_id == "paper-123-chunk-1"
    assert chunks[0].section == "Title"
    assert chunks[0].content.startswith("Title\n\nSample Paper Title")

    introduction_chunks = [chunk for chunk in chunks if chunk.section == "Introduction"]
    assert len(introduction_chunks) >= 2  # long intro paragraph should be split
    for chunk in introduction_chunks:
        assert chunk.content.startswith("Introduction\n\n")
        assert chunk.token_count <= 200
        assert len(chunk.content) <= 220

    # Offsets should be stable and monotonic relative to the generated chunk stream
    for first, second in zip(chunks, chunks[1:]):
        assert second.stream_start_char == first.stream_end_char

    # Section indices should follow ordered sections (Title, Abstract, then body)
    assert chunks[0].section_index == 0


def test_chunking_is_reproducible():
    tei_xml = load_sample_tei()
    chunker = PaperChunkerService(paper_id="paper-123", tei_xml=tei_xml)

    first_pass = chunker.chunk(max_tokens=150, max_chars=180)
    second_pass = chunker.chunk(max_tokens=150, max_chars=180)

    assert [chunk.chunk_id for chunk in first_pass] == [chunk.chunk_id for chunk in second_pass]
    assert [chunk.content for chunk in first_pass] == [chunk.content for chunk in second_pass]
