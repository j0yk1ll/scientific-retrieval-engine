"""Application configuration for the retrieval engine."""

from pathlib import Path
from typing import Any

from email.utils import parseaddr

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalConfig(BaseSettings):  # type: ignore[misc]
    """Settings controlling data paths and service endpoints."""

    db_dsn: str = Field(..., description="PostgreSQL DSN for metadata and chunks")
    data_dir: Path = Field(..., description="Directory for downloaded documents")
    index_dir: Path = Field(..., description="Directory for ColBERT index data")
    grobid_url: AnyHttpUrl = Field(..., description="HTTP endpoint for the GROBID service")
    unpaywall_email: str = Field(..., description="Contact email for Unpaywall requests")
    request_timeout_s: float = Field(
        30.0, description="Default timeout (in seconds) for outbound HTTP requests"
    )

    model_config = SettingsConfigDict(env_prefix="RETRIEVAL_", env_file=".env", extra="ignore")

    def model_post_init(self, __context: Any) -> None:
        """Normalize paths to absolute locations."""

        self.data_dir = self.data_dir.expanduser().resolve()
        self.index_dir = self.index_dir.expanduser().resolve()

    @field_validator("unpaywall_email")
    @classmethod
    def validate_unpaywall_email(cls, value: str) -> str:
        name, addr = parseaddr(value)
        if "@" not in addr:
            raise ValueError("unpaywall_email must contain a valid email address")
        return addr
