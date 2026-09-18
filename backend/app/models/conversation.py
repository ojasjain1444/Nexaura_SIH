"""
Conversation — a chat session, matching the frontend's ChatSession type
(src/types/chat.ts) closely enough that the API adapter layer stays thin.

`user_id` is nullable: real accounts now exist (app.models.user), but the
existing frontend has no login UI or token storage yet, so a request with
no Authorization header must keep working exactly as before — anonymous,
user_id left null. A conversation only gets a real user_id when the
request that created it carried a valid session token (see
app.api.deps.get_optional_current_user and
app.services.chat_service.ChatService._get_or_create_conversation). This
mirrors the same "nullable until the concept is actually wired up"
convention already used for StandardDocument.standard_id elsewhere in this
codebase.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Indexed: HistoryPage lists conversations ordered by recency
    # (existing UI sorts by updatedAt today), so this column is queried on
    # every history list request.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    # Phase 10: at most one ProductProfile per conversation — the structured
    # product-discovery state that conversation's messages progressively
    # build up. None until the assistant recognizes a product-discovery
    # conversation and creates one (see app/services/chat_service.py).
    product_profile: Mapped["ProductProfile | None"] = relationship(
        "ProductProfile", back_populates="conversation", cascade="all, delete-orphan", uselist=False
    )
