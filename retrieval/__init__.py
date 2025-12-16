"""Retrieval engine package scaffold.

This module ensures environment variables from a local `.env` file are
loaded early via `python-dotenv` so downstream modules and `pydantic`
settings can pick them up.
"""

from dotenv import load_dotenv

# Load environment variables from a `.env` file in the repository root.
# Do not override existing environment variables unless explicitly needed.
load_dotenv(dotenv_path=".env", override=False)

from .config import RetrievalConfig
from .engine import RetrievalEngine
from .exceptions import (
    AcquisitionError,
    ConfigError,
    DatabaseError,
    IndexError,
    ParseError,
    RetrievalError,
)

__all__ = [
    "RetrievalConfig",
    "RetrievalEngine",
    "AcquisitionError",
    "ConfigError",
    "DatabaseError",
    "IndexError",
    "ParseError",
    "RetrievalError",
]
