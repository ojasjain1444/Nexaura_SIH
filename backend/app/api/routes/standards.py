from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.standard import StandardResponse
from app.services.standards_service import StandardsService

router = APIRouter(tags=["standards"])


@router.get("/standards", response_model=list[StandardResponse])
def search_standards(
    search: str | None = None,
    category: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[StandardResponse]:
    service = StandardsService(db)
    return service.search(search=search, category=category, status=status)


@router.get("/standards/{standard_id}", response_model=StandardResponse)
def get_standard(standard_id: str, db: Session = Depends(get_db)) -> StandardResponse:
    service = StandardsService(db)
    result = service.get_by_id(standard_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Standard not found")
    return result
