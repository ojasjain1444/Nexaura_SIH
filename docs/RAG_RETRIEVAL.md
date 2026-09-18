# Semantic Retrieval — Phase 4

Status: **implemented and verified**. This document describes what was actually built and tested, not a proposal. Everything below the line "IMPLEMENTED NOW" is real; anything under "FUTURE" is explicitly not built.

## IMPLEMENTED NOW

### Architecture

```
StandardDocument (Phase 3, status="completed")
        │
        ▼
   DocumentPage (Phase 3 — already extracted text)
        │
        ▼
   chunk_page_text()          app/rag/chunking.py
        │
        ▼
   DocumentChunk (no embedding yet)
        │
        ▼
   EmbeddingProvider.embed_texts()   app/rag/embeddings.py
        │
        ▼
   DocumentChunk.embedding_json (populated)
        │
        ▼
   VectorStore.similarity_search()   app/rag/vector_store.py
        │
        ▼
   RetrievalService.retrieve()       app/rag/retrieval.py
        │
        ▼
   POST /api/rag/retrieve  →  evidence chunks (NO LLM ANYWHERE IN THIS CHAIN)
```

Indexing (chunking + embedding) is a deliberately **separate operation** from Phase 3's ingestion pipeline (`app/ingestion/pipeline.py`) — see `app/rag/index_document.py`'s docstring. A document must reach `status="completed"` from Phase 3 before it can be indexed; indexing failures never touch or revert that Phase 3 state.

### Chunking strategy

Implemented in `app/rag/chunking.py`. Rules, in order:
1. **Never cross a page boundary** — every chunk belongs to exactly one page, so page-number provenance is always exact.
2. **Split on section headings first**, reusing the same `SECTION_HEADING_PATTERN` regex that Phase 3's feature extraction already uses — chunk sections and detected features agree by construction.
3. **Within a section, split on paragraph boundaries** (blank lines), then greedily pack paragraphs into chunks up to **800 characters**, carrying **100 characters** of trailing overlap into the next chunk when one closes.
4. **A paragraph longer than 800 characters is not split mid-paragraph** — it becomes its own oversized chunk. This is a deliberate simplicity trade-off for this baseline, not an oversight.

**Why 800/100:** chosen as a reasonable starting point for short, dense BIS-style clause text (2-4 clauses typically fit in ~800 characters) — not benchmarked against real BIS documents, because none were available during this phase (see `IMPLEMENTATION_ROADMAP.md` Phase 3/4). These are explicitly a baseline, not a claimed-optimal value.

**Determinism:** verified by a dedicated test — the same page text always produces the same chunk list, same order, every time. No randomness anywhere in the chunking path.

**Metadata preserved per chunk:** `document_id`, `document_page_id`, `page_number`, `section` (nullable), `chunk_index`, `text`.

### Embedding model

**Model: `intfloat/multilingual-e5-small`** via `sentence-transformers==6.0.1`.

Actually tested on this machine (not assumed):
- Dimension: **384** (confirmed by direct call to `model.get_sentence_embedding_dimension()`)
- Cold load (first download): ~67s. Warm load (cached weights): ~10.6s.
- Encoding 2 short texts: 0.73s on CPU.
- Cached model size on disk: ~470MB (within a 1.1GB huggingface cache directory that also includes torch's own files).
- Cross-lingual sanity check: a Hindi query ("पानी की गुणवत्ता मानक") against an English passage about water quality standards scored 0.88 cosine similarity — meaningfully high, demonstrating the model does encode cross-lingual semantic content. **This is one anecdotal check, not a rigorous multilingual benchmark.**

**Why this model:** it is the smallest model in the E5 family that is genuinely multilingual (XLM-RoBERTa base, ~100 languages), matching the project's future requirement to support Indian-language chat (per `docs/ARCHITECTURE.md`'s multilingual section). Larger alternatives (`multilingual-e5-base`, 278M params) were not installed — "do not blindly install a huge model" — since the small model's actual measured CPU performance above is already practical for this prototype's scale. English-only alternatives (e.g. `all-MiniLM-L6-v2`) were ruled out specifically because they don't meet the multilingual requirement.

No API key is required — the model runs entirely locally after the one-time download.

