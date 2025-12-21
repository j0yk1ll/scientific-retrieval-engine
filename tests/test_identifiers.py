import importlib.util
from pathlib import Path


def load_identifiers_module():
    module_path = (
        Path(__file__).resolve().parent.parent / "retrieval" / "core" / "identifiers.py"
    )
    spec = importlib.util.spec_from_file_location("literature_retrieval_engine.core.identifiers", module_path)
    module = importlib.util.module_from_spec(spec)
    if spec and spec.loader:
        spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


identifiers = load_identifiers_module()
normalize_doi = identifiers.normalize_doi
normalize_title = identifiers.normalize_title


def test_normalize_doi_strips_prefixes_and_lowercases():
    assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("DOI:10.1000/XYZ") == "10.1000/xyz"


def test_normalize_doi_handles_dx_prefix_and_spacing():
    assert normalize_doi("  HTTPS://DX.DOI.ORG/10.5555/ABC  ") == "10.5555/abc"


def test_normalize_doi_trims_whitespace_and_handles_none():
    assert normalize_doi("  https://doi.org/10.1000/12345  ") == "10.1000/12345"
    assert normalize_doi("") is None
    assert normalize_doi(None) is None  # type: ignore[arg-type]


def test_normalize_title_collapses_whitespace_and_lowercases():
    assert normalize_title("  The   Quick Brown   Fox  ") == "the quick brown fox"


def test_normalize_title_handles_unicode():
    assert normalize_title("Ｔｅｓｔ　Ｔｉｔｌｅ") == "test title"
