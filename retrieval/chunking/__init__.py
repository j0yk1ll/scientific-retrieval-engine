"""Chunking utilities for transforming parsed documents into embeddings.

Example: chunk GROBID TEI XML and index for hybrid search
---------------------------------------------------------
```python
from retrieval.chunking import PaperChunkerService
from retrieval.hybrid import BM25Index, FaissVectorIndex, HybridRetriever, Chunk

tei_xml = "<TEI>...</TEI>"  # output from a GROBID server
chunker = PaperChunkerService(paper_id="demo-paper", tei_xml=tei_xml)
paper_chunks = chunker.chunk(max_tokens=400)

bm25 = BM25Index()

class StaticEmbedder:
    def embed(self, texts):
        return [[0.0] * 8 for _ in texts]

vector = FaissVectorIndex(StaticEmbedder())
retriever = HybridRetriever(bm25, vector)
retriever.index_chunks(Chunk.from_paper_chunk(chunk) for chunk in paper_chunks)
results = retriever.search("introduction to transformers")
```
"""

from .paper_chunker_service import (
    PaperChunk,
    PaperChunkerService,
    PaperDocument,
    PaperSection,
)

__all__ = ["PaperChunk", "PaperChunkerService", "PaperDocument", "PaperSection"]
