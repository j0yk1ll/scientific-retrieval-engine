# scientific-retrieval-engine

A Retrieval Engine for Autonomous Deep Research

## Overview

A Python library providing a clean local knowledge retrieval system for tens of thousands of papers, using:

- **OpenAlex** for discovery metadata
- **Unpaywall** for full-text retrieval (primary)
- **Title-based preprint servers** (fallback; no ID-based lookups)
- **GROBID** for PDF → TEI extraction
- **Deterministic TEI chunking**
- **ChromaDB** as the vector index/search engine (no extra reranker)
- **Postgres** for metadata + chunks + provenance
- **Docker** for external dependencies/services (Postgres, GROBID)

## Requirements

- Python 3.11
- Docker & Docker Compose
- Linux (Ubuntu recommended)

## Quick Start

### 1. Start Docker Services

```bash
# Start Postgres and GROBID
make up

# Or manually:
docker compose up -d
```

### 2. Install Dependencies

```bash
# Install runtime + dev dependencies
make install-dev
```

### 3. Run Database Migrations

```bash
make migrate
```

### 4. Run Tests

```bash
# Run all tests
make test

# Run only E2E tests (requires Docker services)
make test-e2e
```

## Configuration

The engine is configured via environment variables (prefix `RETRIEVAL_`) or a `.env` file:

| Variable | Description | Example |
|----------|-------------|---------|
| `RETRIEVAL_DB_DSN` | PostgreSQL connection string | `postgresql://retrieval:retrieval@localhost:5432/retrieval` |
| `RETRIEVAL_DATA_DIR` | Directory for downloaded documents | `./data` |
| `RETRIEVAL_INDEX_DIR` | Directory for ChromaDB index data | `./index` |
| `RETRIEVAL_CHROMA_URL` | ChromaDB server URL (required) | `http://localhost:8000` |
| `RETRIEVAL_GROBID_URL` | GROBID service endpoint | `http://localhost:8070` |
| `RETRIEVAL_UNPAYWALL_EMAIL` | Contact email for Unpaywall API | `you@example.com` |
| `RETRIEVAL_REQUEST_TIMEOUT_S` | HTTP request timeout (seconds) | `30.0` |

## Usage

```python
from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine

# Configure the engine
config = RetrievalConfig(
    db_dsn="postgresql://retrieval:retrieval@localhost:5432/retrieval",
    data_dir="./data",
    index_dir="./index",
    chroma_url="http://localhost:8000",  # Connect to ChromaDB Docker container
    grobid_url="http://localhost:8070",
    unpaywall_email="you@example.com",
)

engine = RetrievalEngine(config)

# Ingest a paper by DOI
paper = engine.ingest_from_doi("10.1234/example.doi")

# Rebuild the ChromaDB index
engine.rebuild_index()

# Search for evidence
bundle = engine.evidence_bundle("machine learning methods", top_k=10)
for evidence_paper in bundle.papers:
    print(f"Paper: {evidence_paper.paper.title}")
    for chunk in evidence_paper.chunks:
        print(f"  - {chunk.content[:100]}...")
```

## Docker Services

The `docker-compose.yml` provides:

- **Postgres 16**: Metadata and chunk storage
  - Port: 5432
  - User: `retrieval`
  - Password: `retrieval`
  - Database: `retrieval`

- **ChromaDB**: Vector database for semantic search
  - Port: 8000
  - Persistent storage in Docker volume
  - Health check: `http://localhost:8000/api/v1/heartbeat`

- **GROBID 0.8.1**: PDF to TEI XML extraction
  - Port: 8070
  - Health check: `http://localhost:8070/api/isalive`

## Development

```bash
# Lint code
make lint

# Type check
make typecheck

# Clean generated files
make clean

# Stop Docker services
make down
```

## Project Structure

```
retrieval/
├── acquisition/     # PDF downloading, Unpaywall, preprint servers
├── discovery/       # OpenAlex client
├── index/           # ChromaDB indexing and search
├── parsing/         # GROBID client, TEI chunking
├── retrieval/       # Search result types and postprocessing
├── storage/         # Database models, DAO, migrations
├── config.py        # Configuration settings
├── engine.py        # Main RetrievalEngine class
└── exceptions.py    # Custom exceptions
```

## License

See LICENSE file for details.
