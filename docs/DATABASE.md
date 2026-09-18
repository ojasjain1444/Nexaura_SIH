# Database — Phases 2–5

Status: **implemented and verified**. This document describes the actual schema and migration setup as built, not a proposal.

**Note on paths:** `backend/...` paths below are correct as-is. Any `src/...` reference (e.g. the mock data files) refers to `frontend/src/...` in the current repository layout.

## 1. Architecture

SQLite by default for local development (`backend/bis_sahayak.db`), with a schema designed to be PostgreSQL-compatible: no SQLite-only types are used, arrays are modeled as child tables rather than relying on a dialect-specific array column, and every model is plain SQLAlchemy 2.x declarative — the same code runs against either database. Switching to PostgreSQL later is a `DATABASE_URL` change plus adding `psycopg2-binary` to `requirements.txt`; it does not require touching any model.

**pgvector is explicitly NOT part of this phase.** No vector column, vector index, or embedding table exists yet — see `IMPLEMENTATION_ROADMAP.md` Phase 4 for when that's introduced.

## 2. Models

| Model | Purpose | Key fields |
|---|---|---|
| `Conversation` | A chat session | `id` (UUID str), `title`, `created_at`, `updated_at` (indexed — history sorts by this) |
| `Message` | One turn in a conversation | `id`, `conversation_id` (FK, indexed, cascade delete), `role` (`user`/`assistant`/`system`), `content`, `created_at` |
| `Standard` | An Indian Standard record | `id`, `code` (unique, indexed), `title` (indexed), `category` (indexed), `description`, `status`, `last_amended`, `sector`, `source_type` |
| `StandardRelatedCode` | One related-code string per row | `standard_id` (FK), `code` |
| `CertificationScheme` | A BIS certification scheme | `id`, `name` (unique, indexed), `type`, `summary`, `average_duration_days`, `fees`, `source_type` |
| `CertificationStep` | One ordered step in a scheme | `scheme_id` (FK, indexed), `order`, `title`, `description` |
| `SchemeEligibility` | One ordered eligibility requirement | `scheme_id` (FK, indexed), `order`, `requirement` |
| `Lab` | A testing laboratory | `id`, `name` (indexed), `city` (indexed), `state`, `contact`, `source_type` |
| `LabAccreditation` | One accreditation string per row | `lab_id` (FK, indexed), `accreditation` |
| `LabTestCategory` | One test-category string per row | `lab_id` (FK, indexed), `category` (indexed) |
| `UserPreference` | Persisted Settings-page preferences | `user_key` (unique, indexed — fixed `"local-default-user"` until auth exists), `language` |
| `StandardDocument` (Phase 3) | An uploaded/ingested source PDF | `id`, `standard_id` (nullable FK — a document can exist before/without being linked to a catalogued Standard), `file_hash` (unique, indexed — duplicate detection), `mime_type`, `size_bytes`, `storage_path`, `page_count`, `status` (indexed), `error_message`, `extracted_standard_number`/`extracted_title`/`extracted_edition` (each independently nullable), `source_type` (default `"unverified"`) |
| `DocumentPage` (Phase 3) | Page-level extracted text | `document_id` (FK, indexed), `page_number` (unique with document_id), `text`, `extraction_method` (`"native"`/`"ocr"`), `ocr_confidence` (null for native) |
| `DocumentFeature` (Phase 3) | One structured, source-located fact extracted from a document | `document_id` (FK, indexed), `feature_type` (indexed — e.g. `"standard_number"`, `"section_heading"`), `value`, `page_number`, `section` (nullable) |
| `DocumentChunk` (Phase 4) | A retrieval-sized text slice with its embedding stored on the same row | `document_id` (FK, indexed), `document_page_id` (FK, indexed — note: integer, not UUID, matching `DocumentPage.id`), `page_number`, `chunk_index` (unique with document_id), `text`, `section` (nullable), `embedding_json` (nullable — null until indexed), `embedding_model` (indexed), `embedding_dimension` |
| `MessageCitation` (Phase 5) | Persisted source-attribution for an assistant Message, copied from real retrieval results at generation time | `message_id` (FK, indexed), `document_id`, `document_name`, `page_number`, `section` (nullable), `chunk_id`, `similarity_score` — `document_id`/`chunk_id` are plain strings, not FKs (see relationships below for why) |

