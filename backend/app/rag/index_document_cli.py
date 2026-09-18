"""
Developer CLI for indexing a processed document.

Usage:
    python -m app.rag.index_document_cli <document_id>

Requires the document to already have status "completed" from the Phase 3
pipeline (see app/ingestion/ingest.py to process a document first). Safe to
re-run — re-creates chunks/embeddings from scratch each time.
"""

import sys

from app.db.session import SessionLocal
from app.rag.index_document import IndexingError, index_document


def run(document_id: str) -> int:
    db = SessionLocal()
    try:
        try:
            result = index_document(db, document_id)
        except IndexingError as exc:
            print(f"INDEXING FAILED: {exc}")
            return 1

        print(f"Indexed document {result.document_id}")
        print(f"Chunks created: {result.chunks_created}")
        print(f"Chunks embedded: {result.chunks_embedded}")
        if result.chunks_created == 0:
            print("WARNING: zero chunks produced — document may have no extractable text.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.rag.index_document_cli <document_id>")
        sys.exit(1)
    sys.exit(run(sys.argv[1]))
