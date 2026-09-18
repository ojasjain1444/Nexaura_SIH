from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_optional_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ConversationDetailResponse, ConversationSummaryResponse
from app.services.history_service import ConversationNotFoundError, HistoryService

router = APIRouter(tags=["history"])


@router.get("/history", response_model=list[ConversationSummaryResponse])
def list_history(
    db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_current_user)
) -> list[ConversationSummaryResponse]:
    service = HistoryService(db)
    return service.list_conversations(user_id=current_user.id if current_user else None)


@router.get("/history/{conversation_id}", response_model=ConversationDetailResponse)
def get_history_item(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> ConversationDetailResponse:
    service = HistoryService(db)
    try:
        return service.get_conversation(conversation_id, user_id=current_user.id if current_user else None)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.delete("/history/{conversation_id}", status_code=204)
def delete_history_item(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> None:
    service = HistoryService(db)
    try:
        service.delete_conversation(conversation_id, user_id=current_user.id if current_user else None)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
