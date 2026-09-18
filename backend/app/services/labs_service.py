from sqlalchemy.orm import Session

from app.repositories.lab_repository import LabRepository
from app.schemas.lab import LabResponse


def _to_response(lab) -> LabResponse:
    return LabResponse(
        id=lab.id,
        name=lab.name,
        city=lab.city,
        state=lab.state,
        accreditations=[a.accreditation for a in lab.accreditations],
        test_categories=[c.category for c in lab.test_categories],
        contact=lab.contact,
        distance_km=None,
    )


class LabsService:
    def __init__(self, db: Session):
        self.repo = LabRepository(db)

    def search(self, search: str | None = None, city: str | None = None, category: str | None = None) -> list[LabResponse]:
        labs = self.repo.search(search=search, city=city, category=category)
        return [_to_response(lab) for lab in labs]
