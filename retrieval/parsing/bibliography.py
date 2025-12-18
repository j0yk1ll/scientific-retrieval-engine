"""Utilities for extracting bibliography entries from GROBID TEI XML."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from lxml import etree

NSMAP = {"tei": "http://www.tei-c.org/ns/1.0"}


def _get_text(element: etree._Element | None) -> str:
    """Extract normalized text from an element."""
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _format_author(author_elem: etree._Element) -> str:
    """Format an author element as a name string."""
    persname = author_elem.find(".//tei:persName", namespaces=NSMAP)
    if persname is None:
        return _get_text(author_elem)
    
    forename = persname.find("tei:forename", namespaces=NSMAP)
    surname = persname.find("tei:surname", namespaces=NSMAP)
    
    parts = []
    if forename is not None:
        parts.append(_get_text(forename))
    if surname is not None:
        parts.append(_get_text(surname))
    
    return " ".join(parts) if parts else _get_text(persname)


def _format_authors(bib_elem: etree._Element) -> str:
    """Format all authors from a biblStruct element."""
    authors = []
    
    # Look for authors in analytic (article) then monogr (book/journal)
    for container in ["tei:analytic", "tei:monogr"]:
        for author in bib_elem.findall(f".//{container}/tei:author", namespaces=NSMAP):
            name = _format_author(author)
            if name and name not in authors:
                authors.append(name)
    
    if not authors:
        return ""
    elif len(authors) == 1:
        return authors[0]
    elif len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    else:
        return f"{authors[0]} et al."


def _format_title(bib_elem: etree._Element) -> str:
    """Extract the title from a biblStruct element."""
    # Try analytic title first (article title)
    title = bib_elem.find(".//tei:analytic/tei:title", namespaces=NSMAP)
    if title is not None and _get_text(title):
        return _get_text(title)
    
    # Fall back to monogr title (book/journal title)
    title = bib_elem.find(".//tei:monogr/tei:title", namespaces=NSMAP)
    return _get_text(title) if title is not None else ""


def _format_year(bib_elem: etree._Element) -> str:
    """Extract the publication year from a biblStruct element."""
    # Look for date in imprint
    date = bib_elem.find(".//tei:imprint/tei:date", namespaces=NSMAP)
    if date is not None:
        when = date.get("when", "")
        if when:
            # Extract year from YYYY-MM-DD or YYYY format
            match = re.match(r"(\d{4})", when)
            if match:
                return match.group(1)
        return _get_text(date)
    return ""


def _format_venue(bib_elem: etree._Element) -> str:
    """Extract venue (journal/conference) from a biblStruct element."""
    # Journal title
    journal = bib_elem.find(".//tei:monogr/tei:title[@level='j']", namespaces=NSMAP)
    if journal is not None and _get_text(journal):
        return _get_text(journal)
    
    # Conference/proceedings title
    meeting = bib_elem.find(".//tei:monogr/tei:meeting", namespaces=NSMAP)
    if meeting is not None and _get_text(meeting):
        return _get_text(meeting)
    
    # Book series or monograph title
    series = bib_elem.find(".//tei:monogr/tei:title[@level='m']", namespaces=NSMAP)
    if series is not None and _get_text(series):
        return _get_text(series)
    
    return ""


def format_bibliography_entry(bib_elem: etree._Element) -> str:
    """Format a single biblStruct element as a citation string.
    
    Returns a formatted string like:
    "Author et al. (2023). Title. Venue."
    """
    authors = _format_authors(bib_elem)
    title = _format_title(bib_elem)
    year = _format_year(bib_elem)
    venue = _format_venue(bib_elem)
    
    parts = []
    
    # Author (Year). Title. Venue.
    if authors:
        if year:
            parts.append(f"{authors} ({year}).")
        else:
            parts.append(f"{authors}.")
    elif year:
        parts.append(f"({year}).")
    
    if title:
        parts.append(f"{title}.")
    
    if venue:
        parts.append(venue + ".")
    
    return " ".join(parts) if parts else ""


def extract_bibliography_map(root: etree._Element) -> Dict[str, str]:
    """Extract a mapping from citation target IDs to formatted bibliography strings.
    
    Parses the <listBibl> section of a GROBID TEI document and creates a 
    dictionary mapping reference IDs (e.g., "b0", "b1") to their formatted
    citation strings.
    
    Args:
        root: The root element of the TEI XML document.
        
    Returns:
        A dictionary mapping reference IDs to formatted citation strings.
    """
    bib_map: Dict[str, str] = {}
    
    # Find the bibliography section
    list_bibl = root.find(".//tei:listBibl", namespaces=NSMAP)
    if list_bibl is None:
        return bib_map
    
    # Process each biblStruct element
    for bib in list_bibl.findall("tei:biblStruct", namespaces=NSMAP):
        bib_id = bib.get("{http://www.w3.org/XML/1998/namespace}id")
        if not bib_id:
            continue
        
        formatted = format_bibliography_entry(bib)
        if formatted:
            bib_map[bib_id] = formatted
    
    return bib_map


def extract_citations_from_element(
    element: etree._Element,
    bib_map: Dict[str, str],
) -> List[str]:
    """Extract resolved citation strings from a TEI element.
    
    Finds all <ref type="bibr"> elements within the given element and 
    resolves their targets to full bibliography strings using the provided map.
    
    Args:
        element: The TEI element to search for citations.
        bib_map: Mapping from citation IDs to formatted bibliography strings.
        
    Returns:
        A deduplicated list of citation strings in order of appearance.
    """
    seen: set[str] = set()
    citations: List[str] = []
    
    # Find all bibliography references
    for ref in element.iter("{http://www.tei-c.org/ns/1.0}ref"):
        ref_type = ref.get("type", "")
        if ref_type != "bibr":
            continue
        
        target = ref.get("target", "")
        if not target:
            continue
        
        # Remove the leading # from the target
        bib_id = target.lstrip("#")
        
        # Look up the bibliography entry
        citation = bib_map.get(bib_id, "")
        if citation and citation not in seen:
            seen.add(citation)
            citations.append(citation)
    
    return citations


def extract_citations_from_text_with_bib(
    text: str,
    bib_map: Dict[str, str],
) -> List[str]:
    """Extract resolved citation strings from plain text using numeric markers.
    
    Parses citation markers like [1], [2, 3], [4-6] from the text and resolves
    them to bibliography entries. This is a fallback for when the original
    TEI elements are not available.
    
    Args:
        text: The plain text containing citation markers.
        bib_map: Mapping from citation IDs (like "b0", "b1") to formatted strings.
        
    Returns:
        A deduplicated list of citation strings in order of appearance.
    """
    # Import here to avoid circular dependency
    from retrieval.parsing.citations import extract_citations
    
    markers = extract_citations(text)
    seen: set[str] = set()
    citations: List[str] = []
    
    for marker in markers:
        # Try common GROBID ID formats: b0, b1, b2...
        # The numeric marker typically corresponds to bN where N = marker - 1 or just marker
        for bib_id in [f"b{int(marker) - 1}", f"b{marker}"]:
            citation = bib_map.get(bib_id, "")
            if citation and citation not in seen:
                seen.add(citation)
                citations.append(citation)
                break
    
    return citations
