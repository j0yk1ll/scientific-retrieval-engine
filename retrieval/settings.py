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
    enable_unpaywall: bool = False
    unpaywall_email: Optional[str] = None
    openalex_base_url: Optional[str] = None
    semanticscholar_base_url: Optional[str] = None
    opencitations_base_url: Optional[str] = None
    unpaywall_base_url: Optional[str] = None
    session: Optional[requests.Session] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.enable_unpaywall and not self.unpaywall_email:
            raise ValueError("Unpaywall email is required when enable_unpaywall is True")

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
