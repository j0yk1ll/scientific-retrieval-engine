from pathlib import Path

from retrieval.storage.files import (
    atomic_write_bytes,
    atomic_write_text,
    pdf_path,
    sha256_bytes,
    sha256_file,
    tei_path,
)


def test_pdf_and_tei_paths(tmp_path: Path) -> None:
    paper_id = "test-paper"
    assert pdf_path(tmp_path, paper_id) == tmp_path / "papers" / "test-paper.pdf"
    assert tei_path(tmp_path, paper_id) == tmp_path / "tei" / "test-paper.tei.xml"


def test_atomic_write_bytes_creates_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.bin"

    atomic_write_bytes(target, b"first")
    assert target.read_bytes() == b"first"

    atomic_write_bytes(target, b"second")
    assert target.read_bytes() == b"second"


def test_atomic_write_text(tmp_path: Path) -> None:
    target = tmp_path / "text" / "file.txt"

    atomic_write_text(target, "hello world")
    assert target.read_text(encoding="utf-8") == "hello world"


def test_sha256_bytes_and_file(tmp_path: Path) -> None:
    content = b"abc123"
    file_path = tmp_path / "hashme.txt"
    file_path.write_bytes(content)

    expected = sha256_bytes(content)

    assert expected == "6ca13d52ca70c883e0f0bb101e425a89e8624de51db2d2392593af6a84118090"
    assert sha256_file(file_path) == expected
