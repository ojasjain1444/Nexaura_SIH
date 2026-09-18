from sqlalchemy.orm import Session

from app.repositories.user_preference_repository import UserPreferenceRepository
from app.schemas.preferences import PreferencesResponse


class PreferencesService:
    def __init__(self, db: Session):
        self.repo = UserPreferenceRepository(db)

    def get(self) -> PreferencesResponse:
        pref = self.repo.get_or_create()
        return PreferencesResponse(language=pref.language)

    def update_language(self, language: str) -> PreferencesResponse:
        pref = self.repo.update_language(language)
        return PreferencesResponse(language=pref.language)
