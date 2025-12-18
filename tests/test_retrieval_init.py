import importlib
import sys
import types

import pytest


class DummyClient:
    def __init__(self, created_counter, register_calls):
        created_counter.append(True)
        self._register_calls = register_calls

    def search_papers(self, *_, **__):
        return ["papers"]

    def search_paper_by_doi(self, *_, **__):
        return ["doi"]

    def search_paper_by_title(self, *_, **__):
        return ["title"]

    def gather_evidence(self, *_, **__):
        return ["evidence"]

    def search_citations(self, *_, **__):
        return ["citations"]

    def clear_papers_and_evidence(self):
        self._register_calls.append("cleared")


@pytest.fixture(autouse=True)
def cleanup_retrieval_module():
    yield
    sys.modules.pop("retrieval", None)
    sys.modules.pop("retrieval.api", None)


def test_import_is_lazy(monkeypatch):
    created_instances: list[bool] = []
    register_calls: list[object] = []

    def register_mock(func):
        register_calls.append(func)

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(Session=object))
    dummy_api = types.ModuleType("retrieval.api")
    dummy_api.RetrievalClient = lambda: DummyClient(created_instances, register_calls)
    sys.modules["retrieval.api"] = dummy_api
    monkeypatch.setattr("atexit.register", register_mock)

    sys.modules.pop("retrieval", None)
    retrieval_module = importlib.import_module("retrieval")

    assert created_instances == []
    assert register_calls == []

    assert retrieval_module.search_papers("example") == ["papers"]
    assert len(created_instances) == 1
    assert len(register_calls) == 1
    assert register_calls[0] is not None
