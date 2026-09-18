# BIS Sahayak — System Architecture

Status: **design document only**. Nothing described here as "backend," "database," "RAG," "OCR," or "voice" has been implemented yet. This document exists to plan the transition from the current frontend-only prototype to a full-stack local development system. See `IMPLEMENTATION_ROADMAP.md` for what gets built, in what order, and how each phase will be verified.

**Note on paths below:** this document was written before the repository was reorganized into separate `frontend/` and `backend/` top-level directories. Every `src/...` path below refers to `frontend/src/...` in the current layout.

---

## 1. What exists today (verified by inspection, 2026-09-17)

This section is fact, not proposal. Everything below was confirmed by reading the actual files in this repository.

**Stack:** React 19, Vite, TypeScript, Tailwind CSS v4, React Router 7, lucide-react. No test framework is installed (no Vitest/Jest in `package.json`) — only `oxlint` for linting.

**Routes** (`src/App.tsx`): `/`, `/assistant`, `/standards`, `/standards/:id`, `/certification`, `/labs`, `/history`, `/settings`, plus a catch-all 404.

**Frontend structure:**
```
src/
  components/
    ui/         Badge, Button, Card, EmptyState, ErrorState, Spinner
    chat/       ChatComposer, MessageBubble, SourceCitationList, ThinkingIndicator
    standards/  StandardStatusBadge
  pages/        HomePage, AssistantPage, StandardsExplorerPage, StandardDetailPage,
                CertificationGuidePage, LabDirectoryPage, HistoryPage, SettingsPage, NotFoundPage
  layouts/      AppLayout, Sidebar, Header, navItems
  hooks/        useChat, useLanguage, useDebouncedValue
  services/     api.ts  <- the single frontend/backend boundary (see below)
  data/         mockStandards, mockSchemes, mockLabs, mockChat, mockHistory
  types/        chat.ts, standards.ts, nav.ts
```

**The mock API layer — `src/services/api.ts`.** This is the only file in the frontend that "talks" to anything resembling a backend. It exports:
- `sendChatMessage(userText: string): Promise<ChatMessage>` — resolves via keyword matching in `data/mockChat.ts` (`findMockResponse`), with an artificial 900ms delay.
- `searchStandards(query: StandardsQuery): Promise<IndianStandard[]>` — filters the in-memory `mockStandards` array.
- `getStandardById(id): Promise<IndianStandard | undefined>`
- `listSchemes(): Promise<CertificationScheme[]>`, `getSchemeById(id)`
- `searchLabs(query: LabsQuery): Promise<TestingLab[]>`

It also already exports `API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''` — declared but **not currently used** by any function, and no `.env` file defines `VITE_API_BASE_URL` anywhere in the repo today.

**Existing TypeScript types** (`src/types/`):
- `chat.ts`: `ChatRole`, `SourceCitation { id, standardCode, title, clause?, url? }`, `ChatMessage { id, role, content, timestamp, sources?, quickReplies? }`, `ChatSession { id, title, createdAt, updatedAt, messages[] }`, `MessageStatus`, `Language` (`'en'|'hi'|'bn'|'ta'|'te'|'mr'|'gu'|'kn'`).
- `standards.ts`: `StandardStatus`, `IndianStandard { id, code, title, category, description, status, lastAmended, sector, relatedCodes[] }`, `SchemeType`, `CertificationScheme { id, name, type, summary, eligibility[], steps[], averageDurationDays, fees }`, `CertificationStep { order, title, description }`, `LabAccreditation`, `TestingLab { id, name, city, state, accreditations[], testCategories[], contact, distanceKm? }`.

**Current chat flow:** `AssistantPage` reads an optional `?q=` search param on mount and auto-sends it, otherwise shows quick-topic buttons. `useChat` hook holds `messages: ChatMessage[]` and `status: 'idle'|'sending'|'thinking'|'error'` in React state (component-local, lost on refresh). Sending calls `sendChatMessage`, which does simple substring/keyword matching against ~6 hardcoded response templates — this is not retrieval, not an LLM call, and not connected to any document.

**Current standards flow:** `StandardsExplorerPage` debounces a search box (`useDebouncedValue`), calls `searchStandards({ search, category })`, which filters an 8-item hardcoded array client-side. `StandardDetailPage` calls `getStandardById`.

