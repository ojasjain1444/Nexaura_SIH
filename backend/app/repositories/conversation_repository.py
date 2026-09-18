from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, conversation: Conversation) -> Conversation:
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_by_id(self, conversation_id: str) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def list_all(self, user_id: str | None = None) -> list[Conversation]:
        """`user_id=None` lists only anonymous conversations (user_id IS
        NULL) — not every conversation regardless of owner. A logged-in
        user's history must never include another user's (or an
        anonymous session's) conversations, and an anonymous caller must
        never see a logged-in user's conversations either. This is the
        actual privacy boundary the whole point of scoping history by
        user exists to enforce."""
        stmt = select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def touch(self, conversation: Conversation) -> Conversation:
        """Bump updated_at (e.g. after a new message is added)."""
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete(self, conversation: Conversation) -> None:
        self.db.delete(conversation)
        self.db.commit()
