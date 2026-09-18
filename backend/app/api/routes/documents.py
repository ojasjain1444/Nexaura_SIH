"""
Document ingestion API.

POST /api/documents/upload registers the document synchronously (fast:
validation, hashing, file write, DB row) and kicks off the actual
extraction/OCR/feature-extraction pipeline as a background task — so the
upload response returns quickly even for a large scanned PDF, per Step 10's
"the upload request should not become an unnecessarily long blocking
operation."
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentFeatureResponse, DocumentPageResponse, DocumentResponse, DocumentStatusResponse
from app.services.document_service import DocumentService, DuplicateDocumentError, InvalidDocumentTypeError
from app.ingestion.validation import DocumentValidationError
from app.rag.index_document import IndexingError

router = APIRouter(tags=["documents"])


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentResponse]:
    service = DocumentService(db)
    return service.list_documents()


def _run_pipeline_in_background(document_id: str, content: bytes, db_session_factory) -> None:
    # Background tasks run after the response is sent, outside the
    # request's DB session — a fresh session is opened here for the
    # duration of the pipeline run and closed when it finishes.
    # `db_session_factory` is the *active* get_db dependency at request
    # time (respecting FastAPI's dependency_overrides, e.g. in tests),
    # never a hardcoded SessionLocal — otherwise a test using an isolated
    # database would have its background task silently run against the
    # real bis_sahayak.db instead, and fail to find the document.
    db_gen = db_session_factory()
    db = next(db_gen)
    try:
        service = DocumentService(db)
        service.process_document(document_id, content)
    finally:
        db.close()


@router.post("/documents/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    # Phase 12: optional, user-asserted classification/provenance note.
    # Both are plain form fields (not JSON) since this is a multipart
    # upload — omitted document_type defaults to "OTHER" in the service
    # layer, never inferred here or anywhere else.
    document_type: str | None = Form(default=None),
    source: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    content = await file.read()
    service = DocumentService(db)
    try:
        document = service.register_upload(
            content=content,
            filename=file.filename or "unnamed.pdf",
            mime_type=file.content_type or "application/octet-stream",
            document_type=document_type,
            source=source,
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except InvalidDocumentTypeError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_DOCUMENT_TYPE", "message": str(exc)})
    except DuplicateDocumentError as exc:
        raise HTTPException(status_code=409, detail=f"Document already uploaded as {exc.existing_document_id}")

    active_get_db = request.app.dependency_overrides.get(get_db, get_db)
    background_tasks.add_task(_run_pipeline_in_background, document.id, content, active_get_db)
    return document


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentResponse:
    service = DocumentService(db)
    result = service.get_document(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(document_id: str, db: Session = Depends(get_db)) -> DocumentStatusResponse:
    service = DocumentService(db)
    result = service.get_status(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.get("/documents/{document_id}/pages", response_model=list[DocumentPageResponse])
def get_document_pages(document_id: str, db: Session = Depends(get_db)) -> list[DocumentPageResponse]:
    service = DocumentService(db)
    result = service.get_pages(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.get("/documents/{document_id}/features", response_model=list[DocumentFeatureResponse])
def get_document_features(document_id: str, db: Session = Depends(get_db)) -> list[DocumentFeatureResponse]:
    service = DocumentService(db)
    result = service.get_features(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.post("/documents/{document_id}/reindex", response_model=DocumentResponse)
def reindex_document(document_id: str, db: Session = Depends(get_db)) -> DocumentResponse:
    service = DocumentService(db)
    try:
        result = service.reindex_document(document_id)
    except IndexingError as exc:
        raise HTTPException(status_code=422, detail={"code": "INDEXING_ERROR", "message": str(exc)})
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> None:
    service = DocumentService(db)
    deleted = service.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
