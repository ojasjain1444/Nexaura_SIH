# Local Development Setup

Status as of Phase 5 (grounded chat + RAG answer generation): the commands below were actually run against this repository and verified to work. This document will be extended as later phases add multilingual generation, voice, etc.

**Repository layout:** `frontend/` (React + Vite + TypeScript) and `backend/` (FastAPI + SQLAlchemy) are separate top-level directories, each with their own dependencies. Run frontend commands from inside `frontend/` and backend commands from inside `backend/` — not from the repo root.

## 1. Prerequisites

- **Node.js** (already required for the frontend — verified working with the installed version on this machine).
- **Python 3.11**. This machine has it via Homebrew at `/opt/homebrew/bin/python3.11` (the system default `python3` is 3.9.6, which is not used for this project). If you don't have it: `brew install python@3.11`.
- **Tesseract OCR binary** (Phase 3): `brew install tesseract`. This is a system binary, not a pip package — `pytesseract` (in `requirements.txt`) is just a Python wrapper around it and will fail at OCR time (not at import time) if the binary isn't installed.
- No PostgreSQL, Docker, or other services are required — the backend uses SQLite by default (see `docs/DATABASE.md`). This also means no pgvector — Phase 4's vector search uses a local NumPy implementation (see `docs/RAG_RETRIEVAL.md`).
- **~500MB-1GB free disk + internet access on first run** (Phase 4): the embedding model (`intfloat/multilingual-e5-small`) downloads automatically on first use and is cached under `~/.cache/huggingface/`. No API key is needed, but the very first embedding call requires network access to download it once.

## 2. Backend setup

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Environment variables

Copy the example file:

```bash
cp .env.example .env
```

`backend/.env.example` documents every variable. **None are required** — the backend starts and `/api/health` works with the file absent entirely, or with every value left blank. As of Phase 2, `DATABASE_URL` and `CORS_ORIGINS` are read by real code; the AI/OCR/voice provider variables remain unused placeholders for future phases.

## 4. Database setup (migrations + seed)

Phase 2 uses SQLite by default (`sqlite:///./bis_sahayak.db`, created inside `backend/`), with real tables managed by Alembic migrations — not `create_all()`. See `docs/DATABASE.md` for the full schema and why.

```bash
cd backend
source .venv/bin/activate

# Apply migrations (creates all tables)
alembic upgrade head

# Seed with prototype/demo data (safe to re-run — will not duplicate rows)
python -m app.db.seed
```

Verified output:
```
Seed complete. Created: 8 standards, 4 certification schemes, 6 labs. (Existing matching rows were left untouched — safe to re-run.)
All seeded rows are marked source_type='demo' — this is prototype data, not verified official BIS information.
```

To reset the database entirely: delete `backend/bis_sahayak.db` and re-run the two commands above.

If you want to point at PostgreSQL instead (not required, not tested as part of this phase), set in `.env`:
```
DATABASE_URL=postgresql://user:password@localhost:5432/bis_sahayak
```
This requires `psycopg2-binary` (not currently in `requirements.txt` — add it when actually switching), then re-run `alembic upgrade head` against the new database.

## 4a. Document ingestion (Phase 3)

Ingest a PDF from the command line:

```bash
cd backend
source .venv/bin/activate
python -m app.ingestion.ingest data/raw/<your-file>.pdf
```

`data/raw/` is empty in this repository — no real BIS document has been provided. To exercise the pipeline without a real document, use the synthetic test fixtures (never real BIS content, clearly labelled in their own text):

```bash
python -m app.ingestion.ingest tests/fixtures/test_text.pdf     # native text extraction
python -m app.ingestion.ingest tests/fixtures/test_scanned.pdf  # OCR path (Tesseract)
python -m app.ingestion.ingest tests/fixtures/test_mixed.pdf    # one native page, one OCR page
```

Verified output (test_text.pdf):
```
Registered document <uuid> (test_text.pdf)
Running pipeline (extraction, OCR where needed, metadata, features)...
Final status: completed
Pages: 1
Extracted standard number: IS 99999
...
```

To regenerate the fixture PDFs: `python3 tests/fixtures/generate_test_pdfs.py`.

## 4b. Semantic indexing + retrieval (Phase 4)

Once a document has been ingested (above) and reached `status: completed`, index it for semantic search:

```bash
python -m app.rag.index_document_cli <document-id>
```

Verified output:
```
Indexed document <uuid>
Chunks created: 4
Chunks embedded: 4
```

The first call downloads the embedding model (~470MB, one-time, requires internet access) and takes about a minute; subsequent calls in the same process reuse the loaded model, and a fresh process reload from the cache takes ~10s. Safe to re-run — re-indexing replaces a document's chunks rather than duplicating them.

Query the indexed content (no LLM involved — this returns evidence chunks, not a generated answer):

```bash
curl -X POST http://localhost:8000/api/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the scope of this document?", "top_k": 3}'
```

See `docs/RAG_RETRIEVAL.md` for the full retrieval architecture, chunking strategy, and honest limitations.

## 4c. Chat / LLM setup (Phase 5)

