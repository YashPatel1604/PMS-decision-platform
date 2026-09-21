"""User account service (invite-only create + authenticate)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.auth.passwords import hash_password, verify_password
from pms_platform.models.user import User

VALID_ROLES = frozenset({"admin", "member", "client"})
_LOCAL_USERS = (
    ("julesh@local", "Julesh", "client", "julesh@2602"),
    ("samir@local", "Samir", "admin", "samir@1510"),
    ("yash@local", "Yash", "member", "yash@1604"),
)


def login_identifier_to_email(identifier: str) -> str:
    text = identifier.strip().lower()
    if not text:
        return text
    return text if "@" in text else f"{text}@local"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    role: str = "member",
) -> User:
    """Create an invite-only user. Raises ValueError on validation errors."""
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        raise ValueError("Valid email is required")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters")
    name = display_name.strip()
    if not name:
        raise ValueError("Display name is required")
    role_norm = role.strip().lower()
    if role_norm not in VALID_ROLES:
        raise ValueError(f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
    if get_user_by_email(session, normalized) is not None:
        raise ValueError(f"User already exists: {normalized}")

    user = User(
        email=normalized,
        password_hash=hash_password(password),
        display_name=name,
        role=role_norm,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    """Return the active user if credentials match."""
    user = get_user_by_email(session, login_identifier_to_email(email))
    if user is None or not user.is_active:
        return None
    if not verify_password(user.password_hash, password):
        return None
    user.last_login_at = datetime.now(UTC)
    session.flush()
    return user


def user_public_dict(user: User) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def count_users(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(User)) or 0)


def ensure_builtin_users(session: Session) -> None:
    """Create Julesh / Samir / Yash if missing; keep seed passwords and roles."""
    for email, name, role, password in _LOCAL_USERS:
        existing = get_user_by_email(session, email)
        if existing is None:
            create_user(
                session,
                email=email,
                password=password,
                display_name=name,
                role=role,
            )
            continue
        if existing.role != role:
            existing.role = role
        if not verify_password(existing.password_hash, password):
            existing.password_hash = hash_password(password)
