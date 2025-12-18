"""Chunk parsed TEI XML returned by GROBID into structured text blocks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from lxml import etree
import tiktoken

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


@dataclass
class GrobidSection:
    title: str
    paragraphs: List[str]


@dataclass
class GrobidDocument:
    paper_id: str
    title: str
    abstract: List[str]
    sections: List[GrobidSection]
    references: List[str]


@dataclass
class GrobidChunk:
    chunk_id: str
    paper_id: str
    section: str
    content: str
    start_char: int
    end_char: int
    token_count: int


class GrobidChunker:
    """Turn GROBID TEI output into reproducible text chunks."""

    def __init__(self, paper_id: str, tei_xml: str, *, encoding_name: str = "cl100k_base") -> None:
        self.paper_id = paper_id
        self.tei_xml = tei_xml
        self.encoding = self._build_encoding(encoding_name)
        self.document = self._parse_document()

    def chunk(self, *, max_tokens: int = 400, max_chars: int = 2000) -> List[GrobidChunk]:
        """Chunk the TEI XML into bounded pieces while preserving section context."""

        chunks: List[GrobidChunk] = []
        running_offset = 0
        chunk_index = 1
        header_token_count = 0

        sections = self._ordered_sections()
        for section in sections:
            paragraph_queue = list(self._split_long_paragraphs(section.paragraphs, max_chars))
            while paragraph_queue:
                current_parts: List[str] = []
                header_prefix = f"{section.title}\n\n"
                available_characters = max(max_chars - len(header_prefix), 1)
                header_token_count = self._count_tokens(header_prefix)
                available_tokens = max(max_tokens - header_token_count, 1)

                while paragraph_queue:
                    next_paragraph = paragraph_queue[0]
                    candidate_parts = current_parts + [next_paragraph]
                    candidate_text = header_prefix + "\n\n".join(candidate_parts)
                    candidate_tokens = self._count_tokens(candidate_text)

                    if (
                        len(candidate_text) <= max_chars
                        and candidate_tokens <= max_tokens
                    ):
                        current_parts.append(paragraph_queue.pop(0))
                        continue

                    if current_parts:
                        break

                    trimmed_paragraph = self._trim_to_limits(
                        next_paragraph, available_characters, available_tokens
                    )
                    current_parts.append(trimmed_paragraph)
                    paragraph_queue[0] = next_paragraph[len(trimmed_paragraph) :].lstrip()
                    if not paragraph_queue[0]:
                        paragraph_queue.pop(0)
                    break

                chunk_text = header_prefix + "\n\n".join(current_parts)
                chunk_tokens = self._count_tokens(chunk_text)

                chunk = GrobidChunk(
                    chunk_id=f"{self.paper_id}-chunk-{chunk_index}",
                    paper_id=self.paper_id,
                    section=section.title,
                    content=chunk_text,
                    start_char=running_offset,
                    end_char=running_offset + len(chunk_text),
                    token_count=chunk_tokens,
                )
                chunks.append(chunk)
                running_offset += len(chunk_text)
                chunk_index += 1

        return chunks

    def _ordered_sections(self) -> List[GrobidSection]:
        sections: List[GrobidSection] = []
        if self.document.title:
            sections.append(GrobidSection(title="Title", paragraphs=[self.document.title]))
        if self.document.abstract:
            sections.append(GrobidSection(title="Abstract", paragraphs=self.document.abstract))
        sections.extend(self.document.sections)
        return sections

    def _parse_document(self) -> GrobidDocument:
        root = etree.fromstring(self.tei_xml.encode())

        title_nodes = root.xpath(".//tei:titleStmt/tei:title", namespaces=TEI_NS)
        title = self._node_text(title_nodes[0]) if title_nodes else ""

        abstract_nodes = root.xpath(".//tei:abstract/tei:p", namespaces=TEI_NS)
        abstract = [self._node_text(node) for node in abstract_nodes if self._node_text(node)]

        section_nodes = root.xpath(".//tei:text/tei:body/tei:div", namespaces=TEI_NS)
        sections: List[GrobidSection] = []
        for section_node in section_nodes:
            head_nodes = section_node.xpath("./tei:head", namespaces=TEI_NS)
            section_title = self._node_text(head_nodes[0]) if head_nodes else "Untitled"
            paragraph_nodes = section_node.xpath("./tei:p", namespaces=TEI_NS)
            paragraphs = [
                self._node_text(paragraph)
                for paragraph in paragraph_nodes
                if self._node_text(paragraph)
            ]
            if paragraphs:
                sections.append(GrobidSection(title=section_title, paragraphs=paragraphs))

        reference_nodes = root.xpath(".//tei:listBibl//tei:title", namespaces=TEI_NS)
        references = [self._node_text(node) for node in reference_nodes if self._node_text(node)]

        return GrobidDocument(
            paper_id=self.paper_id,
            title=title,
            abstract=abstract,
            sections=sections,
            references=references,
        )

    @staticmethod
    def _node_text(node: etree._Element) -> str:
        return " ".join(" ".join(node.itertext()).split()).strip()

    def _count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def _split_long_paragraphs(self, paragraphs: Sequence[str], max_chars: int) -> List[str]:
        parts: List[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= max_chars:
                parts.append(paragraph)
                continue
            parts.extend(self._split_by_whitespace(paragraph, max_chars))
        return parts

    @staticmethod
    def _split_by_whitespace(text: str, max_chars: int) -> List[str]:
        if not text:
            return [text]
        words = text.split()
        if not words:
            return [text[:max_chars]]

        chunks: List[str] = []
        current_words: List[str] = []
        for word in words:
            candidate = " ".join(current_words + [word]) if current_words else word
            if len(candidate) > max_chars and current_words:
                chunks.append(" ".join(current_words))
                current_words = [word]
            elif len(candidate) > max_chars:
                chunks.append(word[:max_chars])
            else:
                current_words.append(word)

        if current_words:
            chunks.append(" ".join(current_words))
        return chunks

    def _trim_to_limits(self, text: str, max_chars: int, max_tokens: int) -> str:
        trimmed = text[:max_chars]
        encoded = self.encoding.encode(trimmed)
        if len(encoded) > max_tokens:
            encoded = encoded[:max_tokens]
            trimmed = self.encoding.decode(encoded)
        return trimmed.strip()

    def _build_encoding(self, encoding_name: str):
        try:
            return tiktoken.get_encoding(encoding_name)
        except Exception:  # pragma: no cover - network or cache dependent
            return _WhitespaceEncoding()


class _WhitespaceEncoding:
    """Minimal encoding fallback that tokenizes on whitespace."""

    def encode(self, text: str) -> List[str]:
        return text.split()

    def decode(self, tokens: List[str]) -> str:
        return " ".join(tokens)

