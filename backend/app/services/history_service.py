from sqlalchemy.orm import Session

from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import CitationResponse, ConversationDetailResponse, ConversationSummaryResponse, MessageResponse


class ConversationNotFoundError(Exception):
    pass


def _message_to_response(message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        timestamp=message.created_at,
        citations=[
            CitationResponse(
                document_id=c.document_id,
                document_name=c.document_name,
                page_number=c.page_number,
                section=c.section,
                chunk_id=c.chunk_id,
            )
            for c in message.citations
        ],
    )


class HistoryService:
    def __init__(self, db: Session):
        self.repo = ConversationRepository(db)

    def list_conversations(self, user_id: str | None = None) -> list[ConversationSummaryResponse]:
        conversations = self.repo.list_all(user_id=user_id)
        return [
            ConversationSummaryResponse(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at)
            for c in conversations
        ]

    def get_conversation(self, conversation_id: str, user_id: str | None = None) -> ConversationDetailResponse:
        conversation = self._get_owned_conversation(conversation_id, user_id)
        return ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[_message_to_response(m) for m in conversation.messages],
        )

    def delete_conversation(self, conversation_id: str, user_id: str | None = None) -> None:
        conversation = self._get_owned_conversation(conversation_id, user_id)
        self.repo.delete(conversation)

    def _get_owned_conversation(self, conversation_id: str, user_id: str | None):
        """Raises ConversationNotFoundError both when the conversation
        genuinely doesn't exist AND when it exists but belongs to a
        different user (or a different ownership state — anonymous vs.
        logged-in) than the caller. Returning 404 rather than 403 in the
        ownership-mismatch case is deliberate: confirming "this ID exists,
        it's just not yours" would leak that the ID is valid to a caller
        who has no business knowing that."""
        conversation = self.repo.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise ConversationNotFoundError(conversation_id)
        return conversation
