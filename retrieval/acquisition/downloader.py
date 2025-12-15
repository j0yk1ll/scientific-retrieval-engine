"""Robust PDF downloader with validation and metadata extraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

from retrieval.exceptions import AcquisitionError


PDF_SIGNATURE = b"%PDF-"


class DownloadError(AcquisitionError):
    """Raised when a PDF cannot be safely downloaded."""


@dataclass
class DownloadMetadata:
    """HTTP metadata captured during download."""

    etag: Optional[str]
    last_modified: Optional[str]
    content_type: Optional[str]
    content_length: Optional[int]


@dataclass
class DownloadedPDF:
    """Downloaded PDF payload and associated metadata."""

    content: bytes
    metadata: DownloadMetadata


class PDFDownloader:
    """Stream and validate PDF downloads with retries and size limits."""

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
        max_size: int = 20 * 1024 * 1024,
        max_retries: int = 3,
        chunk_size: int = 64 * 1024,
    ) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")

        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_size = max_size
        self.max_retries = max_retries
        self.chunk_size = chunk_size

    def download(self, url: str) -> DownloadedPDF:
        """Download a PDF from *url* with validation and retries."""

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._get(url)
                return self._consume_response(response)
            except (requests.RequestException, DownloadError) as exc:  # pragma: no cover - branch validated via retries
                if attempt >= self.max_retries:
                    raise DownloadError(f"Failed to download PDF after {self.max_retries} attempts") from exc

        # This should never be reached because the loop either returns or raises.
        raise DownloadError("Unexpected download state")

    def _get(self, url: str) -> requests.Response:
        response = self.session.get(url, stream=True, timeout=self.timeout)
        response.raise_for_status()
        return response

    def _consume_response(self, response: requests.Response) -> DownloadedPDF:
        headers = response.headers
        content_type = headers.get("Content-Type")
        etag = headers.get("ETag")
        last_modified = headers.get("Last-Modified")

        content_length_header = headers.get("Content-Length")
        content_length: Optional[int] = None
        if content_length_header and content_length_header.isdigit():
            content_length = int(content_length_header)
            if content_length > self.max_size:
                raise DownloadError("PDF exceeds maximum allowed size")

        chunks: list[bytes] = []
        total = 0
        first_chunk: Optional[bytes] = None

        for chunk in response.iter_content(chunk_size=self.chunk_size):
            if not chunk:
                continue
            if first_chunk is None:
                first_chunk = chunk
            total += len(chunk)
            if total > self.max_size:
                raise DownloadError("PDF exceeds maximum allowed size")
            chunks.append(chunk)

        payload = b"".join(chunks)
        if not payload:
            raise DownloadError("Empty PDF response")

        if not self._is_pdf(content_type, first_chunk or payload):
            raise DownloadError("Response is not a valid PDF")

        metadata = DownloadMetadata(
            etag=etag,
            last_modified=last_modified,
            content_type=content_type,
            content_length=content_length or len(payload),
        )

        return DownloadedPDF(content=payload, metadata=metadata)

    def _is_pdf(self, content_type: Optional[str], first_chunk: bytes) -> bool:
        if content_type and content_type.lower().startswith("application/pdf"):
            return True
        return first_chunk.startswith(PDF_SIGNATURE)
