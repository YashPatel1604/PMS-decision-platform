"""Authentication API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_current_user, get_db, get_optional_user, require_admin
from pms_platform.auth.service import authenticate, create_user, user_public_dict
from pms_platform.auth.session import SESSION_COOKIE, issue_session_token
from pms_platform.config import settings
from pms_platform.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str
    role: str = "member"


def _set_session_cookie(response: Response, user_id: int) -> None:
    token = issue_session_token(user_id)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=settings.auth_session_max_age_seconds,
        path="/",
    )


@router.post("/login")
def login(
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Sign in with username or email + password."""
    if settings.auth_disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled (AUTH_DISABLED=1)",
        )
    user = authenticate(session, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    session.commit()
    _set_session_cookie(response, user.user_id)
    return {"user": user_public_dict(user)}


@router.post("/logout")
def logout(
    response: Response,
    _user: User | None = Depends(get_current_user),
) -> dict[str, str]:
    """Clear the session cookie."""
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(
    user: User | None = Depends(get_optional_user),
) -> dict[str, object]:
    """Return the current user, or auth_disabled / anonymous."""
    if settings.auth_disabled:
        return {"auth_disabled": True, "user": None}
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return {"auth_disabled": False, "user": user_public_dict(user)}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user_route(
    body: CreateUserRequest,
    session: Session = Depends(get_db),
    _admin: User | None = Depends(require_admin),
) -> dict[str, object]:
    """Create a user (admin only). Prefer CLI for the first admin."""
    if settings.auth_disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled (AUTH_DISABLED=1)",
        )
    try:
        user = create_user(
            session,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return {"user": user_public_dict(user)}