## 3. Why child tables instead of arrays/JSON

`IndianStandard.relatedCodes`, `CertificationScheme.eligibility`/`.steps`, and `TestingLab.accreditations`/`.testCategories` are all list fields in the frontend's TypeScript types. Rather than a Postgres array column (not portable to SQLite) or a JSON blob (not queryable/indexable), each is a separate child table with a foreign key back to its parent. `CertificationStep` and `SchemeEligibility` additionally carry an explicit `order` column so their sequence is a real, sortable database fact rather than relying on array/JSON ordering semantics.

## 4. Relationships

```
Conversation 1──* Message           (cascade delete: deleting a conversation deletes its messages)
Standard 1──* StandardRelatedCode   (cascade delete)
CertificationScheme 1──* CertificationStep       (cascade delete)
CertificationScheme 1──* SchemeEligibility       (cascade delete)
Lab 1──* LabAccreditation           (cascade delete)
Lab 1──* LabTestCategory            (cascade delete)

Standard 1──* StandardDocument      (SET NULL on delete — a document
                                      outlives the catalogue row it's
                                      linked to; standard_id is nullable)
StandardDocument 1──* DocumentPage    (cascade delete)
StandardDocument 1──* DocumentFeature (cascade delete)
StandardDocument 1──* DocumentChunk   (cascade delete)
DocumentPage 1──* DocumentChunk       (cascade delete — a chunk always
                                        belongs to exactly one page; see
                                        docs/RAG_RETRIEVAL.md's chunking
                                        strategy, which never crosses a
                                        page boundary)

Message 1──* MessageCitation           (cascade delete — citations only
                                         make sense attached to the
                                         message that generated them)
```

