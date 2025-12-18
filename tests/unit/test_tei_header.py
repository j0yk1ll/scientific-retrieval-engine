"""Tests for TEI header metadata extraction."""

import pytest

from retrieval.parsing.tei_header import (
    TEIAuthor,
    TEIMetadata,
    extract_tei_metadata,
)


# Sample GROBID TEI XML with full metadata
SAMPLE_TEI_WITH_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:space="preserve">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Sample Title from titleStmt</title>
      </titleStmt>
      <sourceDesc>
        <biblStruct>
          <analytic>
            <title type="main">Deep Learning for Scientific Text Analysis</title>
            <author>
              <persName>
                <forename>Alice</forename>
                <surname>Smith</surname>
              </persName>
              <idno type="ORCID">0000-0001-2345-6789</idno>
              <affiliation>
                <orgName>University of Example</orgName>
              </affiliation>
            </author>
            <author>
              <persName>
                <forename>Bob</forename>
                <surname>Jones</surname>
              </persName>
              <affiliation>
                <orgName>Research Institute</orgName>
              </affiliation>
            </author>
          </analytic>
          <monogr>
            <idno type="DOI">10.1234/example.2023</idno>
          </monogr>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
    <profileDesc>
      <abstract>
        <p>This paper presents a novel approach to scientific text analysis using deep learning.</p>
        <p>We demonstrate significant improvements over baseline methods.</p>
      </abstract>
      <textClass>
        <keywords>
          <term>deep learning</term>
          <term>natural language processing</term>
          <term>scientific text</term>
        </keywords>
      </textClass>
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div type="section">
        <head>Introduction</head>
        <p>Sample body text.</p>
      </div>
    </body>
  </text>
</TEI>
"""


SAMPLE_TEI_MINIMAL = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <sourceDesc>
        <biblStruct>
          <analytic>
            <title>Minimal Document Title</title>
          </analytic>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <div><p>Content</p></div>
    </body>
  </text>
</TEI>
"""


SAMPLE_TEI_TITLESTMT_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Title from TitleStmt Only</title>
      </titleStmt>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <div><p>Content</p></div>
    </body>
  </text>
</TEI>
"""


class TestExtractTEIMetadata:
    """Test extract_tei_metadata function."""

    def test_extracts_title_from_analytic(self):
        """Title should be extracted from sourceDesc/biblStruct/analytic/title."""
        meta = extract_tei_metadata(SAMPLE_TEI_WITH_METADATA)
        assert meta.title == "Deep Learning for Scientific Text Analysis"

    def test_extracts_title_from_titlestmt_fallback(self):
        """If analytic title is missing, fall back to titleStmt/title."""
        meta = extract_tei_metadata(SAMPLE_TEI_TITLESTMT_ONLY)
        assert meta.title == "Title from TitleStmt Only"

    def test_extracts_abstract(self):
        """Abstract should be extracted and paragraphs joined."""
        meta = extract_tei_metadata(SAMPLE_TEI_WITH_METADATA)
        assert meta.abstract is not None
        assert "novel approach to scientific text analysis" in meta.abstract
        assert "significant improvements" in meta.abstract

    def test_extracts_authors(self):
        """Authors should be extracted with names."""
        meta = extract_tei_metadata(SAMPLE_TEI_WITH_METADATA)
        assert len(meta.authors) == 2
        assert meta.authors[0].name == "Alice Smith"
        assert meta.authors[1].name == "Bob Jones"

    def test_extracts_author_orcid(self):
        """ORCID should be extracted when present."""
        meta = extract_tei_metadata(SAMPLE_TEI_WITH_METADATA)
        assert meta.authors[0].orcid == "0000-0001-2345-6789"
        assert meta.authors[1].orcid is None

    def test_extracts_author_affiliations(self):
        """Affiliations should be extracted."""
        meta = extract_tei_metadata(SAMPLE_TEI_WITH_METADATA)
        assert "University of Example" in meta.authors[0].affiliations
        assert "Research Institute" in meta.authors[1].affiliations

    def test_extracts_keywords(self):
        """Keywords should be extracted from textClass/keywords."""
        meta = extract_tei_metadata(SAMPLE_TEI_WITH_METADATA)
        assert "deep learning" in meta.keywords
        assert "natural language processing" in meta.keywords
        assert "scientific text" in meta.keywords

    def test_extracts_doi(self):
        """DOI should be extracted when present."""
        meta = extract_tei_metadata(SAMPLE_TEI_WITH_METADATA)
        assert meta.doi == "10.1234/example.2023"

    def test_minimal_document(self):
        """Minimal document should extract available fields."""
        meta = extract_tei_metadata(SAMPLE_TEI_MINIMAL)
        assert meta.title == "Minimal Document Title"
        assert meta.abstract is None
        assert len(meta.authors) == 0
        assert len(meta.keywords) == 0
        assert meta.doi is None

    def test_invalid_xml_returns_empty_metadata(self):
        """Invalid XML should return empty metadata."""
        meta = extract_tei_metadata("not valid xml")
        assert meta.title is None
        assert meta.abstract is None
        assert len(meta.authors) == 0

    def test_empty_string_returns_empty_metadata(self):
        """Empty string should return empty metadata."""
        meta = extract_tei_metadata("")
        assert meta.title is None
        assert meta.abstract is None


class TestTEIAuthor:
    """Test TEIAuthor dataclass."""

    def test_author_with_all_fields(self):
        """Author should store all fields."""
        author = TEIAuthor(
            name="John Doe",
            orcid="0000-0001-2345-6789",
            affiliations=["Univ A", "Univ B"],
        )
        assert author.name == "John Doe"
        assert author.orcid == "0000-0001-2345-6789"
        assert len(author.affiliations) == 2

    def test_author_defaults(self):
        """Author should have sensible defaults."""
        author = TEIAuthor(name="Jane Doe")
        assert author.name == "Jane Doe"
        assert author.orcid is None
        assert author.affiliations == []


class TestTEIMetadata:
    """Test TEIMetadata dataclass."""

    def test_metadata_defaults(self):
        """Metadata should have sensible defaults."""
        meta = TEIMetadata()
        assert meta.title is None
        assert meta.abstract is None
        assert meta.authors == []
        assert meta.keywords == []
        assert meta.doi is None
