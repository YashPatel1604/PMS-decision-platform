"""Signed session cookies."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from pms_platform.config import settings

SESSION_COOKIE = "pms_session"
_SALT = "pms-auth-session-v1"


def _serializer() -> URLSafeTimedSerializer:
    secret = settings.auth_secret.strip()
    if not secret:
        raise RuntimeError("AUTH_SECRET is required when auth is enabled")
    return URLSafeTimedSerializer(secret, salt=_SALT)


def issue_session_token(user_id: int) -> str:
    """Create a signed session token for the given user."""
    return _serializer().dumps({"uid": user_id})


def read_session_user_id(token: str) -> int | None:
    """Return user_id from a signed token, or None if invalid/expired."""
    try:
        payload = _serializer().loads(
            token,
            max_age=settings.auth_session_max_age_seconds,
        )
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    uid = payload.get("uid") if isinstance(payload, dict) else None
    if isinstance(uid, int):
        return uid
    if isinstance(uid, str) and uid.isdigit():
        return int(uid)
    return None
