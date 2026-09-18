from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_preference import LOCAL_DEFAULT_USER_KEY, UserPreference


class UserPreferenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, user_key: str = LOCAL_DEFAULT_USER_KEY) -> UserPreference:
        stmt = select(UserPreference).where(UserPreference.user_key == user_key)
        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing:
            return existing
        pref = UserPreference(user_key=user_key, language="en")
        self.db.add(pref)
        self.db.commit()
        self.db.refresh(pref)
        return pref

    def update_language(self, language: str, user_key: str = LOCAL_DEFAULT_USER_KEY) -> UserPreference:
        pref = self.get_or_create(user_key)
        pref.language = language
        self.db.add(pref)
        self.db.commit()
        self.db.refresh(pref)
        return pref
