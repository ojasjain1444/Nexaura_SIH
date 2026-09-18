"""
UserPreference — persists the Settings page's language selection.

Only `language` is modeled: it is the only setting that actually exists in
the frontend today (src/pages/SettingsPage.tsx / src/hooks/useLanguage.ts).
Fields like theme/voice_enabled/response_preferences are explicitly NOT
added here per this phase's instruction to model only settings that
correspond to real existing frontend UI — inventing columns for
not-yet-built settings would be exactly the over-engineering this phase is
told to avoid.

No authentication exists yet, so there is one preference row per local
"anonymous" identity rather than per authenticated user. `user_key` is a
fixed, well-known string ("local-default-user") until real accounts exist
(see docs/IMPLEMENTATION_ROADMAP.md, Phase 11) — the column is named for
what it will become, not left unnamed for lack of an owner concept.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

LOCAL_DEFAULT_USER_KEY = "local-default-user"


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_key", name="uq_user_preferences_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=LOCAL_DEFAULT_USER_KEY)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
