"""Shared base classes for title-only preprint search."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

import requests


@dataclass
class PreprintResult:
    provider: str
    title: str
    url: str
    pdf_url: Optional[str] = None
    authors: Optional[list[str]] = None
    published: Optional[str] = None


class BasePreprintClient(ABC):
    """Abstract base class for all title-only preprint clients."""

    provider: str

    def __init__(self, *, session: Optional[requests.Session] = None, timeout: float = 10.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    @abstractmethod
    def search(self, title: str, *, max_results: int = 5) -> List[PreprintResult]:
        """Search by title, returning a list of candidate results."""

