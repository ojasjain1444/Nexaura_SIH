from sqlalchemy.orm import Session

from app.repositories.standard_repository import StandardRepository
from app.schemas.standard import StandardResponse


def _to_response(standard) -> StandardResponse:
    return StandardResponse(
        id=standard.id,
        code=standard.code,
        title=standard.title,
        category=standard.category,
        description=standard.description,
        status=standard.status,
        last_amended=standard.last_amended,
        sector=standard.sector,
        related_codes=[rc.code for rc in standard.related_codes],
    )


class StandardsService:
    def __init__(self, db: Session):
        self.repo = StandardRepository(db)

    def search(
        self, search: str | None = None, category: str | None = None, status: str | None = None
    ) -> list[StandardResponse]:
        standards = self.repo.search(search=search, category=category, status=status)
        return [_to_response(s) for s in standards]

    def get_by_id(self, standard_id: str) -> StandardResponse | None:
        standard = self.repo.get_by_id(standard_id)
        return _to_response(standard) if standard else None
