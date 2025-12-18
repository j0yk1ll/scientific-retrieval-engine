from retrieval.clients.datacite import DataCiteClient


def test_datacite_client_exact_then_fallback(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):  # type: ignore[override]
        calls.append(kwargs.get("params", {}).get("query"))

        class DummyResponse:
            status_code = 200

            @staticmethod
            def json():
                if len(calls) == 1:
                    return {"data": []}
                return {
                    "data": [
                        {
                            "id": "10.1234/example",
                            "attributes": {
                                "doi": "10.1234/example",
                                "titles": [{"title": "Example Title"}],
                                "publicationYear": 2024,
                                "publisher": "DataCite Press",
                                "url": "https://doi.org/10.1234/example",
                                "creators": [{"creatorName": "Ada Lovelace"}],
                            },
                        }
                    ]
                }

        return DummyResponse()

    monkeypatch.setattr(DataCiteClient, "_request", fake_request)

    client = DataCiteClient()
    works = client.search_by_title('Example "Title"', rows=3)

    assert calls == ['titles.title:"Example \\"Title\\""', 'Example "Title"']
    assert works[0].doi == "10.1234/example"
    assert works[0].title == "Example Title"
    assert works[0].year == 2024
    assert works[0].venue == "DataCite Press"
    assert works[0].authors == ["Ada Lovelace"]
