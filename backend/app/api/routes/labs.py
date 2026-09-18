from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.lab import LabResponse
from app.services.labs_service import LabsService

router = APIRouter(tags=["labs"])


@router.get("/labs", response_model=list[LabResponse])
def search_labs(
    search: str | None = None,
    city: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[LabResponse]:
    service = LabsService(db)
    return service.search(search=search, city=city, category=category)
