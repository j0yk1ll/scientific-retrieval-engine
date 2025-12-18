import pytest

from retrieval.services.unpaywall_service import UnpaywallService


def test_unpaywall_service_requires_configuration() -> None:
    with pytest.raises(ValueError):
        UnpaywallService()
