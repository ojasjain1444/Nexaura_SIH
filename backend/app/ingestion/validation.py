"""
Document upload validation — the first pipeline stage, independently
testable without touching the database or any PDF library.
"""

import hashlib

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB — generous for a BIS standard PDF, small enough to reject junk
ALLOWED_MIME_TYPES = {"application/pdf"}


class DocumentValidationError(Exception):
    pass


def validate_upload(content: bytes, mime_type: str, filename: str) -> None:
    if not content:
        raise DocumentValidationError("File is empty.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise DocumentValidationError(f"File exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit.")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise DocumentValidationError(f"Unsupported file type '{mime_type}'. Only PDF is supported in this phase.")
    if not content.startswith(b"%PDF-"):
        raise DocumentValidationError("File does not appear to be a valid PDF (missing %PDF- header).")
    if not filename:
        raise DocumentValidationError("Filename is required.")


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
