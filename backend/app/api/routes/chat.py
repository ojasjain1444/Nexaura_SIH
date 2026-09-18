from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_optional_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatGenerationError, ChatNotFoundError, ChatService

router = APIRouter(tags=["chat"])

# Maps ChatGenerationError.code to the HTTP status the client should see.
# Only codes actually raised by ChatService appear here.
_ERROR_STATUS_BY_CODE = {
    "LLM_NOT_CONFIGURED": 503,
    "LLM_PROVIDER_ERROR": 502,
    "RETRIEVAL_ERROR": 502,
    # Phase 7 — local Ollama provider. Both are "the configured provider is
    # unreachable/misconfigured", same family as LLM_NOT_CONFIGURED (503,
    # not the client's fault) rather than an upstream 502.
    "OLLAMA_NOT_RUNNING": 503,
    "OLLAMA_MODEL_NOT_FOUND": 503,
}


@router.post("/chat", response_model=ChatResponse)
def send_chat_message(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> ChatResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_REQUEST", "message": "message must not be empty"})

    service = ChatService(db)
    try:
        return service.send_message(
            payload.message,
            payload.conversation_id,
            standard_id=payload.standard_id,
            language=payload.language,
            mode=payload.mode,
            user_id=current_user.id if current_user else None,
        )
    except ChatNotFoundError:
        raise HTTPException(
            status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}
        )
    except ChatGenerationError as exc:
        status_code = _ERROR_STATUS_BY_CODE.get(exc.code, 500)
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)})
