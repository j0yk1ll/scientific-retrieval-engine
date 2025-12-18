from __future__ import annotations

from typing import Optional

from retrieval.clients.unpaywall import UnpaywallClient, UnpaywallRecord


class UnpaywallService:
    """Thin wrapper around UnpaywallClient to expose normalized calls."""

    def __init__(self, client: UnpaywallClient) -> None:
        self.client = client

    def get_record(self, doi: str) -> Optional[UnpaywallRecord]:
        if not doi:
            return None
        try:
            return self.client.get_record(doi)
        except Exception:
            return None
