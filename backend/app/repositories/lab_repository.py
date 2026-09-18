from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.lab import Lab, LabTestCategory


class LabRepository:
    def __init__(self, db: Session):
        self.db = db

    def search(self, search: str | None = None, city: str | None = None, category: str | None = None) -> list[Lab]:
        stmt = select(Lab).options(selectinload(Lab.accreditations), selectinload(Lab.test_categories))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Lab.name.ilike(like), Lab.city.ilike(like)))
        if city:
            stmt = stmt.where(Lab.city == city)
        if category:
            stmt = stmt.join(LabTestCategory).where(LabTestCategory.category == category)
        return list(self.db.execute(stmt).scalars().all())

    def create(self, lab: Lab) -> Lab:
        self.db.add(lab)
        self.db.commit()
        self.db.refresh(lab)
        return lab
