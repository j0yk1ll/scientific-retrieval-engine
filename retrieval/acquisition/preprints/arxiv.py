"""Title-only search for arXiv."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List

import requests

from .base import BasePreprintClient, PreprintResult


class ArxivClient(BasePreprintClient):
    provider = "arxiv"
    BASE_URL = "http://export.arxiv.org/api/query"

    def search(self, title: str, *, max_results: int = 5) -> List[PreprintResult]:  # type: ignore[override]
        params = {
            "search_query": f'ti:"{title}"',
            "start": 0,
            "max_results": max_results,
        }
        response = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        return self._parse_feed(response.text)

    def _parse_feed(self, xml_text: str) -> List[PreprintResult]:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml_text)
        results: List[PreprintResult] = []
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
            pdf_url = None
            for link in entry.findall("atom:link", ns):
                if link.attrib.get("type") == "application/pdf":
                    pdf_url = link.attrib.get("href")
                    break
            authors = [
                author.text.strip()
                for author in entry.findall("atom:author/atom:name", ns)
                if author.text
            ]
            results.append(
                PreprintResult(
                    provider=self.provider,
                    title=title,
                    url=entry_id or pdf_url or "",
                    pdf_url=pdf_url,
                    authors=authors or None,
                )
            )
        return results
