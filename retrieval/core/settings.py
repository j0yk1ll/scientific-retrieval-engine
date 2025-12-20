from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import importlib
import importlib.util
import requests


@dataclass(slots=True)
class RetrievalSettings:
    """Configuration for HTTP clients and external integrations."""

    timeout: float = 10.0
    user_agent: str = "scientific-retrieval-engine"
    unpaywall_email: Optional[str] = None
    openalex_base_url: Optional[str] = None
    crossref_base_url: Optional[str] = None
    datacite_base_url: Optional[str] = None
    semanticscholar_base_url: Optional[str] = None
    semanticscholar_api_key: Optional[str] = None
    unpaywall_base_url: Optional[str] = None
    enable_grobid: bool = False
    grobid_base_url: Optional[str] = None
    enable_semanticscholar_citation_fallback: bool = True
    enable_openalex_citation_fallback: bool = True
    enable_unpaywall: bool = True
    # Practical caps to avoid unbounded citation crawls.
    citation_limit: int = 500
    openalex_citation_max_pages: int = 5
    session: Optional[requests.Session] = field(default=None, repr=False)

    def build_session(self) -> requests.Session:
        """Return a configured :class:`requests.Session` using the settings."""

        if self.session is not None:
            session = self.session
        else:
            session = requests.Session()

        if self.user_agent:
            session.headers.setdefault("User-Agent", self.user_agent)
        return session


def load_dotenv_from_root(override: bool = False) -> None:
    """Optionally load environment variables from a ``.env`` file.

    This helper is intentionally opt-in to avoid mutating the environment when the
    library is imported.
    """

    if importlib.util.find_spec("dotenv") is None:
        raise ImportError("python-dotenv is required to load .env files")

    dotenv = importlib.import_module("dotenv")
    dotenv.load_dotenv(dotenv_path=".env", override=override)
