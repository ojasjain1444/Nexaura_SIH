"""
Message — one turn in a Conversation, matching the frontend's ChatMessage
type (src/types/chat.ts) closely.

Phase 5 adds `citations` (see app/models/message_citation.py) — populated
only for assistant messages generated with real retrieval evidence.

Still NOT included:
- quickReplies: purely a UI/mock-response artifact of the pre-Phase-5
  keyword-matching responder, not a durable fact about a conversation.
- model/voice/language metadata: no such data exists to store yet.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Indexed: every message read/write is scoped to one conversation
    # (loading a conversation's transcript is the core history/chat query).
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    citations: Mapped[list["MessageCitation"]] = relationship(
        "MessageCitation", back_populates="message", cascade="all, delete-orphan"
    )
