"""
FastAPI dependencies shared across routes. Currently only the
current-user dependency for the demo-grade account system (see
app.models.user's module docstring).
"""

from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import AuthService

_BEARER_PREFIX = "Bearer "


def _extract_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        return None
    return authorization.removeprefix(_BEARER_PREFIX).strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Expects `Authorization: Bearer <token>`. Raises 401 if the header
    is missing, malformed, or the token does not match a live session —
    routes that require a logged-in user depend on this rather than
    re-implementing token parsing themselves."""
    token = _extract_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    user = AuthService(db).get_user_for_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def get_optional_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """Same lookup as get_current_user, but never raises: no header (or an
    invalid/expired one) simply resolves to None rather than a 401. Used
    by routes that must keep working for the existing anonymous frontend
    (which has no login UI or token storage yet — see
    app.models.conversation's module docstring) while still scoping data
    to a real user whenever a valid session IS presented, e.g. via a
    future login UI or a direct API caller. A malformed/expired token is
    deliberately treated the same as "no token" here, not as an error —
    this dependency's whole purpose is to make auth optional, so a stale
    token must degrade to anonymous rather than block the request."""
    token = _extract_token(authorization)
    if token is None:
        return None
    return AuthService(db).get_user_for_token(token)
