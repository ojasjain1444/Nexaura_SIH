"""
UserSession — a logged-in session token for a User (app.models.user).

A plain opaque random token stored server-side (not a JWT): with a
2-digit-PIN account system that is explicitly demo-grade (see
app.models.user's module docstring), adding a JWT library and signing key
management would be real complexity spent on a threat model this system
was never meant to resist. A random token that must match a DB row is
simple, revocable (delete the row to log a user out), and exactly as
secure as the account system it belongs to — not weaker, not falsely
stronger.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
