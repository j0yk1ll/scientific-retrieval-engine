from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import importlib.util
import os
from pathlib import Path
from typing import Optional
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
    grobid_base_url: Optional[str] = None
    # Practical caps to avoid unbounded citation crawls.
    citation_limit: int = 500
    openalex_citation_max_pages: int = 5
    session: Optional[requests.Session] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._try_load_dotenv_from_project_root()
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        env_timeout = self._get_env_value("RETRIEVAL_REQUEST_TIMEOUT_S")
        if env_timeout and self.timeout == 10.0:
            self.timeout = float(env_timeout)

        env_unpaywall_email = self._get_env_value("RETRIEVAL_UNPAYWALL_EMAIL")
        if env_unpaywall_email and self.unpaywall_email is None:
            self.unpaywall_email = env_unpaywall_email

        env_grobid_url = self._get_env_value("RETRIEVAL_GROBID_URL")
        if env_grobid_url and self.grobid_base_url is None:
            self.grobid_base_url = env_grobid_url

    def build_session(self) -> requests.Session:
        """Return a configured :class:`requests.Session` using the settings."""

        if self.session is not None:
            session = self.session
        else:
            session = requests.Session()

        if self.user_agent:
            session.headers.setdefault("User-Agent", self.user_agent)
        return session


    def _get_env_value(self, name: str) -> Optional[str]:
        value = os.environ.get(name)
        if value is None:
            return None
        value = value.strip()
        return value or None


    def _try_load_dotenv_from_project_root(self) -> None:
        """
        Best-effort dotenv loading.
        - If python-dotenv is not installed: do nothing.
        - If .env is missing: do nothing.
        - Does NOT override already-set environment variables.
        """
        if importlib.util.find_spec("dotenv") is None:
            return

        project_root = Path(__file__).resolve().parents[2]
        
        env_path = project_root / ".env"
        
        if not env_path.exists():
            return

        dotenv = importlib.import_module("dotenv")
        dotenv.load_dotenv(dotenv_path=str(env_path), override=False)
