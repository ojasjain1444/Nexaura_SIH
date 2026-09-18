from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product_profile import ProductProfile


class ProductProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_conversation_id(self, conversation_id: str) -> ProductProfile | None:
        stmt = select(ProductProfile).where(ProductProfile.conversation_id == conversation_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, profile: ProductProfile) -> ProductProfile:
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def save(self, profile: ProductProfile) -> ProductProfile:
        """Persists in-place mutations to an already-tracked profile (e.g.
        after apply_updates() sets new field values)."""
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile
