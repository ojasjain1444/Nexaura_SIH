"""
User — a real, per-user account, replacing the fixed
app.models.user_preference.LOCAL_DEFAULT_USER_KEY placeholder this project
used before any account concept existed.

This is explicitly a demo-grade account system, not production security:
the PIN is a short numeric code (2 digits — 100 possible values) by
deliberate product decision, meant to distinguish users on a local/demo
deployment, not to withstand a real attacker. pin_hash is still a hash
(never plaintext) because there's no reason to store a password in
cleartext even when it's low-stakes — hashing costs nothing and is simply
good practice, not a claim that this hash makes the PIN's small space any
harder to brute-force. See app/core/security.py for the explicit
"NOT FOR REAL SECURITY" framing carried through the hashing function
itself.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    pin_salt: Mapped[str] = mapped_column(String(32), nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
