"""
Auth service — demo-grade username + 2-digit-PIN accounts (see
app.models.user and app.core.security module docstrings for why this is
explicitly not real account security).
"""

import uuid

from sqlalchemy.orm import Session

from app.core.security import generate_salt, generate_session_token, hash_pin, verify_pin
from app.models.user import User
from app.models.user_session import UserSession
from app.repositories.user_repository import UserRepository
from app.schemas.user import LoginResponse, UserResponse


class UsernameAlreadyTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.repo = UserRepository(db)

    def register(self, username: str, pin: str) -> LoginResponse:
        if self.repo.get_by_username(username) is not None:
            raise UsernameAlreadyTakenError(f"Username '{username}' is already taken")

        salt = generate_salt()
        user = User(id=str(uuid.uuid4()), username=username, pin_salt=salt, pin_hash=hash_pin(pin, salt))
        user = self.repo.create(user)
        return self._start_session(user)

    def login(self, username: str, pin: str) -> LoginResponse:
        user = self.repo.get_by_username(username)
        if user is None or not verify_pin(pin, user.pin_salt, user.pin_hash):
            raise InvalidCredentialsError("Invalid username or PIN")
        return self._start_session(user)

    def logout(self, token: str) -> None:
        self.repo.delete_session(token)

    def get_user_for_token(self, token: str) -> User | None:
        session = self.repo.get_session(token)
        if session is None:
            return None
        return self.repo.get_by_id(session.user_id)

    def _start_session(self, user: User) -> LoginResponse:
        token = generate_session_token()
        self.repo.create_session(UserSession(token=token, user_id=user.id))
        return LoginResponse(token=token, user=UserResponse(id=user.id, username=user.username))
