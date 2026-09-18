from sqlalchemy.orm import Session

from app.repositories.certification_repository import CertificationRepository
from app.schemas.certification import CertificationSchemeResponse, CertificationStepResponse


def _to_response(scheme) -> CertificationSchemeResponse:
    return CertificationSchemeResponse(
        id=scheme.id,
        name=scheme.name,
        type=scheme.type,
        summary=scheme.summary,
        eligibility=[e.requirement for e in scheme.eligibility_items],
        steps=[CertificationStepResponse(order=s.order, title=s.title, description=s.description) for s in scheme.steps],
        average_duration_days=scheme.average_duration_days,
        fees=scheme.fees,
    )


class CertificationService:
    def __init__(self, db: Session):
        self.repo = CertificationRepository(db)

    def list_all(self) -> list[CertificationSchemeResponse]:
        return [_to_response(s) for s in self.repo.list_all()]

    def get_by_id(self, scheme_id: str) -> CertificationSchemeResponse | None:
        scheme = self.repo.get_by_id(scheme_id)
        return _to_response(scheme) if scheme else None
