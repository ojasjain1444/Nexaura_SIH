# BIS Sahayak — Implementation Roadmap

Status: Phases 1–5 are **implemented and verified**. Phase 4 covered retrieval only (chunking/embedding/vector search); Phase 5 adds real LLM-backed generation, grounding, and citations on top of it — with a mock LLM provider, since no real LLM API key exists in this environment (see `docs/CHAT_RAG.md`). Phases 6–12 below have not been implemented yet. Each phase is written to be built and verified on its own — do not start a phase until the one before it is actually done, tested, and reported on. See `ARCHITECTURE.md` for the full design this roadmap implements incrementally.

Each phase lists: objective, files affected, dependencies, APIs touched, tests, and acceptance criteria. A phase is not "done" until its acceptance criteria are demonstrated with real command output, not asserted.

**Note on paths:** `backend/...` paths are correct as-is. Any bare `src/...` reference below (from before the repository was split into `frontend/`/`backend/` top-level directories) refers to `frontend/src/...` in the current layout.

---

## Phase 1 — Backend foundation — ✅ IMPLEMENTED

**Objective:** A minimal, runnable FastAPI app with health check, config, DB scaffold, and CORS — no business logic yet.

**Files affected (as actually created):** `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/core/{__init__.py,config.py,errors.py}`, `backend/app/db/{__init__.py,base.py,session.py}`, `backend/app/api/{__init__.py,routes/__init__.py,routes/health.py}`, `backend/app/schemas/{__init__.py,health.py}`, `backend/app/services/{__init__.py,health_service.py}`, `backend/requirements.txt`, `backend/.env.example`, `backend/tests/{__init__.py,test_health.py,test_db_session.py}`. Also: `.env.example` (frontend), `.gitignore` (Python entries added), `src/services/api.ts` (base URL wired + `checkBackendHealth()` added; all other functions unchanged/still mocked), `docs/LOCAL_DEVELOPMENT.md` (new).

Deliberately **not** created in Phase 1 (per explicit scope limit): `models/`, `repositories/`, `rag/`, `ingestion/`, `ocr/`, `voice/`, `multilingual/` — these have no real content until the phase that needs them.

**Dependencies:** none (first backend code).

**APIs:** `GET /api/health` — implemented and verified over real HTTP.

**Tests:** 7 tests, all passing (`test_health.py`: 200 response, response shape, correct service name, no secret leakage; `test_db_session.py`: engine configured, session creates/executes/closes, `get_db()` dependency works). No fake/placeholder-asserting tests were added.

**Verified NOT required for startup:** LLM/embedding/OCR/STT/TTS credentials, and no `.env` file at all — confirmed by running the server with zero configuration present.

**Acceptance criteria:** `uvicorn app.main:app` starts locally; `curl http://localhost:8000/api/health` returns `{"status": "ok", ...}`; `pytest` passes; frontend `npm run build` and `tsc` still pass unchanged.

---

## Phase 2 — Database — ✅ IMPLEMENTED

**Objective:** Real persistence for the entities that already have a frontend consumer: `Conversation`, `Message`, `Standard`, `CertificationScheme`, `CertificationStep`, `Lab`, `UserPreference`. Seed with the existing mock data, clearly labeled as prototype data, not verified BIS fact.

Note: Phase 1 intentionally built only the database *plumbing* (engine, session factory, declarative base) with zero models and zero tables — confirmed empty (`sqlite_master` had 0 rows) after Phase 1's tests ran. Phase 2 is where models, migrations, and repositories were actually created.

