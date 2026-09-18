from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.services.auth_service import AuthService, InvalidCredentialsError, UsernameAlreadyTakenError

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=LoginResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        return AuthService(db).register(payload.username, payload.pin)
    except UsernameAlreadyTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        return AuthService(db).login(payload.username, payload.pin)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/auth/logout", status_code=204)
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> None:
    if authorization and authorization.startswith("Bearer "):
        AuthService(db).logout(authorization.removeprefix("Bearer ").strip())


@router.get("/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=current_user.id, username=current_user.username)
