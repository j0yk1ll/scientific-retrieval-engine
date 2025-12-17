from retrieval.parsing.citations import extract_citations


def test_extract_citations_handles_ranges_and_duplicates() -> None:
    text = "Memory types that balance persistence with dynamism [2, 3-5; 3]."

    assert extract_citations(text) == ["2", "3", "4", "5"]


def test_extract_citations_ignores_non_numeric_markers() -> None:
    text = "See discussion in [A1] and [beta]; compare with [10]."

    assert extract_citations(text) == ["10"]
