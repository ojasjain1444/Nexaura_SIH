"""
Developer CLI for ingesting AND indexing a document in one command
(Phase 8) — the target flow diagram's
"PDF -> extract -> chunk -> embed -> persist -> index" as one operation,
rather than requiring two separate commands (app.ingestion.ingest then
app.rag.index_document_cli, the two-step process used manually in earlier
phases' live verification).

This is a thin orchestration wrapper: it calls the exact same
DocumentService/index_document functions the two standalone CLIs already
use, in sequence, and reports which stage failed if any step breaks. It
does not change ingestion, indexing, chunking, or embedding behavior in any
way — a document processed via this command produces byte-identical
DocumentPage/DocumentChunk rows to running the two CLIs by hand.

Usage:
    python -m app.ingestion.ingest_and_index data/raw/example.pdf
"""

import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.ingestion.validation import DocumentValidationError
from app.rag.index_document import IndexingError, index_document
from app.services.document_service import DocumentService, DuplicateDocumentError


def run(file_path: str) -> int:
    path = Path(file_path)
    if not path.exists():
        print(f"ERROR: file not found: {file_path}")
        return 1

    content = path.read_bytes()
    db = SessionLocal()
    try:
        service = DocumentService(db)

        print("Stage 1/3: registering upload (validation, duplicate check)...")
        try:
            document = service.register_upload(content=content, filename=path.name, mime_type="application/pdf")
        except DocumentValidationError as exc:
            print(f"FAILED at registration: {exc}")
            return 1
        except DuplicateDocumentError as exc:
            print(f"ALREADY INGESTED: this file was already ingested as document {exc.existing_document_id}")
            print(f"To re-index it, run: python -m app.rag.index_document_cli {exc.existing_document_id}")
            return 1
        print(f"  Registered as document {document.id} ({document.original_filename})")

        print("Stage 2/3: running ingestion pipeline (extraction, OCR where needed, metadata, features)...")
        result = service.process_document(document.id, content)
        if result.status == "failed":
            status_detail = service.get_status(document.id)
            print(f"FAILED at ingestion pipeline: {status_detail.error_message}")
            print(f"Document {document.id} is left in status 'failed' — not indexed.")
            return 1
        print(f"  Pipeline completed. Pages: {result.page_count}")
        print(f"  Standard number: {result.extracted_standard_number or '(none found)'}")
        print(f"  Title: {result.extracted_title or '(none found)'}")
        print(f"  Edition: {result.extracted_edition or '(none found)'}")
        print(f"  Publication year: {result.extracted_publication_year or '(none found)'}")
        print(f"  Source type: {result.source_type} (never 'verified_bis' unless a human confirms it)")

        print("Stage 3/3: indexing (chunking + local embeddings)...")
        try:
            index_result = index_document(db, document.id)
        except IndexingError as exc:
            print(f"FAILED at indexing: {exc}")
            print(f"Document {document.id} completed ingestion but is NOT indexed — not retrievable yet.")
            return 1
        print(f"  Chunks created: {index_result.chunks_created}")
        print(f"  Chunks embedded: {index_result.chunks_embedded}")
        if index_result.chunks_created == 0:
            print("  WARNING: zero chunks produced — document may have no extractable text.")

        print(f"Done. Document {document.id} is ingested, indexed, and ready for retrieval.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.ingestion.ingest_and_index <path-to-pdf>")
        sys.exit(1)
    sys.exit(run(sys.argv[1]))