**Files affected (as actually created/modified):**
- Models: `app/models/{__init__,conversation,message,standard,certification_scheme,lab,user_preference}.py`
- Repositories: `app/repositories/{__init__,conversation_repository,message_repository,standard_repository,lab_repository,certification_repository,user_preference_repository}.py`
- Schemas: `app/schemas/{standard,certification,lab,chat,preferences}.py`
- Services: `app/services/{standards_service,labs_service,certification_service,history_service,chat_service,preferences_service,demo_responder}.py`
- API routes: `app/api/routes/{standards,labs,certification,history,chat,preferences}.py`, `app/main.py` (routers registered)
- Migrations: `alembic.ini`, `app/db/migrations/{env.py,script.py.mako}`, `app/db/migrations/versions/1770f4814979_initial_schema.py`
- Seed: `app/db/seed.py`
- Tests: `tests/conftest.py`, `tests/test_migrations.py`, `tests/test_chat_and_history.py`, `tests/test_standards.py`, `tests/test_labs.py`, `tests/test_certification.py`, `tests/test_preferences.py`, `tests/test_seed.py`
- `requirements.txt` (added `alembic`)
- Frontend: `src/services/api.ts` (all mock-resolving functions replaced with real `fetch()` calls, `getHistory`/`getHistoryById`/`deleteHistoryItem`/`getPreferences`/`updatePreferences` added), `src/hooks/useChat.ts` (tracks `conversationId`), `src/hooks/useLanguage.ts` (syncs with backend), `src/pages/HistoryPage.tsx` (fetches from backend instead of importing `mockHistory` directly)
- Docs: `docs/DATABASE.md` (new), this file, `docs/LOCAL_DEVELOPMENT.md` updated

**Dependencies:** Phase 1.

**APIs implemented and tested:** `GET /api/standards`, `GET /api/standards/{id}`, `GET /api/labs`, `GET /api/certification`, `GET /api/certification/{id}`, `POST /api/chat`, `GET /api/history`, `GET /api/history/{id}`, `DELETE /api/history/{id}`, `GET /api/preferences`, `PUT /api/preferences`.

Not implemented (was in the original proposal, decided against): `POST /api/conversations` as a standalone endpoint — conversation creation is implicit in the first `POST /api/chat` call without a `conversationId`, which matched the actual frontend flow better than a separate creation step. `POST /api/standards/search` (semantic search) — deferred to Phase 8, since it needs embeddings that don't exist yet.

**Tests:** 34 total (up from 7 in Phase 1), all passing — see `LOCAL_DEVELOPMENT.md` §8 for the full list of what's covered. Includes an actual server-restart persistence test (not just an in-memory assertion) — see the Phase 2 completion report for details.

**Acceptance criteria — met:** all endpoints return real DB-backed data matching the seeded mock content; `src/services/api.ts` updated; `StandardsExplorerPage`, `LabDirectoryPage`, `CertificationGuidePage` work unmodified against the real backend (only their data source changed); `HistoryPage` was modified (not "unmodified" as originally drafted) because it previously imported `mockHistory` directly, bypassing `services/api.ts` entirely — fixing that inconsistency was itself part of this phase's stated scope; empty-DB states render the existing `EmptyState`/`ErrorState`/`Spinner` components, verified by Playwright against a freshly seeded (non-empty) database and by automated tests against an empty isolated test database.

---

## Phase 3 — BIS document ingestion + OCR — ✅ IMPLEMENTED

**Objective:** Take a file, extract text (native or OCR, decided independently per page), extract conservative metadata/features, store it as a `StandardDocument` with `DocumentPage`/`DocumentFeature` rows — no chunking, no embeddings.

**Real BIS source material:** none was available in this repository (`backend/data/raw/` was empty at the start of this phase, and remains empty — no real BIS PDF has been provided). All testing was performed against synthetic, clearly-labelled test fixtures generated by `backend/tests/fixtures/generate_test_pdfs.py`, each containing the literal text "SYNTHETIC TEST DOCUMENT -- NOT AN OFFICIAL BIS STANDARD". A real BIS PDF can be dropped into `backend/data/raw/` and run through the same pipeline (`python -m app.ingestion.ingest data/raw/<file>.pdf`) at any time — nothing about the pipeline is test-fixture-specific.

**Files affected (as actually created):**
- Models: `app/models/{standard_document,document_page,document_feature}.py`
- OCR: `app/ocr/{provider,tesseract_provider}.py` (Protocol-based interface + Tesseract implementation — no other provider hard-coded)
- Ingestion: `app/ingestion/{validation,extraction,metadata_extraction,feature_extraction,storage,pipeline,ingest}.py`
- Repository: `app/repositories/document_repository.py`
- Service/schema/API: `app/services/document_service.py`, `app/schemas/document.py`, `app/api/routes/documents.py`
- Migration: `app/db/migrations/versions/440d97c5a48f_phase_3_document_ingestion_tables.py`
- Tests: `tests/test_ingestion.py`, `tests/test_ingestion_edge_cases.py`, `tests/test_ocr_failure.py`, `tests/fixtures/generate_test_pdfs.py` + generated fixture PDFs
- `requirements.txt` (added `pymupdf`, `pytesseract`, `Pillow`, `python-multipart`) — plus the `tesseract` OS binary via `brew install tesseract` (not a pip package)
- `.gitignore` (added rules for `backend/data/{raw,processed}/*`)

