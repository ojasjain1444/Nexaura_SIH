from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.certification_scheme import CertificationScheme


class CertificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[CertificationScheme]:
        stmt = select(CertificationScheme).options(
            selectinload(CertificationScheme.steps), selectinload(CertificationScheme.eligibility_items)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id(self, scheme_id: str) -> CertificationScheme | None:
        stmt = (
            select(CertificationScheme)
            .options(selectinload(CertificationScheme.steps), selectinload(CertificationScheme.eligibility_items))
            .where(CertificationScheme.id == scheme_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, scheme: CertificationScheme) -> CertificationScheme:
        self.db.add(scheme)
        self.db.commit()
        self.db.refresh(scheme)
        return scheme
