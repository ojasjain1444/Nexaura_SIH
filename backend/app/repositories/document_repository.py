from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.document_chunk import DocumentChunk
from app.models.document_feature import DocumentFeature
from app.models.document_page import DocumentPage
from app.models.standard_document import StandardDocument
from app.models.standard_requirement import StandardRequirement
from app.models.standard_scope import StandardScope


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, document: StandardDocument) -> StandardDocument:
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: str) -> StandardDocument | None:
        return self.db.get(StandardDocument, document_id)

    def get_by_hash(self, file_hash: str) -> StandardDocument | None:
        stmt = select(StandardDocument).where(StandardDocument.file_hash == file_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(self) -> list[StandardDocument]:
        # Newest first — a document-management list is read top-down as
        # "most recently uploaded first", the same convention used by
        # ConversationRepository for chat history.
        stmt = select(StandardDocument).order_by(StandardDocument.ingested_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def count_chunks(self, document_id: str) -> int:
        stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        return len(list(self.db.execute(stmt).scalars().all()))

    def delete(self, document: StandardDocument) -> None:
        # Cascades to pages/features/chunks via the ORM-level
        # cascade="all, delete-orphan" declared on StandardDocument's
        # relationships (see app/models/standard_document.py) — this does
        # not depend on SQLite's ondelete="CASCADE" being enforced at the
        # DB level (it isn't; PRAGMA foreign_keys is never enabled here).
        self.db.delete(document)
        self.db.commit()

    def get_with_pages(self, document_id: str) -> StandardDocument | None:
        stmt = (
            select(StandardDocument)
            .options(selectinload(StandardDocument.pages))
            .where(StandardDocument.id == document_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_with_features(self, document_id: str) -> StandardDocument | None:
        stmt = (
            select(StandardDocument)
            .options(selectinload(StandardDocument.features))
            .where(StandardDocument.id == document_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_status(self, document: StandardDocument, status: str, error_message: str | None = None) -> StandardDocument:
        document.status = status
        document.error_message = error_message
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def set_page_count(self, document: StandardDocument, page_count: int) -> None:
        document.page_count = page_count
        self.db.add(document)
        self.db.commit()

    def set_extracted_metadata(
        self,
        document: StandardDocument,
        standard_number: str | None,
        title: str | None,
        edition: str | None,
        publication_year: str | None = None,
    ) -> None:
        document.extracted_standard_number = standard_number
        document.extracted_title = title
        document.extracted_edition = edition
        document.extracted_publication_year = publication_year
        self.db.add(document)
        self.db.commit()

    def add_page(self, page: DocumentPage) -> DocumentPage:
        self.db.add(page)
        self.db.commit()
        self.db.refresh(page)
        return page

    def add_feature(self, feature: DocumentFeature) -> DocumentFeature:
        self.db.add(feature)
        self.db.commit()
        self.db.refresh(feature)
        return feature

    def set_scope(self, scope: StandardScope) -> StandardScope:
        self.db.add(scope)
        self.db.commit()
        self.db.refresh(scope)
        return scope

    def get_scope(self, document_id: str) -> StandardScope | None:
        stmt = select(StandardScope).where(StandardScope.document_id == document_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def add_requirement(self, requirement: StandardRequirement) -> StandardRequirement:
        self.db.add(requirement)
        self.db.commit()
        self.db.refresh(requirement)
        return requirement

    def get_requirements(self, document_id: str) -> list[StandardRequirement]:
        stmt = select(StandardRequirement).where(StandardRequirement.document_id == document_id)
        return list(self.db.execute(stmt).scalars().all())
