from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_session import UserSession


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_session(self, session: UserSession) -> UserSession:
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, token: str) -> UserSession | None:
        return self.db.get(UserSession, token)

    def delete_session(self, token: str) -> None:
        session = self.get_session(token)
        if session is not None:
            self.db.delete(session)
            self.db.commit()
