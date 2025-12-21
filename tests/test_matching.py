from literature_retrieval_engine.core.matching import jaccard, title_tokens


def test_title_tokens_normalize_and_strip_punctuation():
    tokens = title_tokens(" The Future, of AI! ")

    assert tokens == {"the", "future", "of", "ai"}


def test_jaccard_similarity_handles_empty_sets():
    assert jaccard([], []) == 1.0
    assert jaccard([], ["a"]) == 0.0


def test_jaccard_similarity_calculates_overlap():
    first = {"alpha", "beta", "gamma"}
    second = {"alpha", "beta", "delta"}

    assert jaccard(first, second) == 0.5
