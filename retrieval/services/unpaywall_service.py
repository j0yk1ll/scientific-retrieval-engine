from __future__ import annotations

from typing import Optional

from retrieval.clients.base import ClientError
from retrieval.clients.unpaywall import UnpaywallClient, UnpaywallRecord
from retrieval.settings import RetrievalSettings


class UnpaywallService:
    """Thin wrapper around UnpaywallClient to expose normalized calls."""

    def __init__(
        self,
        *,
        client: Optional[UnpaywallClient] = None,
        settings: Optional[RetrievalSettings] = None,
        email: Optional[str] = None,
        session=None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if client is None:
            if settings is None and email is None:
                raise ValueError("UnpaywallService requires a client, settings, or contact email")

            resolved_settings = settings or RetrievalSettings()
            contact_email = email or resolved_settings.unpaywall_email
            if not contact_email:
                raise ValueError("UnpaywallService requires a contact email")

            client_session = session or resolved_settings.session or resolved_settings.build_session()
            client = UnpaywallClient(
                contact_email,
                session=client_session,
                base_url=base_url or resolved_settings.unpaywall_base_url,
                timeout=timeout or resolved_settings.timeout,
            )

        self.client = client

    def get_record(self, doi: str) -> Optional[UnpaywallRecord]:
        if not doi:
            return None
        try:
            return self.client.get_record(doi)
        except ClientError:
            return None