**Design decision — citations are NOT foreign-keyed to StandardDocument/DocumentChunk.** `MessageCitation.document_id` and `.chunk_id` are plain string columns, not FKs. A citation is a historical record of "what evidence was used when this message was generated" — if a document is later deleted or re-indexed (re-indexing deletes and recreates all of a document's chunks, per `docs/RAG_RETRIEVAL.md`), the citation should remain a truthful record of the past, not silently break or disappear because the live data changed underneath it.

**Design decision — embedding storage:** `DocumentChunk.embedding_json` stores the vector directly on the chunk row rather than in a separate `Embedding` table. A chunk has exactly one active embedding at a time in this phase; there is no current requirement to store multiple simultaneous embeddings per chunk (e.g. comparing two providers side by side). Co-locating `embedding_model`/`embedding_dimension` with the vector they describe makes the model-compatibility check (see `docs/RAG_RETRIEVAL.md`) a single-row read rather than a join. If a future phase needs multiple embeddings per chunk, that is the point to introduce a separate `Embedding` table — not before.

`Standard`, `Lab`, and `CertificationScheme` are independent reference entities — no foreign keys between them, matching how the current frontend/mock data treats them (a scheme's eligibility text mentions standards by free-text description, not by a queryable relationship; introducing that FK would be speculative, not something today's data or UI needs).

`StandardDocument.standard_id` is nullable and uses `ON DELETE SET NULL` rather than cascade: a document's extracted pages/features remain valid and queryable even if the catalogue `Standard` row it was linked to is later deleted — the document doesn't disappear just because a reference-data row does.

No `User` model exists. `Conversation` and `UserPreference` are not tied to a `user_id` foreign key — there is no authentication yet, and adding a nullable FK to a table that doesn't exist would be premature. `UserPreference` instead has a fixed `user_key = "local-default-user"` as a placeholder identity until Phase 11 (auth) exists.

## 5. Indexes — why each one exists

- `conversations.updated_at` — `HistoryPage` lists conversations ordered by recency; every history-list request sorts by this column.
- `messages.conversation_id` — every message read/write is scoped to one conversation; this is the join column for loading a transcript.
- `standards.code` (unique) — the primary human-facing lookup key (e.g. "IS 14625"); uniqueness prevents two rows claiming the same real-world standard.
- `standards.title`, `standards.category` — `StandardsExplorerPage` filters/searches by both.
- `certification_schemes.name` (unique) — schemes are displayed and looked up by name.
- `labs.name`, `labs.city` — `LabDirectoryPage` searches by both.
- `lab_test_categories.category`, `certification_steps.scheme_id`, `scheme_eligibility_items.scheme_id`, `standard_related_codes.standard_id`, `lab_accreditations.lab_id`, `lab_test_categories.lab_id` — all FK columns used to join a child table back to its parent; indexed because every parent-detail fetch does this join.
- `standard_documents.file_hash` (unique) — the actual duplicate-detection mechanism: every upload looks up by hash before inserting.
- `standard_documents.status` — `GET /api/documents/{id}/status` and any future "list documents still processing" query filter on this.
- `standard_documents.standard_id`, `document_pages.document_id`, `document_features.document_id` — FK join columns, same rationale as above.
- `document_features.feature_type` — queries like "all standard_number features across documents" filter on this.
- `document_chunks.document_id`, `document_chunks.document_page_id` — FK join columns, same rationale as above.
- `document_chunks.embedding_model` — `LocalVectorStore.similarity_search` filters to only chunks matching the query's embedding model before doing any similarity math; this is the actual mechanism behind the model-compatibility guard described in `docs/RAG_RETRIEVAL.md`.
- `message_citations.message_id` — every citation is loaded scoped to one message (rendering a chat response, or loading a conversation transcript from history).

No index was added speculatively — each one above is exercised by an actual current query in the service/repository layer.

## 6. Migrations

**Alembic**, not `Base.metadata.create_all()`, is the mechanism for real (dev/production) schema changes. `create_all()` is used only inside the test suite (`tests/conftest.py`), against a fresh temporary SQLite file per test — never against `bis_sahayak.db`. This distinction matters: `create_all()` has no concept of incremental change or rollback, which is fine for a throwaway test database but not for a database you intend to evolve over time.

Migration files live in `backend/app/db/migrations/versions/`. The Alembic environment (`app/db/migrations/env.py`) reads `DATABASE_URL` from the app's own `Settings` object rather than duplicating it in `alembic.ini`, so there is exactly one source of truth for which database migrations run against.

Verified commands (all run against this repository):
```bash
cd backend && source .venv/bin/activate

alembic revision --autogenerate -m "initial schema"                       # 1770f4814979 — 10 tables (Phase 2)
alembic upgrade head
alembic downgrade base                                  # verified: drops all tables, leaves only alembic_version
alembic upgrade head                                    # re-applies cleanly

alembic revision --autogenerate -m "phase 3 document ingestion tables"    # 440d97c5a48f — adds 3 tables
alembic upgrade head
alembic downgrade -1                                    # verified: drops only the 3 Phase 3 tables, Phase 2 tables remain
alembic upgrade head                                    # re-applies cleanly

alembic revision --autogenerate -m "phase 4 document chunks and embeddings"  # 0db4a559c3a4 — adds 1 table
alembic upgrade head
alembic downgrade -1                                    # verified: drops only document_chunks; Phase 2/3 tables remain
alembic upgrade head                                    # re-applies cleanly

alembic revision --autogenerate -m "phase 5 message citations"  # 0b55be269283 — adds 1 table
alembic upgrade head
alembic downgrade -1                                    # verified: drops only message_citations; all other tables remain
alembic upgrade head                                    # re-applies cleanly
```

Current revision: `0b55be269283` ("phase 5 message citations"), on top of `0db4a559c3a4` (Phase 4), `440d97c5a48f` (Phase 3), and `1770f4814979` (Phase 2). Future schema changes are new `alembic revision --autogenerate` calls on top of this chain.

## 7. Seed data

`python -m app.db.seed` inserts the same prototype data already used by the frontend's mock layer (`src/data/mockStandards.ts`, `mockSchemes.ts`, `mockLabs.ts`), hand-ported value-for-value into `backend/app/db/seed.py` — nothing was invented. Every seeded row is written with `source_type = "demo"`.

**This is explicitly not verified official BIS information.** It is the same placeholder data the frontend prototype has always shown, now persisted in a real database instead of a browser-side array. If a future phase imports real, verified BIS standards, those rows should use a different `source_type` value (e.g. `"verified_bis"`) — the seed script must never be the source of that value.

Idempotent: re-running matches existing rows by their natural key (`Standard.code`, `CertificationScheme.name`, `Lab.name`) and skips them. Verified by running the command twice — first run created 8/4/6 rows, second run created 0/0/0.

## 8. Development database

Location: `backend/bis_sahayak.db` (SQLite), gitignored. Delete the file and re-run `alembic upgrade head` + `python -m app.db.seed` to reset to a clean, seeded state.

## 8a. Document ingestion pipeline (Phase 3)

Pipeline: validation → registration (`StandardDocument` row, `status="uploaded"`) → text extraction (per page: native PDF text if available, else render-to-image + Tesseract OCR) → `DocumentPage` rows written → conservative regex-based metadata extraction (standard number, title, edition — from the first page only, BIS cover-page convention) → regex-based feature extraction (`DocumentFeature` rows: `standard_number` mentions anywhere in the body, `section_heading` clause headings) → `status="completed"`. Any stage failure sets `status="failed"` with a real `error_message` — no stage is skipped or faked to make a document appear to have finished.

**OCR:** Tesseract 5.5.3 (`brew install tesseract`), accessed only through the `OCRProvider` protocol in `app/ocr/provider.py` — the pipeline never imports `pytesseract` directly, so a future cloud OCR provider is a new class implementing that same protocol, not a pipeline rewrite. Per-page native-vs-OCR is decided independently (a page is OCR'd only if its native text is under 10 characters), verified with a mixed-content test fixture where page 1 used native extraction and page 2 used OCR in the same document.

**Metadata/feature extraction:** pure regex pattern matching against known BIS conventions (e.g. `IS 14625`, `IS/ISO 2859-1`, "First Revision"). No LLM, no fuzzy matching, no confidence scoring beyond OCR's own per-character confidence. A field that doesn't match stays `null` — verified by a dedicated test asserting no field is guessed for a document with no recognizable metadata.

**Storage:** original files are written to `{STORAGE_PATH}/processed/{document_id}.pdf` (named by UUID, not original filename, to avoid collisions); `StandardDocument.storage_path` records the location. `STORAGE_PATH` defaults to `./data` (relative to wherever the backend process runs), giving `backend/data/processed/` in normal local development.

**Real BIS data status:** `backend/data/raw/` exists but is empty — no real BIS PDF has been provided to this project. Everything tested in Phase 3 used synthetic fixtures from `backend/tests/fixtures/`, each containing the literal disclaimer text "SYNTHETIC TEST DOCUMENT -- NOT AN OFFICIAL BIS STANDARD". `StandardDocument.source_type` defaults to `"unverified"` for exactly this reason.

## 9. Future PostgreSQL migration

When actually switching (not scheduled in this phase):
1. `pip install psycopg2-binary` and add it to `requirements.txt`.
2. Set `DATABASE_URL=postgresql://user:password@localhost:5432/bis_sahayak` in `.env`.
3. Run `alembic upgrade head` against the new database — the same migration file works unchanged, since no SQLite-specific or Postgres-specific types were used.
4. No model or repository code changes are required.

## 10. pgvector — status

`DocumentChunk` was added in Phase 4 (see §2 above) with its embedding stored as JSON in a SQLite `TEXT` column, not a `pgvector` `Vector` column — this machine has no PostgreSQL and no Docker installed, so pgvector could not be honestly implemented and tested here. See `docs/RAG_RETRIEVAL.md` for the full explanation, the `VectorStore` abstraction that makes a future `PgVectorStore` addable without touching retrieval code, and exactly what was/wasn't tested.
