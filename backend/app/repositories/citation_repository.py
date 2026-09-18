from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message_citation import MessageCitation


class CitationRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, citation: MessageCitation) -> MessageCitation:
        self.db.add(citation)
        self.db.commit()
        self.db.refresh(citation)
        return citation

    def get_by_message(self, message_id: str) -> list[MessageCitation]:
        stmt = select(MessageCitation).where(MessageCitation.message_id == message_id)
        return list(self.db.execute(stmt).scalars().all())