**Current history flow:** `HistoryPage` reads directly from `data/mockHistory.ts` (a static array of 3 sessions) — it does **not** go through `services/api.ts` at all. This is an inconsistency worth fixing when the backend lands: history should be fetched the same way everything else is.

**Current settings flow:** `useLanguage` hook persists a language code to `localStorage` under key `bis-sahayak-language`. There is no backend call and no other preference (voice, theme, response style) exists in the codebase today. `SettingsPage` only renders the language picker.

**Update (Phase 2 complete):** the paragraph above described the state before any backend work started. As of Phase 2, a real FastAPI backend, SQLite database (Alembic-migrated), and full test suite exist under `backend/` — see `docs/DATABASE.md` and `docs/IMPLEMENTATION_ROADMAP.md` for what was actually built. `src/services/api.ts` now makes real `fetch()` calls for standards, labs, certification, history, chat persistence, and preferences. Still true and unchanged: no OCR, RAG, voice, or multilingual implementation exists; no Docker config exists; chat responses are still a keyword-matched demo responder, not an LLM.

---

## 2. Target architecture (proposed)

```
┌──────────────────────────┐
│   React Frontend (Vite)  │   unchanged UI, only src/services/api.ts
│   :5173                  │   is rewired from mocks -> fetch()
└─────────────┬─────────────┘
              │ HTTP (JSON), same-origin CORS allow-list
              ▼
┌──────────────────────────┐
│   FastAPI Backend         │   :8000
│   api/  core/  models/    │
│   schemas/  services/     │
└──┬───────┬───────┬───────┬┘
   │       │       │       │
   ▼       ▼       ▼       ▼
┌─────┐ ┌──────┐ ┌──────┐ ┌────────────┐
│ DB  │ │Ingest│ │ OCR  │ │ RAG/Vector │
│(SQL │ │ pipe │ │ pipe │ │  layer     │
│Alch)│ │      │ │      │ │            │
└─────┘ └──────┘ └──────┘ └─────┬──────┘
                                 ▼
                        ┌────────────────┐
                        │ LLM / Embedding │  behind a provider
                        │ provider adapter│  interface — swappable,
                        └────────────────┘  not hard-coded

   (future, not this phase)
   ┌───────────┐  ┌──────────────┐  ┌───────────────────┐
   │  Voice     │  │ Multilingual │  │ External BIS APIs │
   │ STT / TTS  │  │ translation  │  │ (future)          │
   └───────────┘  └──────────────┘  └───────────────────┘
```

**Layer responsibilities:**

- **Frontend** — presentation and interaction only. Never talks to the database, OCR, or LLM provider directly. Its only contract with the rest of the system is `src/services/api.ts`.
- **Backend API (FastAPI)** — request validation (Pydantic schemas), auth (future), orchestration between services, response shaping. Contains no business logic itself — delegates to the service layer.
- **Service layer** — business logic (e.g. "what counts as a valid chat turn," "how history is paginated"). Calls repositories for persistence, calls RAG/LLM adapters for generation.
- **Repository layer** — the only code that issues SQLAlchemy queries. Keeps persistence details out of services, which makes swapping SQLite → PostgreSQL later a repository-only change.
- **Database** — durable storage for conversations, messages, standards metadata, documents, chunks, labs, schemes, preferences.
- **Ingestion pipeline** — turns a raw file in `data/raw/` into a `StandardDocument` + extracted page text. Independent of RAG; can run and be tested before any embedding code exists.
- **OCR pipeline** — invoked by ingestion only for pages without extractable text. Modular provider interface so the local engine (e.g. Tesseract) can later be swapped for a cloud OCR service without touching ingestion logic.
- **RAG/vector layer** — chunks processed document text, embeds it, stores vectors, and serves similarity search. Strictly additive on top of ingestion — does not change how documents are stored.
- **LLM/embedding provider adapter** — a thin interface (`generate(prompt) -> str`, `embed(text) -> vector`) so the concrete provider (OpenAI, Anthropic, a local model, etc.) is a configuration choice, not a code dependency scattered through the app.
- **Voice / multilingual / external integrations** — explicitly out of scope for the backend-foundation phase. Planned as provider-interface modules that sit beside the RAG layer, not inside it, so they can be built later without refactoring what came before.

