"""Client wrapper for interacting with a GROBID service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from .base import BaseHttpClient


class GrobidClient(BaseHttpClient):
    """Minimal client for submitting PDFs to GROBID.

    The client exposes a :meth:`process_fulltext` helper that submits a PDF to the
    ``/api/processFulltextDocument`` endpoint and returns the TEI XML response as a
    string. The base URL is configurable to support remote or containerized
    deployments.
    """

    BASE_URL = "http://localhost:8070"

    def process_fulltext(
        self,
        pdf: Union[bytes, str, Path],
        *,
        consolidate_header: bool = False,
        consolidate_citations: bool = False,
        tei_coordinates: bool = False,
    ) -> str:
        """Process a PDF and return TEI XML.

        Args:
            pdf: Raw PDF bytes or a filesystem path to the PDF.
            consolidate_header: Whether to consolidate header metadata.
            consolidate_citations: Whether to consolidate citation metadata.
            tei_coordinates: Whether to include TEI coordinates in the response.

        Returns:
            The TEI XML string returned by GROBID.
        """

        filename, pdf_bytes = self._normalize_pdf_input(pdf)
        data: Dict[str, Any] = {
            "consolidateHeader": "1" if consolidate_header else "0",
            "consolidateCitations": "1" if consolidate_citations else "0",
            "teiCoordinates": "1" if tei_coordinates else "0",
        }
        files = {"input": (filename, pdf_bytes, "application/pdf")}

        response = self._request(
            "POST",
            "/api/processFulltextDocument",
            data=data,
            files=files,
            headers={"Accept": "application/xml"},
        )
        return response.text

    @staticmethod
    def _normalize_pdf_input(pdf: Union[bytes, str, Path]) -> tuple[str, bytes]:
        if isinstance(pdf, (str, Path)):
            pdf_path = Path(pdf)
            return pdf_path.name, pdf_path.read_bytes()
        return "document.pdf", pdf