**Loading discipline:** the model is loaded exactly once per process via a class-level singleton guarded by a lock (`LocalEmbeddingProvider._model`), never per-request — verified by the measured load times above, which make per-request loading obviously impractical.

### Vector storage — LOCAL vs. PGVECTOR, explicitly distinguished

**What is actually implemented and tested: `LocalVectorStore`** (`app/rag/vector_store.py`). Embeddings are stored as JSON-encoded arrays in a SQLite `TEXT` column (`DocumentChunk.embedding_json`). Similarity search loads candidate rows via SQLAlchemy, then computes cosine similarity with NumPy, in Python, doing a full linear scan of every embedded chunk on every query. This is real, working, tested code — verified against real embeddings from the real model in `test_indexing.py` and `test_retrieval_evaluation.py`, and over live HTTP (see below).

**What is NOT implemented: PostgreSQL + pgvector.** This machine has neither PostgreSQL nor Docker installed (checked directly: `which psql` → not found, `which docker` → not found). No pgvector code was written, because it could not be honestly tested without a running PostgreSQL instance. The `VectorStore` protocol in `app/rag/vector_store.py` is written so a future `PgVectorStore` class can implement the same interface without touching `retrieval.py` or `index_document.py` — but until that class exists and is tested against a real running pgvector instance, it does not exist in this codebase.

**Scaling honesty:** `LocalVectorStore`'s linear scan is fine for the corpus sizes this prototype will ever hold (a handful of synthetic test documents, dozens of chunks). It would not scale to a real production BIS corpus of thousands of documents — that is exactly the gap pgvector (with a real ANN index) is meant to close, later.

**Model/dimension compatibility:** `DocumentChunk.embedding_model` and `.embedding_dimension` are stored per-row. `LocalVectorStore.similarity_search` filters to only chunks matching the query's embedding model before doing any similarity math, and raises `VectorStoreError` on a genuine dimension mismatch rather than silently truncating or padding vectors — verified by dedicated tests (`test_incompatible_model_chunks_are_excluded`, `test_dimension_mismatch_raises_error`).

### Retrieval API

`POST /api/rag/retrieve` (`app/api/routes/rag.py`). **This is retrieval only — it never calls an LLM and generates no answer text.**

Request:
```json
{ "query": "What is the scope of this standard?", "top_k": 5, "document_id": "optional-uuid" }
```

Response:
```json
{
  "results": [
    { "chunk_id": "...", "document_id": "...", "document_name": "test_text.pdf",
      "page_number": 1, "section": "1", "text": "...", "similarity_score": 0.84 }
  ]
}
```

**Filters actually implemented:** `document_id` (via `POST /api/rag/retrieve`) and, as of Phase 5, `standard_id` (via `RetrievalService.retrieve()`, used internally by chat — see `docs/CHAT_RAG.md`; not yet exposed as a parameter on `POST /api/rag/retrieve` itself). `standard_id` resolves through the real `StandardDocument.standard_id` FK to the matching document IDs, then filters vector search to those — a real, schema-backed filter, not a placeholder. `page`, `section`, and `language` filters remain **not implemented** — adding them now would mean fake, non-functional query parameters, which this project explicitly avoids.

**Validation:** `query` must be non-empty and ≤1000 characters; `top_k` must be 1–20. Both enforced by Pydantic validators, tested for both boundaries.

**Similarity metric:** cosine similarity, computed as `dot(a, b) / (|a| * |b|)` on normalized embeddings. Range **[-1, 1]**, though in practice observed values cluster higher (~0.7–0.9) due to a known characteristic of E5-family bi-encoders — see "Limitations" below. **Called `similarity_score`, never "confidence"** — it measures embedding-space proximity, not a calibrated probability of relevance.

**top_k behavior:** returns up to `top_k` results ranked by descending similarity. If fewer than `top_k` chunks exist in the filtered scope, returns however many exist. If zero chunks are indexed (empty database, or a `document_id` filter pointing at a processed-but-not-yet-indexed document), returns `{"results": []}` — verified live: uploading and processing a document without indexing it, then retrieving filtered to that document, returned an empty array, not a fabricated result.

### Indexing workflow

CLI: `python -m app.rag.index_document_cli <document_id>`. Requires the document's Phase 3 status to already be `"completed"`.