---

## 3. Backend technology recommendation

**Recommendation: Python + FastAPI + SQLAlchemy 2.x + Pydantic v2, SQLite for local dev, PostgreSQL + pgvector as the documented production/scale-up path.**

Why this, concretely, for this machine and this project:

| Concern | Choice | Reasoning |
|---|---|---|
| Language/framework | Python 3.11 + FastAPI | Python 3.11 is already installed via Homebrew on this Mac (`/opt/homebrew/bin/python3.11`) — no new install needed. The system default `python3` is 3.9.6 (Xcode-bundled), which works with FastAPI/SQLAlchemy 2/Pydantic v2 but 3.11 is faster and has better typing support. FastAPI gives async support, automatic OpenAPI docs, and Pydantic validation for free — well matched to a small team building incrementally. |
| Local database | **SQLite** for Phase 1–2, **PostgreSQL** documented as the upgrade path | This machine has no `psql` client and no Docker installed today. Requiring Postgres from day one would mean the backend cannot even start until infra is installed — that contradicts "runnable" and "realistic for a student project." SQLAlchemy's ORM makes the switch mechanical (same models, different connection string) **as long as we avoid Postgres-only types until we actually migrate**. This is why Phase 1 must not use `pgvector`-specific column types. |
| Future vector storage | pgvector (once on PostgreSQL) | Documented, not installed. When RAG is actually built (a later phase), the project will need either pgvector or a standalone vector store (e.g. Chroma, sqlite-vec). Recommendation: pgvector once Postgres is adopted, because it keeps vectors and relational data (document, page, standard) in one transactional store — simpler ops for a hackathon-scale system than running a second database. |
| ORM | SQLAlchemy 2.x (declarative style, typed) | Works identically against SQLite and PostgreSQL, which is exactly the migration path above. |
| Validation | Pydantic v2 | FastAPI's native schema layer; keeps `schemas/` (API contracts) explicitly separate from `models/` (DB tables), per the user's requirement. |
| OCR | **Tesseract (via `pytesseract`)**, evaluated below | Free, runs fully offline, installable via `brew install tesseract`, has an Indian-language (`hin`, etc.) trained-data option relevant to BIS documents. Alternative considered: cloud OCR (Google Vision / AWS Textract) — higher accuracy but requires API keys and network access, which conflicts with "runs locally" and "does not require every provider configured to start." Recommendation: implement the `OCRProvider` interface with Tesseract as the default local implementation, and leave room for a cloud implementation behind the same interface later — never hard-coded to one vendor. |
| LLM / embeddings | Provider-agnostic adapter interface; concrete provider chosen via `LLM_PROVIDER` / `EMBEDDING_PROVIDER` env vars | Per the user's explicit requirement: do not hard-code the system to one AI vendor. The interface is two functions (`generate`, `embed`); which SDK backs them is a config decision, implemented only when the RAG phase actually starts — not before. |
| Background processing | FastAPI `BackgroundTasks` for Phase 1; a real queue (e.g. Celery/RQ with Redis, or `arq`) documented as the upgrade path for document ingestion once files are large/numerous | `BackgroundTasks` is enough for "don't block the upload response" at prototype scale and needs zero extra infrastructure. A dedicated worker queue is the honest answer for production-scale ingestion, but installing Redis/Celery before there is a single ingestion endpoint would be premature infrastructure. |

---

## 4. Backend directory structure (proposed, not yet created)

Adapted from the structure suggested in the prompt, trimmed to match what this project actually needs at each stage rather than pre-creating empty folders for unbuilt features.