`POST /api/chat` now performs real retrieval and requires an LLM provider to be configured — with none set (the default), it returns a structured `503 LLM_NOT_CONFIGURED` error rather than a fabricated answer. Two options:

**Mock provider (no API key needed, clearly labelled MOCK in every response):**
```bash
LLM_PROVIDER=mock uvicorn app.main:app --reload --port 8000
```
This is what was used for all Phase 5 development verification — no real LLM API key exists in this environment.

**Real provider (Anthropic — implemented but not tested with a real key here):**
```bash
# in backend/.env:
LLM_PROVIDER=anthropic
LLM_API_KEY=<your key>
LLM_MODEL=claude-sonnet-4-5   # optional, this is the default
```

See `docs/CHAT_RAG.md` for the full chat/grounding/citation architecture.

## 5. Start the backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
# or, to enable chat generation with the mock provider:
LLM_PROVIDER=mock uvicorn app.main:app --reload --port 8000
```

Verified output on this machine:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

## 6. Verify the backend

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/standards
curl http://localhost:8000/api/labs
curl http://localhost:8000/api/certification
curl http://localhost:8000/api/history
curl http://localhost:8000/api/preferences

# Document upload (Phase 3) — using a synthetic test fixture
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@tests/fixtures/test_text.pdf;type=application/pdf"
# then, using the returned "id":
curl http://localhost:8000/api/documents/<id>/status
curl http://localhost:8000/api/documents/<id>/pages
curl http://localhost:8000/api/documents/<id>/features

# Semantic retrieval (Phase 4) — index first (see §4b), then:
curl -X POST http://localhost:8000/api/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the scope of this document?", "top_k": 3}'

# Grounded chat (Phase 5) — requires LLM_PROVIDER set (see §4c); returns
# citations from real retrieval when documents are indexed:
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the scope of this document?"}'
```

All verified working against a seeded database as of this phase.

## 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Verified: serves at `http://localhost:5173`. **Important:** if port 5173 is already taken by a stray process, Vite will silently move to 5174 — but the backend's CORS is configured to allow only `http://localhost:5173` by default, so a frontend running on a different port will get CORS errors. Free the port first: `lsof -ti:5173 -sTCP:LISTEN | xargs kill`.

Optionally set the backend URL explicitly (defaults to `http://localhost:8000` if omitted):
```bash
cd frontend
cp .env.example .env
# edit VITE_API_BASE_URL if your backend runs elsewhere
```

## 8. Run backend tests

```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

Verified: 119 tests pass, covering health, database session plumbing, migrations table presence, chat/history persistence, standards/labs/certification CRUD and search, preferences, seed idempotency, (Phase 3) document validation, native/OCR text extraction, mixed-content page-by-page handling, metadata/feature extraction, OCR failure handling, duplicate/large/empty-document edge cases, (Phase 4) chunking determinism, the real embedding model, vector store math and compatibility guards, indexing/re-indexing, and retrieval (service + API), and (Phase 5) grounded chat flow, retrieval integration, citation generation, LLM-not-configured/provider-failure handling, standard_id filtering, and prompt-injection safety. Tests run against isolated temporary SQLite databases and storage directories (one per test) — never against your real `bis_sahayak.db` or `data/processed/`. All LLM calls in tests use mocked/fake providers — zero external network dependency. A handful of tests are marked `slow` (load the real embedding model, ~10s each); run `pytest -m "not slow"` to skip them for a faster iteration loop, or the plain command above to run everything.

## 9. Run frontend checks

```bash
cd frontend
npx tsc -b --noEmit
npm run build
```

Verified: both clean, no errors, as of this phase.

## 10. Manual end-to-end check

With both servers running (steps 5 and 7):
1. Open `http://localhost:5173/assistant`, send a message — it now creates a real `Conversation` + `Message` rows in the backend (not browser-only state).
2. Open `/history` — the conversation you just created appears, fetched from `GET /api/history`.
3. Open `/settings`, change language — persisted via `PUT /api/preferences`; reload the page and it stays changed (confirms it's backend-persisted, not just `localStorage`).
4. Open `/standards`, `/labs`, `/certification` — all now list real database rows (the seeded demo data), not the old in-browser mock arrays.

## 11. Troubleshooting

- **`uvicorn: command not found`** — the virtual environment isn't activated. Run `source .venv/bin/activate` from inside `backend/` first.
- **`ModuleNotFoundError: No module named 'app'`** — you're not running uvicorn/alembic/pytest from inside the `backend/` directory.
- **`/api/standards` returns `[]`** — the database hasn't been seeded yet. Run `python -m app.db.seed`.
- **Alembic says "Target database is not up to date"** — run `alembic upgrade head` before starting the server.
- **Port 8000 already in use** — another process is bound to it. Find and stop it: `lsof -ti:8000 -sTCP:LISTEN | xargs kill`, or start uvicorn with `--port <other-port>` and update `VITE_API_BASE_URL` to match.
- **Port 5173 already in use / CORS errors in the browser console** — see the note in step 7. Free port 5173 rather than letting Vite fall back to 5174, or add the fallback port to `CORS_ORIGINS` in `backend/.env`.
