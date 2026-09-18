"""
Local filesystem storage for uploaded documents.

Files are stored under `{STORAGE_PATH}/processed/{document_id}.pdf` —
named by the document's own UUID rather than the original filename, so two
uploads with the same filename never collide, and the original filename is
preserved separately as StandardDocument.original_filename for display.
"""

from pathlib import Path

from app.core.config import get_settings


def store_document_file(document_id: str, content: bytes) -> str:
    settings = get_settings()
    storage_dir = Path(settings.storage_path) / "processed"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{document_id}.pdf"
    file_path.write_bytes(content)
    return str(file_path)


def read_document_file(storage_path: str) -> bytes:
    return Path(storage_path).read_bytes()