```
backend/
  app/
    main.py              FastAPI app instantiation, router registration, CORS
    core/
      config.py          Settings (pydantic-settings), reads env vars
      errors.py          Shared exception types + handlers (no stack traces to client)
      logging.py         Local dev logging setup
    api/
      health.py          GET /api/health
      chat.py            POST /api/chat  (Phase 1: stub; later: real)
      standards.py       GET /api/standards, /api/standards/{id}
      labs.py            GET /api/labs
      certification.py   GET /api/certification
      history.py         GET /api/history, /api/history/{id}
      documents.py       (Phase 3+) upload/status endpoints
      rag.py             (Phase 5+) POST /api/rag/query
      voice.py           (Phase 8+) transcribe/synthesize
    models/              SQLAlchemy ORM classes (one file per aggregate)
    schemas/             Pydantic request/response models — mirrors models/ but never imported by it
    services/            business logic; one module per domain (chat, standards, labs, certification, history, documents)
    repositories/        one per persisted entity; the only layer issuing queries
    rag/                 (later) chunking, retrieval, prompt assembly
    ingestion/           (later) file validation, extraction orchestration
    ocr/                 (later) OCRProvider interface + Tesseract implementation
    voice/               (later) STT/TTS provider interfaces
    multilingual/        (later) detection/translation service
    db/
      base.py            SQLAlchemy declarative base, session factory
      session.py         `get_db()` dependency for FastAPI routes
  tests/
    test_health.py
    ... one file per endpoint/service as they're built
  data/
    raw/                 developer-provided source documents (gitignored)
    processed/           extracted text/pages (gitignored)
  .env.example
  requirements.txt / pyproject.toml
```

This phase creates **no files under `backend/`** — see `IMPLEMENTATION_ROADMAP.md` Phase 1 for when this structure actually gets built.

---

## 5. API design

Endpoints are grouped by what already has a frontend consumer today vs. what is purely future-facing.

**Already needed by the existing frontend (Phase 1–2 priority):**
| Endpoint | Replaces | Notes |
|---|---|---|
| `GET /api/health` | — | New; used to verify the backend is alive. |
| `POST /api/chat` | `sendChatMessage()` | Request: `{ message, conversation_id? }`. Response: `ChatMessage`-shaped JSON (reuse the existing frontend type). |
| `GET /api/standards` | `searchStandards()` | Query params: `search`, `category`, `status` — same shape as today's `StandardsQuery`. |
| `GET /api/standards/{id}` | `getStandardById()` | |
| `GET /api/certification` | `listSchemes()` | |
| `GET /api/certification/{id}` | `getSchemeById()` | |
| `GET /api/labs` | `searchLabs()` | Query params: `search`, `city`, `category`. |
| `GET /api/history` | (currently bypasses `api.ts` entirely — a gap to close) | List of `ChatSession` summaries. |
| `GET /api/history/{id}` | | Full session with messages. |
| `DELETE /api/history/{id}` | | New capability, not in current mock layer. |

**Future-facing (not built until their respective roadmap phase):**
`POST /api/chat/stream`, `POST /api/standards/search` (semantic), `POST /api/documents/upload`, `GET /api/documents/{id}`, `GET /api/documents/{id}/status`, `POST /api/rag/query`, `POST /api/voice/transcribe`, `POST /api/voice/synthesize`.

Design choices worth flagging now:
- REST + JSON throughout, matching what `fetch()` in `services/api.ts` already expects.
- Response shapes should mirror the existing frontend TypeScript types wherever a type already exists (`ChatMessage`, `IndianStandard`, `CertificationScheme`, `TestingLab`, `ChatSession`) so the eventual `services/api.ts` rewrite is close to a drop-in replacement rather than a redesign.
- Errors follow a single envelope (see §10) so the frontend's existing `ErrorState` component can render any backend failure without per-endpoint handling.

---

## 6. Database entities and relationships

```
User (future — not built until auth phase)
  └─< Conversation
         └─< Message
                └─< Citation >── StandardDocument (which doc/page a message cited)

Standard
  └─< StandardDocument
         └─< DocumentChunk
                └── Embedding   (one embedding per chunk; separate table so the
                                 embedding model/dimension can change without
                                 touching chunk text)

CertificationScheme        (standalone reference table; no FK dependency on Standard
                             today — schemes reference standards by free-text in the
                             mock data, not a foreign key. Revisit if/when real BIS
                             scheme data links to specific standard codes.)

Lab                        (standalone reference table)

DocumentProcessingJob ──> StandardDocument  (1 job per ingestion attempt; tracks
                                              status transitions, retries, errors)

UserPreference ──> User (future) | or a single-row "local dev user" record
                                   until auth exists (see §9)
```

