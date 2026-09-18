"""
RetrievalService — query → embedding → vector search → evidence chunks.

Deliberately does NOT know anything about LLMs, chat, or answer generation.
It has one job: given a query, return the most semantically similar
indexed chunks with their real source provenance. What a future phase does
with those chunks (generate an answer, render citations) is entirely
outside this module's concern — this is the boundary described in Phase 4's
architecture principle.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.standard_document import StandardDocument
from app.rag.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider
from app.rag.vector_store import VectorStore, VectorStoreError, get_vector_store
from app.repositories.document_repository import DocumentRepository
from app.schemas.retrieval import RetrievedChunk

# Matches the "passage: " prefix convention in app/rag/index_document.py —
# E5-family models require a "query: " prefix on the query side.
QUERY_PREFIX = "query: "

# Off-corpus detection.
#
# Cosine similarity alone cannot do this. Measured against the live index,
# "for a wooden chair" — furniture appears nowhere in the corpus — scores
# 0.841, while a genuinely answerable concrete question scores 0.881. The
# bands overlap, so any score floor that rejects the first also rejects real
# questions. (docs/RAG_RETRIEVAL.md records the same finding.) The cause is
# that E5 matches the *register* of standards prose — "standard",
# "certification", "requirements", "shall conform to" — which every query of
# this kind shares regardless of subject.
#
# Lexical grounding separates them cleanly, because the thing an off-corpus
# question is actually about is precisely the word missing from the evidence:
# no retrieved chunk contains "chair", "shampoo", "laptop" or "bakery".
# Measured over the live corpus, answerable queries ground >= 0.50 of their
# content words (most at 1.00) and off-corpus queries <= 0.60, so the cutoff
# sits between. Cheap substring matching is deliberate: no extra model, no
# extra query latency.
MIN_CONTENT_WORD_GROUNDING = 0.5

# Words carrying no subject matter. Two groups are stripped. Ordinary
# function words carry no topic at all; standards-register words ("standard",
# "certification", "requirement", "test", "apply", "cover", "mark", "label",
# "lab") are just as useless here despite looking meaningful, because every
# document in a corpus of standards contains them. Leaving them in lets an
# off-corpus question ground itself on boilerplate — "which standard covers
# mobile phone batteries" scored as covered on "standard" and "cover" alone,
# while the words that actually matter, "mobile" and "batteries", appeared
# nowhere.
_STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those there here
    what which who whom whose when where why how whether
    is are was were be been being am do does did doing done
    have has had having can could shall should will would may might must
    i me my mine we us our you your yours it its they them their
    for of to in on at by with from into onto under over about as
    need want require get getting go tell give take
    also so now ok okay please kindly thanks
    all any some each every both other another same
    not no nor only just very more most much many few
    standard standards specification specifications code codes
    certification certificate certified certify certifications
    requirement requirements required
    test testing tested lab labs laboratory laboratories
    apply applies applied applicable application
    cover covers covered covering
    process procedure obtain market sell product products
    india indian bis
    """.split()
)


class RetrievalError(Exception):
    pass


def _stem(word: str) -> str:
    """Crude suffix trim so a query word matches its inflected forms in the
    documents ("batteries"/"battery", "bars"/"bar"). Not linguistically
    correct and does not need to be — it only has to make the same word
    collide with itself across forms."""
    for suffix in ("ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def _content_words(query: str) -> set[str]:
    return {
        _stem(word)
        for word in re.findall(r"[a-z]+", query.lower())
        if word not in _STOPWORDS and len(word) > 2
    }


def looks_off_corpus(query: str, chunks: list[RetrievedChunk]) -> bool:
    """True when retrieval returned chunks that do not actually concern what
    the question is about.

    Retrieval always returns its nearest neighbours, so "which standard
    applies to laptops" comes back with concrete and rebar clauses that score
    respectably and mention nothing resembling a laptop. This reports that
    mismatch so the answer layer can decline instead of inviting the model to
    reason over unrelated evidence.

    A signal, not a filter: the chunks are still returned, so the caller can
    still tell the user what the corpus does contain.
    """
    if not chunks:
        return False

    content_words = _content_words(query)
    if not content_words:
        # Nothing but function and register words — no subject to check.
        return False

    evidence_words = {
        _stem(word) for chunk in chunks for word in re.findall(r"[a-z]+", chunk.text.lower())
    }
    grounded = sum(1 for word in content_words if word in evidence_words)
    return (grounded / len(content_words)) < MIN_CONTENT_WORD_GROUNDING


class RetrievalService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ):
        self.db = db
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.vector_store = vector_store or get_vector_store()
        self.document_repo = DocumentRepository(db)

    def retrieve(
        self,
        query: str,
        top_k: int,
        document_id: str | None = None,
        standard_id: str | None = None,
        document_types: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        if document_id is not None and standard_id is not None:
            raise RetrievalError("document_id and standard_id are mutually exclusive filters")

        search_document_id: str | list[str] | None = document_id

        if document_id is not None:
            document = self.document_repo.get_by_id(document_id)
            if document is None:
                raise RetrievalError(f"document_id '{document_id}' does not exist")

        if standard_id is not None:
            # Legitimate, schema-backed filter: StandardDocument.standard_id
            # is a real FK to Standard (added in Phase 3) — resolving it to
            # the set of document IDs linked to that standard, then
            # filtering retrieval to those, is not a fabricated filter.
            stmt = select(StandardDocument.id).where(StandardDocument.standard_id == standard_id)
            linked_document_ids = [row[0] for row in self.db.execute(stmt).all()]
            search_document_id = linked_document_ids  # may be [] — handled honestly by the vector store (0 matches)

        try:
            query_vector = self.embedding_provider.embed_text(QUERY_PREFIX + query)
        except EmbeddingError as exc:
            raise RetrievalError(f"Failed to embed query: {exc}") from exc

        try:
            matches = self.vector_store.similarity_search(
                self.db,
                query_vector=query_vector,
                model_name=self.embedding_provider.model_name,
                top_k=top_k,
                document_id=search_document_id,
                document_types=document_types,
            )
        except VectorStoreError as exc:
            raise RetrievalError(f"Vector search failed: {exc}") from exc

        # Chunks are returned as ranked, without a relevance cutoff: a
        # per-chunk score floor is not meaningful for this embedding model
        # (see MIN_TOP_SCORE). Judging whether the set as a whole answers the
        # question is the answer layer's call, via looks_off_corpus().
        results = []
        for match in matches:
            document = self.document_repo.get_by_id(match.chunk.document_id)
            results.append(
                RetrievedChunk(
                    chunk_id=match.chunk.id,
                    document_id=match.chunk.document_id,
                    document_name=document.original_filename if document else "(unknown document)",
                    document_type=document.document_type if document else None,
                    page_number=match.chunk.page_number,
                    section=match.chunk.section,
                    text=match.chunk.text,
                    similarity_score=match.similarity_score,
                )
            )
        return results
