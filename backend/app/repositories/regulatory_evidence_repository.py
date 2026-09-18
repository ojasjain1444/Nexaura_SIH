from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.regulatory_evidence import RegulatoryEvidence


class RegulatoryEvidenceRepository:
    """Basic CRUD for RegulatoryEvidence. No ingestion code path calls
    create() — a row here only ever comes from an explicit administrative
    action recording real regulatory evidence, per this project's
    verified_bis-style governance (see app/models/regulatory_evidence.py's
    module docstring)."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_document_id(self, document_id: str) -> RegulatoryEvidence | None:
        stmt = select(RegulatoryEvidence).where(RegulatoryEvidence.document_id == document_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, evidence: RegulatoryEvidence) -> RegulatoryEvidence:
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def save(self, evidence: RegulatoryEvidence) -> RegulatoryEvidence:
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)
        return evidence
