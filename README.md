# scientific-retrieval-engine

A Retrieval Engine for Autonomous Deep Research

## Overview

A lightweight Python library providing session-scoped paper discovery and citation lookups using trusted metadata services:

- **OpenAlex** and **Semantic Scholar** for discovery metadata
- **Unpaywall** (optional) for locating full-text sources
- **OpenCitations** for citation lookups

All results are stored **only in memory for the current Python session**. There is no filesystem or database persistence; when the session ends or you call the clear helper, the internal index is emptied.

## High-level API

The package exposes a simplified, function-only interface:

- `search_papers(query, k=5, min_year=None, max_year=None)`
- `search_paper_by_doi(doi)`
- `search_paper_by_title(title)`
- `gather_evidence(query)`
- `search_citations(paper_id)`
- `clear_papers_and_evidence()`

Each function leverages dedicated service clients (OpenAlex, Semantic Scholar, Unpaywall, and OpenCitations) and stores papers/evidence only for the active session. Re-running `search_papers` with the same query can return new results as upstream sources evolve.

### Supported inputs and scope

- Inputs must be either a DOI or a title. URL-based lookups, arbitrary URLs, and other identifiers (e.g., arXiv, ISBN, PubMed) are intentionally unsupported.
- The pipeline queries curated metadata services only; it does **not** scrape source servers directly.
- Preprint servers (e.g., arXiv) are out of scope and are not consulted by any workflow.

### DOI lookups

DOI inputs are resolved across Crossref, DataCite, OpenAlex, and Semantic Scholar.
Results are merged to prefer canonical identifiers while preserving the originating
source on each :class:`retrieval.models.Paper` instance via ``paper.source`` and
``paper.primary_source``.

```python
from retrieval import search_paper_by_doi

papers = search_paper_by_doi("10.5555/example.doi")
for paper in papers:
    print(paper.title, paper.doi, paper.source)
```

### Title → DOI resolution

Title searches first query OpenAlex and Semantic Scholar. When results are missing
DOIs, the pipeline attempts to resolve them through Crossref and DataCite using
token similarity and (when available) overlapping author names.

```python
from retrieval import search_paper_by_title

papers = search_paper_by_title("Attention is all you need")
print(papers[0].doi)  # May be upgraded via Crossref/DataCite
```

### GROBID ingestion + hybrid search

GROBID TEI output can be chunked and indexed for lexical + vector retrieval:

```python
from retrieval.services import PaperChunkerService
from retrieval.hybrid_search import BM25Index, FaissVectorIndex, HybridRetriever, Chunk

tei_xml = "<TEI>...</TEI>"  # GROBID response
chunks = PaperChunkerService("demo-paper", tei_xml).chunk(max_tokens=400)

bm25 = BM25Index()

class StaticEmbedder:
    def embed(self, texts):
        return [[0.0] * 8 for _ in texts]

vector = FaissVectorIndex(StaticEmbedder())
retriever = HybridRetriever(bm25, vector)
retriever.index_chunks(Chunk.from_paper_chunk(chunk) for chunk in chunks)
results = retriever.search("introduction")
```

### Hybrid retrieval example

Combine lexical and vector search across any chunk collection:

```python
from retrieval.hybrid_search import BM25Index, FaissVectorIndex, HybridRetriever, Chunk

chunks = [
    Chunk(text="Transformer models excel at sequence tasks"),
    Chunk(text="Graph neural networks capture relational structure"),
]

class StaticEmbedder:
    def embed(self, texts):
        return [[0.1, 0.2] for _ in texts]

bm25 = BM25Index()
vector = FaissVectorIndex(StaticEmbedder())
retriever = HybridRetriever(bm25, vector)
retriever.index_chunks(chunks)

for hit in retriever.search("sequence modeling"):
    print(hit.chunk.text, hit.score)
```

### Unpaywall configuration example

Unpaywall is opt-in and requires a contact email. Enable it via settings (or environment variables loaded with ``load_dotenv_from_root``):

```python
from retrieval.api import RetrievalClient
from retrieval.settings import RetrievalSettings

settings = RetrievalSettings(enable_unpaywall=True, unpaywall_email="you@example.com")
client = RetrievalClient(settings=settings)

# Unpaywall will be used automatically during DOI lookups to attach open-access links
papers = client.search_paper_by_doi("10.5555/example.doi")
```

## Requirements

- Python 3.11

## Quick Start

### Install Dependencies

```bash
# Install runtime
test -x "$(command -v uv)" || pip install uv
make install
```

### Usage

```python
from retrieval import (
    search_papers,
    search_paper_by_doi,
    search_paper_by_title,
    gather_evidence,
    search_citations,
    clear_papers_and_evidence,
)

# Search by free-text query
papers = search_papers("graph neural networks", k=5)

# Search explicitly by DOI or title
doi_results = search_paper_by_doi("10.5555/example.doi")
title_results = search_paper_by_title("Attention is all you need")

# Collect evidence for a question
collected = gather_evidence("applications of transformers in biology")

# Fetch citations for a specific paper identifier (e.g., DOI)
citations = search_citations("10.5555/example.doi")

# Clear all in-memory papers and evidence for this session
clear_papers_and_evidence()
```

The internal index is automatically discarded when the Python process exits, ensuring session-only storage.

## Development

```bash
# Lint code
make lint

# Run tests
make test

# Type check
make typecheck
```

## License

See LICENSE file for details.
