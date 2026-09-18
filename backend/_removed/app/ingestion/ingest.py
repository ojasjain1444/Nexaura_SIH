"""
Developer CLI for ingesting a document from the command line.

Usage:
    python -m app.ingestion.ingest data/raw/example.pdf

Runs the exact same registration + pipeline code as the
POST /api/documents/upload endpoint (via DocumentService), so CLI and API
ingestion never diverge in behavior. Reports the final status; does not
claim success if the pipeline actually failed.
"""

import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.ingestion.validation import DocumentValidationError
from app.services.document_service import DocumentService, DuplicateDocumentError


def ingest_file(file_path: str) -> int:
    path = Path(file_path)
    if not path.exists():
        print(f"ERROR: file not found: {file_path}")
        return 1

    content = path.read_bytes()
    db = SessionLocal()
    try:
        service = DocumentService(db)
        try:
            document = service.register_upload(content=content, filename=path.name, mime_type="application/pdf")
        except DocumentValidationError as exc:
            print(f"VALIDATION FAILED: {exc}")
            return 1
        except DuplicateDocumentError as exc:
            print(f"DUPLICATE: this file was already ingested as document {exc.existing_document_id}")
            return 1

        print(f"Registered document {document.id} ({document.original_filename})")
        print("Running pipeline (extraction, OCR where needed, metadata, features)...")

        result = service.process_document(document.id, content)

        print(f"Final status: {result.status}")
        if result.status == "failed":
            status_detail = service.get_status(document.id)
            print(f"Error: {status_detail.error_message}")
            return 1

        print(f"Pages: {result.page_count}")
        print(f"Extracted standard number: {result.extracted_standard_number or '(none found)'}")
        print(f"Extracted title: {result.extracted_title or '(none found)'}")
        print(f"Extracted edition: {result.extracted_edition or '(none found)'}")
        print(f"Extracted publication year: {result.extracted_publication_year or '(none found)'}")
        print(f"Source type: {result.source_type} (never 'verified_bis' unless a human confirms it — see docs/DATABASE.md)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.ingestion.ingest <path-to-pdf>")
        sys.exit(1)
    sys.exit(ingest_file(sys.argv[1]))
