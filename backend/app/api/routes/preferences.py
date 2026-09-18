from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.preferences import PreferencesResponse, PreferencesUpdateRequest
from app.services.preferences_service import PreferencesService

router = APIRouter(tags=["preferences"])


@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(db: Session = Depends(get_db)) -> PreferencesResponse:
    service = PreferencesService(db)
    return service.get()


@router.put("/preferences", response_model=PreferencesResponse)
def update_preferences(payload: PreferencesUpdateRequest, db: Session = Depends(get_db)) -> PreferencesResponse:
    service = PreferencesService(db)
    return service.update_language(payload.language)
