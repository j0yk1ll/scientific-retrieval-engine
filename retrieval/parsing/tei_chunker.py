"""Deterministic chunking for TEI XML documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from lxml import etree

from retrieval.exceptions import ParseError

NSMAP = {"tei": "http://www.tei-c.org/ns/1.0"}


def _normalize_text(element: etree._Element) -> str:
    """Return collapsed, stripped text content for an element."""

    text_content = " ".join(element.itertext())
    return " ".join(text_content.split())


@dataclass(frozen=True)
class TEIChunk:
    """Represents a deterministic chunk extracted from TEI."""

    id: str
    section: str
    text: str


class TEIChunker:
    """Chunk TEI XML into deterministic passages."""

    def __init__(self, max_chars: int = 1200) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        self.max_chars = max_chars

    def chunk(self, tei_xml: str) -> List[TEIChunk]:
        """Parse TEI XML and return ordered chunks respecting *max_chars*."""

        root = self._parse(tei_xml)
        body = root.find(".//tei:text/tei:body", namespaces=NSMAP)
        if body is None:
            raise ParseError("TEI document is missing <text><body>")

        chunks: list[TEIChunk] = []
        counter = 1
        for section_path, paragraphs in self._iter_sections(body, ()):  # depth-first order
            buffer: list[str] = []
            for paragraph in paragraphs:
                candidate = "\n\n".join(buffer + [paragraph]) if buffer else paragraph
                if buffer and len(candidate) > self.max_chars:
                    chunks.append(
                        TEIChunk(
                            id=f"chunk-{counter}",
                            section=" > ".join(section_path),
                            text="\n\n".join(buffer),
                        )
                    )
                    counter += 1
                    buffer = [paragraph]
                else:
                    buffer = [candidate] if not buffer else buffer + [paragraph]
            if buffer:
                chunks.append(
                    TEIChunk(
                        id=f"chunk-{counter}",
                        section=" > ".join(section_path),
                        text="\n\n".join(buffer),
                    )
                )
                counter += 1

        if not chunks:
            raise ParseError("No paragraphs found in TEI document")

        return chunks

    def _parse(self, tei_xml: str) -> etree._Element:
        try:
            return etree.fromstring(tei_xml.encode("utf-8"))
        except (etree.XMLSyntaxError, ValueError) as exc:  # pragma: no cover - defensive
            raise ParseError("Invalid TEI XML") from exc

    def _iter_sections(
        self, node: etree._Element, path: Iterable[str]
    ) -> Iterable[tuple[list[str], list[str]]]:
        for div in node.findall("tei:div", namespaces=NSMAP):
            head = div.find("tei:head", namespaces=NSMAP)
            title = _normalize_text(head) if head is not None else None
            section_path = list(path)
            if title:
                section_path.append(title)

            paragraphs = [
                text
                for p in div.findall("tei:p", namespaces=NSMAP)
                if (text := _normalize_text(p))
            ]
            if paragraphs:
                yield section_path, paragraphs

            yield from self._iter_sections(div, section_path)
