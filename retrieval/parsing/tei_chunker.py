"""Deterministic chunking for TEI XML documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from lxml import etree

from retrieval.exceptions import ParseError
from retrieval.parsing.bibliography import (
    extract_bibliography_map,
    extract_citations_from_text_with_bib,
)

NSMAP = {"tei": "http://www.tei-c.org/ns/1.0"}


def _normalize_text(element: etree._Element) -> str:
    """Return collapsed, stripped text content for an element."""

    text_content = " ".join(element.itertext())
    return " ".join(text_content.split())


@dataclass(frozen=True)
class TEIChunk:
    """Represents a deterministic chunk extracted from TEI."""

    id: str
    kind: str  # e.g., "title", "abstract", "section_paragraph"
    position: int  # Global reading order (0-indexed)
    section_title: str | None  # Title of the innermost section
    order_in_section: int | None  # Position within section
    text: str
    citations: List[str] = field(default_factory=list)  # Full citation strings
    tei_id: str | None = None  # TEI element ID if available
    tei_xpath: str | None = None  # XPath to source element


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

        # Extract bibliography mapping for citation resolution
        bib_map = extract_bibliography_map(root)

        chunks: list[TEIChunk] = []
        global_position = 0
        
        for section_path, paragraphs in self._iter_sections(body, ()):  # depth-first order
            buffer: list[str] = []
            order_in_section = 0
            section_title = section_path[-1] if section_path else None
            
            for paragraph in paragraphs:
                candidate = "\n\n".join(buffer + [paragraph]) if buffer else paragraph
                if buffer and len(candidate) > self.max_chars:
                    chunk_text = "\n\n".join(buffer)
                    chunks.append(
                        TEIChunk(
                            id=f"chunk-{global_position}",
                            kind="section_paragraph",
                            position=global_position,
                            section_title=section_title,
                            order_in_section=order_in_section,
                            text=chunk_text,
                            citations=extract_citations_from_text_with_bib(chunk_text, bib_map),
                        )
                    )
                    global_position += 1
                    order_in_section += 1
                    buffer = [paragraph]
                else:
                    buffer = [candidate] if not buffer else buffer + [paragraph]
            if buffer:
                chunk_text = "\n\n".join(buffer)
                chunks.append(
                    TEIChunk(
                        id=f"chunk-{global_position}",
                        kind="section_paragraph",
                        position=global_position,
                        section_title=section_title,
                        order_in_section=order_in_section,
                        text=chunk_text,
                        citations=extract_citations_from_text_with_bib(chunk_text, bib_map),
                    )
                )
                global_position += 1

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
        # Sort sibling <div> elements by their <head> text to provide a
        # deterministic, alphabetic ordering of sections at each level.
        divs = list(node.findall("tei:div", namespaces=NSMAP))
        def _div_title(d: etree._Element) -> str:
            h = d.find("tei:head", namespaces=NSMAP)
            return _normalize_text(h) if h is not None else ""

        divs.sort(key=_div_title)

        for div in divs:
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
