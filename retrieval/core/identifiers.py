from __future__ import annotations

import re
import unicodedata

_DOI_PREFIX_PATTERN = re.compile(r"^(https?://)?(dx\.)?doi\.org/", re.IGNORECASE)


def normalize_doi(doi: str | None) -> str | None:
    """Normalize a DOI string into a canonical lowercase form.

    The normalization removes leading DOI prefixes (e.g., ``https://doi.org/`` or
    ``doi:``), trims whitespace, and lowercases the remaining identifier. Empty
    or missing values return ``None``.
    """

    if not doi:
        return None

    cleaned = doi.strip()
    cleaned = _DOI_PREFIX_PATTERN.sub("", cleaned)
    if cleaned.lower().startswith("doi:"):
        cleaned = cleaned.split(":", 1)[1]
    cleaned = cleaned.strip().lower()

    return cleaned or None


def normalize_title(title: str | None) -> str:
    """Normalize a title by collapsing whitespace and normalizing unicode."""

    if not title:
        return ""

    normalized = unicodedata.normalize("NFKC", title)
    collapsed = " ".join(normalized.split())
    return collapsed.lower()