**Re-indexing safety:** `index_document()` deletes all of a document's existing chunks before recreating them (`ChunkRepository.delete_by_document`), so running it twice never produces duplicate or stale chunks — verified: running indexing twice on the same document produced 4 chunks both times, not 8.

### Live HTTP verification (actually performed, not simulated)

1. Uploaded `tests/fixtures/test_text.pdf` via `POST /api/documents/upload`.
2. Polled `GET /api/documents/{id}/status` until `"completed"`.
3. Ran `python -m app.rag.index_document_cli <id>` — reported "Chunks created: 4, Chunks embedded: 4".
4. Called `POST /api/rag/retrieve` with `{"query": "standard number references", "document_id": "<id>"}` — the "2 REFERENCES" chunk (the section literally about standard-number references) ranked #1 with score 0.898, ahead of the SCOPE (0.809) and REQUIREMENTS (0.798) chunks.
5. Confirmed `document_id`, `page_number` (1), and `section` fields on every result matched the real ingested content.
6. Confirmed an irrelevant filter (retrieval scoped to a processed-but-unindexed document) returned `{"results": []}`, not a fabricated match.

### Evaluation (real numbers, tiny corpus — read the caveat)

`tests/test_retrieval_evaluation.py` runs 3 hand-written queries against the single synthetic `test_text.pdf` fixture (the only realistic-content fixture available — `data/raw/` remains empty, no real BIS document exists in this repository). Actual measured result on this run:

```
Top-1 section match: 3/3
Top-3 section match: 3/3
```

**This is not a production accuracy claim.** A 3-query, 1-document, 4-chunk evaluation is far too small to generalize from. It exists as a development regression check (the test asserts ≥2/3 top-3 matches, so a genuine embedding/retrieval bug would fail it) — not as evidence of real-world retrieval quality on actual BIS standards.

### Security

Document text is never executed, never used to construct shell commands, and never treated as an instruction — the retrieval path only ever embeds it as plain text and returns it as plain text in a JSON field. `top_k` is capped at 20; query length is capped at 1000 characters; both enforced server-side, not just documented.

### Performance

- Embedding model loaded once per process (singleton), not per request — see above.
- `LocalVectorStore` does not cache identical-text embeddings across calls in this phase; the retrieval path always re-embeds the incoming query (a single short string, ~0.1-0.3s) — deemed acceptable at this scale, not optimized further to avoid premature complexity.
- No distributed infrastructure of any kind — this is a local SIH prototype, matching the assignment's own instruction not to over-engineer.

## Limitations (documented honestly, not hidden)

1. **No absolute relevance threshold.** Retrieval ranks and returns up to `top_k` chunks by similarity, but does not reject "genuinely irrelevant" results below some cutoff — because the E5 model family's cosine similarities for this small, high-dimensional space cluster in a narrow high band (empirically ~0.7–0.9 even for a deliberately unrelated query vs. an unrelated chunk, measured directly in development). Inventing a fixed threshold without a real evaluation set large enough to calibrate it would itself be a fabrication — exactly what this phase's instructions forbid. When the entire indexed corpus is small (as it necessarily is here, with only synthetic test documents), an "irrelevant" query still returns the corpus's closest chunks, just with visibly lower scores near the bottom of the observed range.
2. **Oversized paragraphs are not split.** A single paragraph over ~800 characters becomes one large chunk rather than being cut mid-sentence.
3. **`LocalVectorStore` does not scale** — linear scan, no ANN index. Fine for this prototype's corpus size; would need pgvector (or another real vector index) for a production-scale BIS corpus.
4. **No real BIS document has been tested.** Every number and behavior described above was measured against synthetic, clearly-labelled test fixtures. The same pipeline is expected to work unchanged on a real BIS PDF once one is provided, but that has not been verified because no such document exists in this repository.

## FUTURE (explicitly not implemented in this phase)

- PostgreSQL + pgvector `VectorStore` implementation.
- Cloud/API-based embedding provider (only `"local"` exists; `EMBEDDING_PROVIDER` other than `"local"` raises an error).
- `standard_id`, `page`, `section`, `language` retrieval filters.
- A calibrated relevance/confidence threshold, once a real evaluation set exists to calibrate it against.
- LLM-based answer generation, RAG chat integration, citations rendered in the Assistant UI, multilingual response generation, voice (Whisper/Piper) — all later phases per `docs/IMPLEMENTATION_ROADMAP.md`.
