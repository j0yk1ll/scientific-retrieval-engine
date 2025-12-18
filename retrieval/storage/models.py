"""Pydantic models representing storage-layer entities."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExternalSource(str, Enum):
    """Supported external identifier namespaces."""

    ARXIV = "arxiv"
    DOI = "doi"


class VenueType(str, Enum):
    """Type classification for publication venues."""

    JOURNAL = "journal"
    CONFERENCE = "conference"
    PREPRINT = "preprint"
    BOOK = "book"
    OTHER = "other"


class ParserName(str, Enum):
    """Supported document parsers."""

    GROBID = "grobid"
    OTHER = "other"


class ChunkKind(str, Enum):
    """Classification of chunk content type."""

    TITLE = "title"
    ABSTRACT = "abstract"
    SECTION_PARAGRAPH = "section_paragraph"
    FIGURE_CAPTION = "figure_caption"
    TABLE_CAPTION = "table_caption"
    EQUATION = "equation"
    METHODS_STEP = "methods_step"
    RESULT_STATEMENT = "result_statement"
    LIMITATION_STATEMENT = "limitation_statement"
    REFERENCE_ENTRY = "reference_entry"


# ─────────────────────────────────────────────────────────────────────────────
# Paper models (internal database representation)
# ─────────────────────────────────────────────────────────────────────────────


class Paper(BaseModel):
    """Metadata describing a single paper (internal DB model)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    paper_id: str  # UUID or content-derived stable ID
    title: str
    abstract: str | None = None
    doi: str | None = None
    published_at: date | None = None
    external_source: str | None = None  # "arxiv" or "doi"
    external_id: str | None = None
    venue_name: str | None = None
    venue_type: str | None = None
    venue_publisher: str | None = None
    keywords: list[str] = Field(default_factory=list)
    content_hash: str | None = None
    pdf_sha256: str | None = None
    provenance_source: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    parser_warnings: list[str] = Field(default_factory=list)
    ingested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaperAuthor(BaseModel):
    """Author associated with a paper."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    paper_id: int
    author_name: str
    author_order: int = Field(gt=0)
    orcid: str | None = None
    affiliations: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class PaperSource(BaseModel):
    """Provenance information for a paper."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    paper_id: int
    source_name: str
    source_identifier: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class PaperFile(BaseModel):
    """File record associated with a paper."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    paper_id: int
    file_type: str
    location: str
    checksum: str | None = None
    created_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Chunk models (internal database representation)
# ─────────────────────────────────────────────────────────────────────────────


class Chunk(BaseModel):
    """Chunk of TEI content belonging to a paper (internal DB model)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    chunk_id: str  # Stable chunk identifier
    paper_id: int
    paper_uuid: str  # Reference to paper.paper_id (UUID string)
    kind: str = ChunkKind.SECTION_PARAGRAPH.value
    position: int = Field(ge=0)  # Global reading order
    section_title: str | None = None  # Title of the section
    order_in_section: int | None = None
    content: str
    language: str | None = None
    citations: list[str] = Field(default_factory=list)  # Full citation strings
    # PDF anchoring
    pdf_page_start: int | None = None
    pdf_page_end: int | None = None
    pdf_bbox: list[float] | None = None  # [x0, y0, x1, y1]
    # TEI anchoring
    tei_id: str | None = None
    tei_xpath: str | None = None
    # Character range in source
    char_start: int | None = None
    char_end: int | None = None
    created_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Output schemas (JSON API representation matching the spec)
# ─────────────────────────────────────────────────────────────────────────────


class AuthorOutput(BaseModel):
    """Author in the output schema."""

    name: str
    orcid: str | None = None
    affiliations: list[str] = Field(default_factory=list)


class VenueOutput(BaseModel):
    """Venue information in the output schema."""

    name: str | None = None
    type: VenueType | None = None
    publisher: str | None = None


class FingerprintsOutput(BaseModel):
    """Content fingerprints in the output schema."""

    content_hash: str
    pdf_sha256: str | None = None


class ParserOutput(BaseModel):
    """Parser information in the output schema."""

    name: Literal["grobid", "other"]
    version: str


class ProvenanceOutput(BaseModel):
    """Provenance information in the output schema."""

    source: str
    parser: ParserOutput
    ingested_at: datetime
    parser_warnings: list[str] = Field(default_factory=list)


class PaperRecordOutput(BaseModel):
    """Output schema for a paper record (matches PaperRecord JSON schema)."""

    paper_id: str
    external_source: ExternalSource
    external_id: str
    title: str
    authors: list[AuthorOutput] = Field(default_factory=list)
    venue: VenueOutput | None = None
    publication_date: str | None = None  # ISO date or partial
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    fingerprints: FingerprintsOutput
    provenance: ProvenanceOutput


class TextOutput(BaseModel):
    """Text content in the output schema."""

    content: str
    language: str | None = None


class PdfAnchorOutput(BaseModel):
    """PDF anchoring information in the output schema."""

    page_start: int | None = None
    page_end: int | None = None
    bbox: list[float] | None = None  # [x0, y0, x1, y1]


class TeiAnchorOutput(BaseModel):
    """TEI anchoring information in the output schema."""

    tei_id: str | None = None
    xpath: str | None = None


class CharRangeOutput(BaseModel):
    """Character range in the output schema."""

    start: int | None = None
    end: int | None = None


class PaperChunkOutput(BaseModel):
    """Output schema for a paper chunk (matches PaperChunk JSON schema)."""

    chunk_id: str
    paper_id: str
    kind: ChunkKind
    position: int = Field(ge=0)
    title: str | None = None  # Section title
    order_in_section: int | None = None
    pdf: PdfAnchorOutput | None = None
    tei: TeiAnchorOutput | None = None
    char_range: CharRangeOutput | None = None
    text: str  # Flattened text content
    citations: list[str] = Field(default_factory=list)  # Full citation strings


# ─────────────────────────────────────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────────────────────────────────────


def generate_paper_uuid() -> str:
    """Generate a new UUID for a paper."""
    return str(uuid.uuid4())


def generate_chunk_id(paper_uuid: str, position: int) -> str:
    """Generate a stable chunk ID from paper UUID and position."""
    return f"{paper_uuid}:chunk:{position}"


def compute_content_hash(content: str) -> str:
    """Compute a SHA-256 hash of content for fingerprinting."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_pdf_hash(pdf_bytes: bytes) -> str:
    """Compute a SHA-256 hash of PDF bytes."""
    return hashlib.sha256(pdf_bytes).hexdigest()
