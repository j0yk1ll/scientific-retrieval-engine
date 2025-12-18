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

Each function leverages dedicated service clients (OpenAlex, Semantic Scholar, Unpaywall, and OpenCitations) and caches papers/evidence only for the active session. Re-running `search_papers` with the same query can return new results as upstream sources evolve.

### Supported inputs and scope

- Inputs must be either a DOI or a title. URL-based lookups and parsing are intentionally unsupported.
- The pipeline queries curated metadata services only; it does **not** scrape source servers directly.
- Preprint servers (e.g., arXiv) are out of scope and are not consulted by any workflow.

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
