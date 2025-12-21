from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class ValidationResult:
    is_pdf: bool
    status_code: int | None = None
    content_type: str | None = None


def validate_pdf_url(
    session: requests.Session,
    url: str,
    timeout: float | tuple[float, float],
) -> ValidationResult:
    head_response = None
    try:
        head_response = session.head(url, allow_redirects=True, timeout=timeout)
    except requests.RequestException:
        head_response = None

    if head_response:
        content_type = head_response.headers.get("Content-Type")
        if _is_pdf_content_type(content_type):
            return ValidationResult(
                is_pdf=True,
                status_code=head_response.status_code,
                content_type=content_type,
            )

    try:
        get_response = session.get(
            url,
            headers={"Range": "bytes=0-2047"},
            allow_redirects=True,
            timeout=timeout,
        )
    except requests.RequestException:
        status_code = head_response.status_code if head_response else None
        content_type = (
            head_response.headers.get("Content-Type") if head_response else None
        )
        return ValidationResult(
            is_pdf=False,
            status_code=status_code,
            content_type=content_type,
        )

    content_type = get_response.headers.get("Content-Type")
    if _is_pdf_content_type(content_type):
        return ValidationResult(
            is_pdf=True,
            status_code=get_response.status_code,
            content_type=content_type,
        )

    body = get_response.content or b""
    return ValidationResult(
        is_pdf=body.startswith(b"%PDF"),
        status_code=get_response.status_code,
        content_type=content_type,
    )


def _is_pdf_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    return "pdf" in content_type.lower()
