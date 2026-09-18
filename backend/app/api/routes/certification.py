from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.certification import CertificationSchemeResponse
from app.services.certification_service import CertificationService

router = APIRouter(tags=["certification"])


@router.get("/certification", response_model=list[CertificationSchemeResponse])
def list_certification_schemes(db: Session = Depends(get_db)) -> list[CertificationSchemeResponse]:
    service = CertificationService(db)
    return service.list_all()


@router.get("/certification/{scheme_id}", response_model=CertificationSchemeResponse)
def get_certification_scheme(scheme_id: str, db: Session = Depends(get_db)) -> CertificationSchemeResponse:
    service = CertificationService(db)
    result = service.get_by_id(scheme_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Certification scheme not found")
    return result
