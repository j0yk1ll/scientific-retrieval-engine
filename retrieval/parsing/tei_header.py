"""Utilities for extracting metadata from GROBID TEI XML headers.

This module parses the teiHeader section of GROBID-generated TEI documents
to extract paper metadata including title, authors, abstract, and keywords.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from lxml import etree

NSMAP = {"tei": "http://www.tei-c.org/ns/1.0"}


def _get_text(element: etree._Element | None) -> str:
    """Extract normalized text from an element."""
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


@dataclass
class TEIAuthor:
    """Author information extracted from TEI header."""
    
    name: str
    orcid: Optional[str] = None
    affiliations: List[str] = field(default_factory=list)


@dataclass
class TEIMetadata:
    """Metadata extracted from TEI header."""
    
    title: Optional[str] = None
    abstract: Optional[str] = None
    authors: List[TEIAuthor] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    doi: Optional[str] = None


def _extract_author_name(author_elem: etree._Element) -> str:
    """Extract author name from an author element."""
    persname = author_elem.find("tei:persName", namespaces=NSMAP)
    if persname is None:
        return ""
    
    forename = persname.find("tei:forename", namespaces=NSMAP)
    surname = persname.find("tei:surname", namespaces=NSMAP)
    
    parts = []
    if forename is not None:
        # Handle multiple forename elements (first name, middle name)
        forename_text = _get_text(forename)
        if forename_text:
            parts.append(forename_text)
    if surname is not None:
        surname_text = _get_text(surname)
        if surname_text:
            parts.append(surname_text)
    
    return " ".join(parts) if parts else _get_text(persname)


def _extract_author_orcid(author_elem: etree._Element) -> Optional[str]:
    """Extract ORCID from author element if present."""
    # GROBID may encode ORCID in an idno element
    idno = author_elem.find(".//tei:idno[@type='ORCID']", namespaces=NSMAP)
    if idno is not None:
        orcid = _get_text(idno)
        if orcid:
            return orcid
    return None


def _extract_author_affiliations(author_elem: etree._Element) -> List[str]:
    """Extract affiliations from author element."""
    affiliations = []
    for affil in author_elem.findall("tei:affiliation", namespaces=NSMAP):
        # Try to get organization name
        org = affil.find(".//tei:orgName", namespaces=NSMAP)
        if org is not None:
            org_text = _get_text(org)
            if org_text and org_text not in affiliations:
                affiliations.append(org_text)
        else:
            # Fall back to full affiliation text
            affil_text = _get_text(affil)
            if affil_text and affil_text not in affiliations:
                affiliations.append(affil_text)
    return affiliations


def _extract_authors(header: etree._Element) -> List[TEIAuthor]:
    """Extract all authors from TEI header."""
    authors = []
    
    # Authors are in sourceDesc/biblStruct/analytic/author
    # or in fileDesc/sourceDesc/biblStruct/analytic/author
    for author_elem in header.findall(
        ".//tei:sourceDesc/tei:biblStruct/tei:analytic/tei:author",
        namespaces=NSMAP
    ):
        name = _extract_author_name(author_elem)
        if not name:
            continue
        
        author = TEIAuthor(
            name=name,
            orcid=_extract_author_orcid(author_elem),
            affiliations=_extract_author_affiliations(author_elem),
        )
        authors.append(author)
    
    return authors


def _extract_title(header: etree._Element) -> Optional[str]:
    """Extract paper title from TEI header."""
    # Title is in sourceDesc/biblStruct/analytic/title[@type='main']
    # or just sourceDesc/biblStruct/analytic/title
    title_elem = header.find(
        ".//tei:sourceDesc/tei:biblStruct/tei:analytic/tei:title[@type='main']",
        namespaces=NSMAP
    )
    if title_elem is None:
        title_elem = header.find(
            ".//tei:sourceDesc/tei:biblStruct/tei:analytic/tei:title",
            namespaces=NSMAP
        )
    
    if title_elem is not None:
        title = _get_text(title_elem)
        if title:
            return title
    
    # Fallback: try titleStmt/title
    title_elem = header.find(".//tei:titleStmt/tei:title", namespaces=NSMAP)
    if title_elem is not None:
        title = _get_text(title_elem)
        if title:
            return title
    
    return None


def _extract_abstract(root: etree._Element) -> Optional[str]:
    """Extract abstract from TEI document.
    
    The abstract in GROBID TEI is typically at /TEI/teiHeader/profileDesc/abstract
    """
    # Look for abstract in profileDesc
    abstract_elem = root.find(
        ".//tei:teiHeader/tei:profileDesc/tei:abstract",
        namespaces=NSMAP
    )
    if abstract_elem is not None:
        # Abstract may contain multiple <p> elements
        paragraphs = abstract_elem.findall("tei:p", namespaces=NSMAP)
        if paragraphs:
            texts = [_get_text(p) for p in paragraphs if _get_text(p)]
            if texts:
                return " ".join(texts)
        else:
            # Try div/p structure
            paragraphs = abstract_elem.findall(".//tei:p", namespaces=NSMAP)
            if paragraphs:
                texts = [_get_text(p) for p in paragraphs if _get_text(p)]
                if texts:
                    return " ".join(texts)
            else:
                # Fall back to all text content
                abstract_text = _get_text(abstract_elem)
                if abstract_text:
                    return abstract_text
    
    return None


def _extract_keywords(root: etree._Element) -> List[str]:
    """Extract keywords from TEI document.
    
    Keywords are typically in /TEI/teiHeader/profileDesc/textClass/keywords
    """
    keywords = []
    
    # Look for keywords in textClass
    for kw_container in root.findall(
        ".//tei:teiHeader/tei:profileDesc/tei:textClass/tei:keywords",
        namespaces=NSMAP
    ):
        # Keywords may be in <term> elements
        for term in kw_container.findall(".//tei:term", namespaces=NSMAP):
            kw = _get_text(term)
            if kw and kw not in keywords:
                keywords.append(kw)
        
        # Or directly as text content with commas/semicolons
        if not keywords:
            kw_text = _get_text(kw_container)
            if kw_text:
                # Split by common delimiters
                for kw in re.split(r'[,;]', kw_text):
                    kw = kw.strip()
                    if kw and kw not in keywords:
                        keywords.append(kw)
    
    return keywords


def _extract_doi(header: etree._Element) -> Optional[str]:
    """Extract DOI from TEI header if present."""
    # DOI may be in idno[@type='DOI']
    doi_elem = header.find(".//tei:idno[@type='DOI']", namespaces=NSMAP)
    if doi_elem is not None:
        doi = _get_text(doi_elem)
        if doi:
            return doi
    return None


def extract_tei_metadata(tei_xml: str) -> TEIMetadata:
    """Extract metadata from a GROBID TEI XML document.
    
    Parses the teiHeader section to extract:
    - Title
    - Authors (with ORCIDs and affiliations when available)
    - Abstract
    - Keywords
    - DOI
    
    Args:
        tei_xml: The complete TEI XML document as a string.
        
    Returns:
        TEIMetadata object containing extracted metadata.
    """
    try:
        root = etree.fromstring(tei_xml.encode("utf-8"))
    except (etree.XMLSyntaxError, ValueError):
        return TEIMetadata()
    
    header = root.find("tei:teiHeader", namespaces=NSMAP)
    if header is None:
        return TEIMetadata()
    
    return TEIMetadata(
        title=_extract_title(header),
        abstract=_extract_abstract(root),
        authors=_extract_authors(header),
        keywords=_extract_keywords(root),
        doi=_extract_doi(header),
    )
