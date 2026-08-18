"""Unit tests for invite-only auth service."""

from pms_platform.auth.passwords import hash_password, verify_password
from pms_platform.auth.service import authenticate, create_user, get_user_by_email
from pms_platform.auth.session import issue_session_token, read_session_user_id
from pms_platform.config import settings


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert verify_password(hashed, "correct-horse-battery")
    assert not verify_password(hashed, "wrong")


def test_create_and_authenticate(session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_secret", "unit-test-auth-secret-key-32b")
    user = create_user(
        session,
        email="Admin@Firm.com",
        password="password123",
        display_name="Admin",
        role="admin",
    )
    session.commit()
    assert user.email == "admin@firm.com"
    assert get_user_by_email(session, "admin@firm.com") is not None

    ok = authenticate(session, "admin@firm.com", "password123")
    assert ok is not None
    assert ok.user_id == user.user_id
    assert ok.last_login_at is not None

    assert authenticate(session, "admin@firm.com", "nope") is None


def test_duplicate_email_rejected(session) -> None:
    create_user(
        session,
        email="a@firm.com",
        password="password123",
        display_name="A",
    )
    session.flush()
    try:
        create_user(
            session,
            email="a@firm.com",
            password="password123",
            display_name="B",
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "already exists" in str(exc)


def test_session_token_roundtrip(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_secret", "unit-test-auth-secret-key-32b")
    token = issue_session_token(42)
    assert read_session_user_id(token) == 42
    assert read_session_user_id("not-a-token") is None