Field-level notes (elaborated fully when each model is actually implemented in its roadmap phase — this is the relationship shape, not final DDL):

- **Conversation**: `id`, `title`, `created_at`, `updated_at`, `user_id` (nullable until auth exists).
- **Message**: `id`, `conversation_id` (FK), `role`, `content`, `created_at`. Citations are a separate table rather than a JSON blob so they can be queried/joined against `StandardDocument`.
- **Standard**: mirrors `IndianStandard` today (`code`, `title`, `category`, `description`, `status`, `last_amended`, `sector`) plus `related_codes` as a join table or array column (decide when implemented — arrays are Postgres-only, so SQLite-first means a join table).
- **StandardDocument**: the ingested file behind a Standard — `id`, `standard_id` (nullable; a document can exist before it's linked to a catalogued standard), `filename`, `file_hash`, `mime_type`, `size_bytes`, `page_count`, `ingested_at`, `status`.
- **DocumentChunk**: `id`, `document_id` (FK), `page_number`, `text`, `section_context` (nullable) — created only once ingestion/chunking exists; **not created in Phase 1 or 2**.
- **Embedding**: `id`, `chunk_id` (FK, 1:1), `vector`, `model_name`, `dimension` — created only once the RAG phase starts.
- **Lab**: mirrors `TestingLab` today.
- **CertificationScheme**: mirrors `CertificationScheme`/`CertificationStep` today — steps likely become a child table (`CertificationStep` with `scheme_id` FK) rather than a JSON column, so they can be queried/ordered by the DB.
- **DocumentProcessingJob**: `id`, `document_id` (FK), `status` (`uploaded|queued|processing|ocr_required|processed|failed`), `error_message` (nullable), `started_at`, `finished_at`.
- **UserPreference**: `id`, `user_id` (or a fixed local-dev identifier pre-auth), `language`, future: `voice_enabled`, `response_style`.

---

## 7. Frontend/backend boundary

**`src/services/api.ts` remains the only file that changes.** No component, hook, or page should ever call `fetch()` directly — this is already how the file is structured today (see §1), so the migration is additive, not a redesign:

- Add `fetch()`-based implementations alongside (or replacing) the current mock-resolving bodies of `sendChatMessage`, `searchStandards`, `getStandardById`, `listSchemes`, `getSchemeById`, `searchLabs`.
- Add the missing `getHistory()`, `getHistoryById()`, `deleteHistory()` functions here — today `HistoryPage` reads `mockHistory` directly, which is the one place that doesn't go through this boundary. Fixing that is part of routing history through the same seam as everything else, not a new pattern.
- `API_BASE_URL` (already declared, currently unused) becomes the actual `fetch()` prefix once wired up. It reads from `VITE_API_BASE_URL`, which needs a `.env` entry (e.g. `VITE_API_BASE_URL=http://localhost:8000`) — this file does not exist yet.
- Function signatures and return types stay identical to what pages already import, so `AssistantPage`, `StandardsExplorerPage`, `StandardDetailPage`, `CertificationGuidePage`, `LabDirectoryPage` require **zero changes** when the backend lands — they already only know about `services/api.ts`'s exported functions, never about mock data directly (`HistoryPage` is the one exception to fix, noted above).

---

## 8. RAG architecture

**Retrieval half — ✅ IMPLEMENTED (Phase 4):**

```
query → embedding (local, multilingual-e5-small) → vector similarity search
(document_id or standard_id filter supported) → top-k chunks with page/section provenance
```

See `docs/RAG_RETRIEVAL.md` for full detail: chunking strategy, embedding model selection and measured performance, the explicit LOCAL-vs-pgvector vector store distinction, and live-verified retrieval results. `POST /api/rag/retrieve` implements exactly this half of the pipeline and nothing more — it never calls an LLM.

**Generation half — ✅ IMPLEMENTED (Phase 5):**

```
top-k chunks → build_context_block() (delimited, untrusted-data framing) →
LLMProvider.generate(system_prompt, history, user_message) → answer
→ MessageCitation rows built from the actual retrieval results (never
  from the LLM's output) → persisted + returned to the frontend
```

Grounding rules (see `app/llm/grounding.py`, full detail in `docs/CHAT_RAG.md`): the LLM is instructed to answer only from retrieved chunks for document-specific questions, to explicitly say when evidence is insufficient rather than guess, and to treat retrieved document content as untrusted data rather than instructions — verified with a deliberately adversarial "ignore previous instructions" chunk in `tests/test_prompt_injection_safety.py`. Citations map to real `DocumentChunk`/`StandardDocument` rows via the persisted `MessageCitation` table — never fabricated by the LLM.

**LLM provider status:** abstracted (`app/llm/provider.py`), with a mock provider (explicit opt-in, clearly labelled) and a real Anthropic provider implemented. **No real LLM API key exists in this development environment**, so all Phase 5 verification used the mock provider — see `docs/CHAT_RAG.md` for the exact, honest status.

## 9. OCR / document ingestion architecture — ✅ IMPLEMENTED (Phase 3)

Implemented as designed: `OCRProvider` protocol (`app/ocr/provider.py`) with `TesseractOCRProvider` (`app/ocr/tesseract_provider.py`) as the concrete implementation — local, offline, no API key, using PyMuPDF (not `pypdf`/`pdfplumber` as originally sketched — PyMuPDF was chosen because it also handles page-to-image rendering for the OCR path, avoiding a second library). Ingestion (`app/ingestion/extraction.py`) decides per-page whether OCR is needed based on native text length; verified independently correct on mixed-content documents. See `docs/DATABASE.md` §8a for full details and `docs/IMPLEMENTATION_ROADMAP.md` Phase 3 for what was tested. Document chunking, embeddings, and vector search remain unimplemented — that is Phase 4 (RAG).

## 10. Multilingual architecture (future — not implemented)

A single `multilingual` service handling language detection and translation, sitting between the chat API and the RAG layer — not scattered across endpoints. Two candidate designs (multilingual embeddings vs. translate-then-retrieve) are noted as an open decision to be tested empirically when this phase starts, not decided speculatively now.

## 11. Voice architecture (future — not implemented)

`SpeechToTextProvider` / `TextToSpeechProvider` interfaces. Voice input feeds the *same* chat/RAG pipeline as typed text — there is no separate "voice answer generator." This keeps grounding and citation behavior identical regardless of input modality, once built.

---

## 12. Error handling and API contract

A single error envelope, applied consistently by a FastAPI exception handler in `core/errors.py`:

```json
{ "error": { "code": "not_found", "message": "Standard not found" } }
```

No stack traces, file paths, or internal exception text ever reach the client. Full details are logged server-side only (`core/logging.py`). This lets the frontend's existing `ErrorState` component handle any failure uniformly without per-endpoint special-casing.

## 13. CORS

Development CORS allows exactly `http://localhost:5173` (the Vite dev server), not a wildcard. Configured via `core/config.py` so it can be extended (e.g. a deployed frontend origin) without code changes, only environment configuration.

## 14. Security considerations (forward-looking; enforced starting Phase 1, deepened later)

- No secrets in source control — all provider keys/DB URLs via environment variables, with `.env.example` documenting required names but no real values.
- No AI credentials required for the backend to start or for `/api/health` to respond.
- File upload validation (MIME type, size limits, path traversal prevention) is a hard requirement once the documents endpoint exists — not implemented until that phase, and not claimed as implemented before then.
- Uploaded documents and user chat input are both untrusted content; once RAG exists, retrieved document text must never be treated as system instructions.

## 15. Local development setup (once Phase 1 is implemented — not yet runnable)

```bash
# Backend (once created)
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend (already runnable today)
npm install
npm run dev
```

This machine has Python 3.11/3.12 available via Homebrew, no Docker, and no PostgreSQL client installed — which is why SQLite is the Phase 1–2 default rather than PostgreSQL, with Postgres+pgvector documented as the upgrade path once ingestion/RAG actually need it.

## 16. Future scalability

SQLite → PostgreSQL is a connection-string-and-migration change if Postgres-specific SQL/types are avoided until the switch. The repository/service split means swapping the LLM or embedding provider, or moving from `BackgroundTasks` to a real job queue, touches one module each rather than cascading through the codebase. None of this is built yet — it is the reason the layering in §2 is shaped the way it is.