Not created: `DocumentProcessingJob` as a separate table (the roadmap's original proposal) — the processing status/error fields live directly on `StandardDocument` instead, since a document has exactly one in-flight processing attempt at a time in this phase; a separate job-history table would be justified once retries/reprocessing exist, not before.

**Dependencies:** Phase 2 (`Standard` table exists; `StandardDocument.standard_id` is a nullable FK to it).

**APIs implemented and tested (live HTTP + automated):** `POST /api/documents/upload` (201, background-processed), `GET /api/documents/{id}`, `GET /api/documents/{id}/status`, `GET /api/documents/{id}/pages`, `GET /api/documents/{id}/features`.

**Tests:** 24 new tests (58 total in the backend suite) covering: valid text PDF, valid scanned PDF (real Tesseract OCR, not mocked), mixed PDF (page-by-page independent native/OCR decision, verified), invalid file, empty-page PDF, OCR provider failure, duplicate file hash, 50-page large document, document with no extractable metadata, and all 404/422/409 API error paths. A real bug was caught and fixed during this phase: the upload endpoint's background task originally used a hardcoded `SessionLocal`, which silently bypassed FastAPI's test dependency override — background-processed documents in tests were invisible to the test's own database. Fixed by threading the active `get_db` override through to the background task.

**Acceptance criteria:** CLI (`python -m app.ingestion.ingest tests/fixtures/test_text.pdf`) processes a file end-to-end and reports genuine status; no fabricated BIS document was ever created or presented as official — `source_type` defaults to `"unverified"` and the pipeline never sets `"verified_bis"` itself; page-level OCR-vs-native decisions verified independently correct via a mixed-content fixture; metadata/feature fields are null (not guessed) when unrecognized, verified by a dedicated test.

---

## Phase 4 — Embeddings + Vector Search Foundation — ✅ IMPLEMENTED

**Scope correction from the original plan:** the original Phase 4 objective ("...serve grounded, cited answers") described both retrieval AND generation. Those were deliberately split: this phase implements retrieval only (chunking, embedding, vector search, evidence chunks). LLM-based answer generation, grounded conversational responses, and citations rendered in chat are **not** part of what was built here — they remain future work (folded into Phase 6, chat integration, or a dedicated generation phase).

**Objective (as actually scoped):** Chunk processed (Phase 3) documents, embed them with a local multilingual model, store vectors, and serve semantically relevant evidence chunks via API — no LLM anywhere in this chain.

**Files affected (as actually created):**
- Model: `app/models/document_chunk.py` (embedding stored directly on the chunk row — see `docs/DATABASE.md` §4 for why no separate `Embedding` table was created)
- RAG package: `app/rag/{__init__,chunking,embeddings,vector_store,index_document,index_document_cli,retrieval}.py`
- Repository: `app/repositories/chunk_repository.py`
- Schema/API: `app/schemas/retrieval.py`, `app/api/routes/rag.py`
- Migration: `app/db/migrations/versions/0db4a559c3a4_phase_4_document_chunks_and_embeddings.py`
- Tests: `tests/test_chunking.py`, `tests/test_embeddings.py`, `tests/test_vector_store.py`, `tests/test_indexing.py`, `tests/test_retrieval.py`, `tests/test_retrieval_evaluation.py`
- `requirements.txt` (added `sentence-transformers`), `pytest.ini` (new — registers the `slow` marker for real-model tests)
- Docs: `docs/RAG_RETRIEVAL.md` (new, full detail), `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/LOCAL_DEVELOPMENT.md` updated

**Embedding model:** `intfloat/multilingual-e5-small` (384 dims), local, no API key — see `docs/RAG_RETRIEVAL.md` for why it was selected and actual measured load/encode times.

**Vector storage:** `LocalVectorStore` (NumPy cosine similarity over SQLite-stored JSON vectors) — real, tested. **PostgreSQL + pgvector was NOT implemented** — no PostgreSQL/Docker available on this machine; the `VectorStore` protocol allows adding it later without touching retrieval code.

**Dependencies:** Phase 3 (needs `DocumentPage` text to chunk, and `StandardDocument.status == "completed"` before indexing).

**APIs implemented and tested (live HTTP + automated):** `POST /api/rag/retrieve` — retrieval only, never calls an LLM.

**Tests:** 42 new tests (100 total in the backend suite): chunking determinism/boundaries, embedding provider (including the real model, marked `slow`), vector store math and compatibility guards, indexing (including re-indexing safety and embedding-failure handling), retrieval service and API (including validation, filtering, empty-index, invalid-document-id cases), and a real retrieval evaluation against the synthetic corpus.

**Acceptance criteria — met:** live HTTP retrieval verified end-to-end against a real processed-and-indexed synthetic document, with correct page/section/document provenance and genuinely relevant top-1 ranking; re-indexing verified not to duplicate chunks; empty-index and invalid-filter cases verified to return honest empty results, never fabricated matches; retrieval evaluation numbers (3/3 top-1 on a 3-query synthetic corpus) are real measurements, explicitly caveated as too small to generalize — no invented accuracy claim.

---

## Phase 5 — Grounded chat + RAG answer generation — ✅ IMPLEMENTED

**Objective (as actually scoped):** Wire `POST /api/chat` to Phase 4's `RetrievalService` and a real (abstracted) `LLMProvider`, replacing Phase 2's keyword-matching demo responder, with grounding, real citations, and honest insufficient-evidence handling.

**Files affected (as actually created/modified):**
- LLM package: `app/llm/{__init__,provider,mock_provider,anthropic_provider,grounding,context_builder}.py`
- Model: `app/models/message_citation.py` (+ `Message.citations` relationship added)
- Repository: `app/repositories/citation_repository.py`
- Service: `app/services/chat_service.py` (rewritten), `app/services/history_service.py` (citations added to responses)
- Schema: `app/schemas/chat.py` (rewritten — `standardId`, `language`, `citations`)
- API: `app/api/routes/chat.py` (rewritten), `app/core/errors.py` (custom error codes support)
- Retrieval extension: `app/rag/retrieval.py` (`standard_id` filtering added), `app/rag/vector_store.py` (`document_id` now accepts a list)
- Migration: `app/db/migrations/versions/0b55be269283_phase_5_message_citations.py`
- Config: `app/core/config.py` (`llm_model` added)
- `requirements.txt` (added `anthropic`, not tested with a real key)
- Tests: `tests/test_chat_rag.py`, `tests/test_prompt_injection_safety.py` (new); `tests/test_chat_and_history.py` (updated to configure the mock provider explicitly, since the real contract now requires one)
- Frontend: `src/services/api.ts` only (`sendChatMessage` gained an optional `standardId` param + citation mapping; `getHistoryById` fixed to apply the same mapping) — no component changed
- **Pre-existing bug fixed** (found during this phase's mandatory frontend baseline, not introduced by it): `src/pages/StandardsExplorerPage.tsx` missing `.catch()` on its category-list fetch, causing an uncaught page error when the backend was unreachable
- Docs: `docs/CHAT_RAG.md` (new), this file, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/LOCAL_DEVELOPMENT.md`, `docs/RAG_RETRIEVAL.md` updated

**Dependencies:** Phase 4 (RetrievalService, indexed chunks).

**APIs:** `POST /api/chat` — real retrieval + real (when configured) LLM generation. `POST /api/chat/stream` was **not implemented** — a normal synchronous response was judged more reliable for a first working implementation, per this phase's own preference for reliability over streaming.

**Tests:** 19 new tests (119 total) — see `docs/CHAT_RAG.md` for the full breakdown. All use mocked/fake LLM and embedding providers; zero external network dependency.

**Acceptance criteria — met:** `AssistantPage` and every other frontend component work unmodified against the real backend; citations render via the existing unmodified `SourceCitationList` component; live HTTP and full-browser verification both performed (mock LLM provider, since no real API key exists in this environment — see `docs/CHAT_RAG.md` for the honest "not tested with a real key" status); mandatory frontend-only (backend-off) and full-stack (backend-on) baselines both established and re-verified after all changes, with zero regressions beyond the one pre-existing bug found and fixed.

---

## Phase 6 — Multilingual

**Objective:** Language detection + translation layer so chat can be conducted in languages beyond English without losing grounding.

**Files affected:** `app/multilingual/*.py`, `app/services/chat.py` (integration point), `src/pages/SettingsPage.tsx` (only if a UI gap is found — language selector already exists via `useLanguage`).

**Dependencies:** Phase 5.

**APIs:** none new; extends `POST /api/chat` request/response with language handling.

**Tests:** English↔Hindi round trip, mixed-language input, citation fidelity preserved (document IDs/page numbers never translated).

**Acceptance criteria:** measured results for each tested language pair reported honestly — no claimed support for languages not actually tested against the configured provider.

---

## Phase 7 — Voice

**Objective:** STT/TTS around the existing chat pipeline — voice is an input/output modality, not a separate answer-generation path.

**Files affected:** `app/voice/*.py` (provider interfaces), `app/api/voice.py`, `src/components/chat/ChatComposer.tsx` (add mic control + state machine: idle/recording/processing/error).

**Dependencies:** Phase 5 (voice reuses the chat/RAG pipeline as-is).

**APIs:** `POST /api/voice/transcribe`, `POST /api/voice/synthesize`.

**Tests:** valid/invalid audio, mic permission denied, empty transcription, TTS failure, end-to-end voice query.

**Acceptance criteria:** visual chat transcript and citations remain the source of truth; audio is never the only evidence channel.

---

## Phase 8 — Standards Explorer integration

**Objective:** Connect `/standards` to real search (already partly done in Phase 2 for basic CRUD) and add the "ask about this standard" contextual link into RAG.

**Files affected:** `src/pages/StandardsExplorerPage.tsx`, `src/pages/StandardDetailPage.tsx` (wire the existing "Ask the assistant about this standard" link to pass `standard_id` context — UI already exists, this is a backend contract addition, not a redesign).

**Dependencies:** Phase 4 (semantic search needs embeddings).

**APIs:** `POST /api/standards/search` (semantic, additive to the existing `GET /api/standards`).

**Tests:** keyword search, semantic search, standard-filtered chat context, missing-document handling (metadata-only vs. fully indexed — must be distinguished, never implied as equivalent).

**Acceptance criteria:** existing Standards UI unchanged visually; new capability is additive.

---

## Phase 9 — Certification and Labs

**Objective:** Move Certification Guide and Lab Directory from static seed data (Phase 2) to structured, queryable guidance, with citations where BIS-sourced.

**Files affected:** `app/services/{certification,labs}.py`, `src/pages/{CertificationGuidePage,LabDirectoryPage}.tsx` (data source only, not layout).

**Dependencies:** Phase 2 (base CRUD), Phase 4 (if citation-backed guidance is added).

**Tests:** search, location/capability filters, citation presence when applicable, explicit "information unavailable" path.

**Acceptance criteria:** never presents generated guidance as official legal/regulatory advice; never invents a laboratory not present in seed/imported data.

---

## Phase 10 — History/Settings persistence

**Objective:** Move `HistoryPage` off direct `mockHistory` import onto the Phase 2 history API; move `useLanguage` and any future preferences to backend-persisted `UserPreference`, with local-anonymous identity pending real auth.

**Files affected:** `src/pages/HistoryPage.tsx`, `src/hooks/useLanguage.ts`, `src/services/api.ts`.

**Dependencies:** Phase 2.

**Tests:** new conversation persists across backend restart, delete conversation, settings persist across reload.

**Acceptance criteria:** UI visually unchanged; data now server-backed instead of static/localStorage-only.

---

## Phase 11 — Future authentication (not scheduled; placeholder)

Deferred until explicitly requested. `UserPreference`/`Conversation` are designed with a nullable/local-dev `user_id` today specifically so real auth can be added later without a schema rewrite.

---

## Phase 12 — Testing and hardening

**Objective:** Security/reliability pass — file upload validation, prompt-injection resistance (documents and user input never override system instructions), rate limiting considerations, secret exposure audit, error-response audit.

**Files affected:** cross-cutting; `docs/SECURITY.md` and `docs/HALLUCINATION_CONTROL.md` written only once there is an actual system behavior to document and test — not before.

**Dependencies:** all prior phases that are in scope for the demo.

**Acceptance criteria:** every claim in the resulting security document is backed by a test that was actually run, with output shown. No "production-secure" claims.

---

## How to use this roadmap

Work one phase at a time. After finishing a phase: run its tests, run the frontend build/typecheck, report actual results, and stop for review before starting the next phase. This roadmap intentionally does not get executed in one pass — each phase's acceptance criteria exist specifically so "done" means something concrete and checkable, not an assertion.
