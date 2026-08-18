"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from pms_platform.auth.service import get_user_by_id
from pms_platform.auth.session import SESSION_COOKIE, read_session_user_id
from pms_platform.config import settings
from pms_platform.db.base import get_session_factory
from pms_platform.models.user import User


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for API handlers."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_optional_user(
    request: Request,
    session: Session = Depends(get_db),
) -> User | None:
    """Return the signed-in user, or None if anonymous / auth disabled."""
    if settings.auth_disabled:
        return None
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    user_id = read_session_user_id(token)
    if user_id is None:
        return None
    user = get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    request: Request,
    session: Session = Depends(get_db),
) -> User | None:
    """Require a signed-in user when auth is enabled.

    When ``AUTH_DISABLED=1``, returns None so handlers stay usable without accounts.
    """
    if settings.auth_disabled:
        return None
    user = get_optional_user(request, session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(user: User | None = Depends(get_current_user)) -> User | None:
    """Require an admin when auth is enabled."""
    if settings.auth_disabled:
        return None
    if user is None or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user
