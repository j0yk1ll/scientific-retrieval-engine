"""Client for interacting with a GROBID server."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests

from retrieval.exceptions import ParseError


class GrobidClient:
    """Lightweight HTTP wrapper around the GROBID service."""

    def __init__(
        self,
        base_url: str,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be provided")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.base_url = str(base_url).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def process_fulltext(self, pdf_path: Path | str) -> str:
        """Submit a PDF to GROBID and return the TEI XML response."""

        path = Path(pdf_path)
        if not path.is_file():
            raise ParseError(f"PDF path does not exist: {path}")

        url = f"{self.base_url}/api/processFulltextDocument"
        files = {
            "input": (path.name, path.read_bytes(), "application/pdf"),
        }
        data = {
            "consolidateHeader": "1",
            "consolidateCitations": "0",
            "teiCoordinates": "0",
        }

        try:
            response = self.session.post(url, files=files, data=data, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network error paths
            raise ParseError("Failed to contact GROBID service") from exc

        tei_xml = response.text
        if not tei_xml.strip():
            raise ParseError("Empty TEI response from GROBID")

        return tei_xml
