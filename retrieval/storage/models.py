"""Pydantic models representing storage-layer entities."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Paper(BaseModel):
    """Metadata describing a single paper."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    title: str
    abstract: str | None = None
    doi: str | None = None
    published_at: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaperAuthor(BaseModel):
    """Author associated with a paper."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    paper_id: int
    author_name: str
    author_order: int = Field(gt=0)
    affiliation: str | None = None
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


class Chunk(BaseModel):
    """Chunk of TEI content belonging to a paper."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    paper_id: int
    chunk_order: int = Field(ge=0)
    content: str
    created_at: datetime | None = None
