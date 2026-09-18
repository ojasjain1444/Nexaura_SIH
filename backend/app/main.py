"""
BIS Sahayak backend — FastAPI application entry point.

Real chat generation (local Ollama or mock, never a demo responder),
hybrid semantic+keyword retrieval, document ingestion (PDF/OCR extraction,
metadata, chunking, embeddings, scope/requirement extraction), an
Internet-Archive-backed fallback for standards not yet locally ingested,
and demo-grade username+PIN accounts scoping conversation history. See
docs/ for the per-area design docs (RAG_RETRIEVAL.md, CHAT_RAG.md, etc.).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.certification import router as certification_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.history import router as history_router
from app.api.routes.labs import router as labs_router
from app.api.routes.preferences import router as preferences_router
from app.api.routes.rag import router as rag_router
from app.api.routes.standards import router as standards_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.single_instance import acquire_or_exit

settings = get_settings()
logger = logging.getLogger("bis_sahayak")

# Runs at true module-import time — before the FastAPI app object, the
# lifespan hook, or anything else in this module exists — so a duplicate
# process exits before uvicorn (or, worse, uvicorn --reload's separate
# parent watcher process) ever touches the socket. Confirmed via direct
# timing that `import app.main` completes before uvicorn does any socket
# work; confirmed via live testing that checking any later (e.g. inside
# the lifespan hook below) is too late — see
# app/core/single_instance.py's module docstring for the full story,
# including why this is skipped automatically under pytest.
acquire_or_exit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loads the local sentence-transformers embedding model once at
    # startup instead of on the first real request. Confirmed via live
    # testing that a cold load takes long enough (measured up to ~60s+ on
    # this machine) that the very first chat/retrieval request after
    # starting the server can time out client-side — indistinguishable
    # from a real failure to whoever is using the app at that moment
    # (e.g. during a live demo). Any failure here is logged, not raised:
    # the app must still start even if the model can't be pre-warmed
    # (e.g. no network on first-ever run before the model is cached) —
    # it will simply fall back to the old cold-load-on-first-use behavior.
    try:
        from app.rag.embeddings import get_embedding_provider

        get_embedding_provider().embed_text("warmup")
        logger.info("Embedding model pre-loaded at startup.")
    except Exception as exc:  # noqa: BLE001 — startup must never crash because warmup failed
        logger.warning("Embedding model pre-load failed (will load on first use instead): %s", exc)
    yield


app = FastAPI(title=settings.service_name, lifespan=lifespan)

# Development CORS: only the Vite dev server origin(s) from configuration,
# never a wildcard. See docs/ARCHITECTURE.md §13.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(standards_router, prefix="/api")
app.include_router(labs_router, prefix="/api")
app.include_router(certification_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(preferences_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
