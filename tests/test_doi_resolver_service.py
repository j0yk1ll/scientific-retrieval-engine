from literature_retrieval_engine.providers.clients.crossref import CrossrefWork
from literature_retrieval_engine.providers.clients.datacite import DataCiteWork
from literature_retrieval_engine.services.doi_resolver_service import DoiResolverService


class StubCrossrefService:
    def __init__(self, papers):
        self._papers = papers

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._papers[:rows]


class StubDataCiteService:
    def __init__(self, papers):
        self._papers = papers

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._papers[:rows]


def test_resolve_uses_title_match_and_author_overlap():
    title = "A Precise Study"
    works = [
        CrossrefWork(
            title=title,
            doi="10.1111/title-match",
            year=2020,
            venue=None,
            authors=["Alice Smith"],
            url=None,
        ),
        CrossrefWork(
            title=title,
            doi="10.2222/wrong-author",
            year=2020,
            venue=None,
            authors=["Bob Jones"],
            url=None,
        ),
    ]

    resolver = DoiResolverService(
        crossref=StubCrossrefService(works), datacite=StubDataCiteService([])
    )

    resolved = resolver.resolve_doi_from_title(title, expected_authors=["Alice Smith"])

    assert resolved == "10.1111/title-match"


def test_resolve_falls_back_to_datacite_when_crossref_missing():
    title = "A Precise Study"
    crossref_works: list[CrossrefWork] = []
    datacite_works = [
        DataCiteWork(
            title=title,
            doi="10.9999/datacite",
            year=2021,
            venue=None,
            authors=["Dana Scully"],
            url=None,
        )
    ]

    resolver = DoiResolverService(
        crossref=StubCrossrefService(crossref_works), datacite=StubDataCiteService(datacite_works)
    )

    resolved = resolver.resolve_doi_from_title(title, expected_authors=["Dana Scully"])

    assert resolved == "10.9999/datacite"


def test_resolve_accepts_near_exact_match_with_author_overlap():
    title = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau"
    near_match_title = (
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma"
    )
    works = [
        CrossrefWork(
            title=near_match_title,
            doi="10.3333/near-match",
            year=2022,
            venue=None,
            authors=["Alice Smith"],
            url=None,
        )
    ]

    resolver = DoiResolverService(
        crossref=StubCrossrefService(works), datacite=StubDataCiteService([])
    )

    resolved = resolver.resolve_doi_from_title(title, expected_authors=["Alice Smith"])

    assert resolved == "10.3333/near-match"


def test_resolve_rejects_near_match_without_author_overlap_when_expected():
    title = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau"
    near_match_title = (
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma"
    )
    works = [
        CrossrefWork(
            title=near_match_title,
            doi="10.4444/wrong-author",
            year=2022,
            venue=None,
            authors=["Bob Jones"],
            url=None,
        )
    ]

    resolver = DoiResolverService(
        crossref=StubCrossrefService(works), datacite=StubDataCiteService([])
    )

    resolved = resolver.resolve_doi_from_title(title, expected_authors=["Alice Smith"])

    assert resolved is None
