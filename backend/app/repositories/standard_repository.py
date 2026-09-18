from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.standard import Standard


class StandardRepository:
    def __init__(self, db: Session):
        self.db = db

    def search(
        self, search: str | None = None, category: str | None = None, status: str | None = None
    ) -> list[Standard]:
        stmt = select(Standard).options(selectinload(Standard.related_codes))
        if search:
            like = f"%{search}%"
            # Matches the existing mock searchStandards() behavior exactly:
            # case-insensitive substring match across title, code, description.
            stmt = stmt.where(
                or_(
                    Standard.title.ilike(like),
                    Standard.code.ilike(like),
                    Standard.description.ilike(like),
                )
            )
        if category:
            stmt = stmt.where(Standard.category == category)
        if status:
            stmt = stmt.where(Standard.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id(self, standard_id: str) -> Standard | None:
        stmt = (
            select(Standard)
            .options(selectinload(Standard.related_codes))
            .where(Standard.id == standard_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> Standard | None:
        stmt = select(Standard).where(Standard.code == code)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, standard: Standard) -> Standard:
        self.db.add(standard)
        self.db.commit()
        self.db.refresh(standard)
        return standard
