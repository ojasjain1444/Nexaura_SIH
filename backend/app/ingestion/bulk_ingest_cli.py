"""
Developer CLI for bulk-ingesting a folder of real BIS PDFs.

Usage:
    python -m app.ingestion.bulk_ingest_cli <folder> [--document-type INDIAN_STANDARD] [--source "manual acquisition"]

Runs the exact same DocumentService.register_upload() + process_document()
path a single UI upload (POST /api/documents/upload) goes through — this is
not a separate ingestion system, just that same path looped over every PDF
in a folder, so a bulk-ingested document behaves identically to one
uploaded through the UI (same validation, same duplicate-by-hash
detection, same pipeline stages, same StandardScope/StandardRequirement
extraction).

Intended source of input files: PDFs a human has already legitimately
obtained (e.g. downloaded one at a time via BIS's own free-indigenous-
standard portal, https://www.bis.gov.in/whats_new/download-indigenous-
-standards-free-of-cost/ — login + captcha required per download, by
design). This script only processes files already sitting on disk; it does
not fetch, scrape, or automate access to any website.

A failure on one file (corrupt PDF, duplicate hash, embedding crash) is
reported and skipped — it must never abort the whole batch, since a folder
of dozens of real PDFs will realistically include at least one problem
file, and losing the rest of the batch to it would defeat the point of
bulk ingestion.
"""

import argparse
import sys
import time
from pathlib import Path

from app.db.session import SessionLocal
from app.ingestion.validation import DocumentValidationError
from app.services.document_service import DocumentService, DuplicateDocumentError, InvalidDocumentTypeError


def _ingest_one(service: DocumentService, path: Path, document_type: str | None, source: str | None) -> str:
    content = path.read_bytes()
    document = service.register_upload(
        content=content,
        filename=path.name,
        mime_type="application/pdf",
        document_type=document_type,
        source=source,
    )
    result = service.process_document(document.id, content)
    if result.status != "completed":
        return f"FAILED ({result.status}): {result.error_message or 'no error message recorded'}"
    return f"OK — {result.chunk_count} chunks, status={result.display_status}"


def run(folder: str, document_type: str | None, source: str | None) -> int:
    pdf_paths = sorted(Path(folder).glob("*.pdf"))
    if not pdf_paths:
        print(f"No .pdf files found in {folder}")
        return 1

    print(f"Found {len(pdf_paths)} PDF(s) in {folder}\n")

    succeeded, failed, skipped_duplicates = 0, 0, 0
    db = SessionLocal()
    try:
        service = DocumentService(db)
        for i, path in enumerate(pdf_paths, start=1):
            started = time.monotonic()
            # Printed on its own line (not held open with end=""): the
            # embedding library's own progress output
            # ("Loading weights: 0%|...") writes '\r'-based updates to the
            # same stream and can visually overwrite an unflushed partial
            # line — confirmed on a real run where this made the filename
            # appear to vanish from the terminal, even though it was
            # genuinely printed.
            print(f"[{i}/{len(pdf_paths)}] {path.name}", flush=True)
            try:
                outcome = _ingest_one(service, path, document_type, source)
                print(f"  -> {outcome} ({time.monotonic() - started:.1f}s)")
                succeeded += 1
            except DuplicateDocumentError as exc:
                print(f"  -> SKIPPED (already ingested as document {exc.existing_document_id})")
                skipped_duplicates += 1
            except (DocumentValidationError, InvalidDocumentTypeError) as exc:
                print(f"  -> REJECTED: {exc}")
                failed += 1
            except Exception as exc:  # noqa: BLE001 — one bad file must not abort the whole batch
                print(f"  -> ERROR: {exc}")
                failed += 1
    finally:
        db.close()

    print(f"\nDone: {succeeded} ingested, {skipped_duplicates} duplicates skipped, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk-ingest a folder of real BIS PDFs.")
    parser.add_argument("folder", help="Folder containing .pdf files to ingest")
    parser.add_argument("--document-type", default=None, help="e.g. INDIAN_STANDARD (defaults to OTHER, same as UI upload)")
    parser.add_argument("--source", default=None, help="Free-text provenance note, e.g. 'manual BIS portal download'")
    args = parser.parse_args()
    sys.exit(run(args.folder, args.document_type, args.source))
