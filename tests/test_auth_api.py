"""API auth gate tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pms_platform.api.main import app
from pms_platform.auth.service import create_user
from pms_platform.config import settings
from pms_platform.db.base import Base


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "auth_secret", "api-test-auth-secret-key-32bytes!")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)


@pytest.fixture
def auth_db(monkeypatch, auth_enabled):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(
        "pms_platform.api.auth_middleware.get_session_factory",
        lambda: factory,
    )
    monkeypatch.setattr(
        "pms_platform.api.deps.get_session_factory",
        lambda: factory,
    )

    session = factory()
    create_user(
        session,
        email="admin@firm.com",
        password="password123",
        display_name="Admin",
        role="admin",
    )
    create_user(
        session,
        email="member@firm.com",
        password="password123",
        display_name="Member",
        role="member",
    )
    create_user(
        session,
        email="julesh@local",
        password="1234",
        display_name="Julesh",
        role="client",
    )
    session.commit()
    session.close()
    return factory


def test_health_public_when_auth_on(auth_enabled) -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_protected_route_rejects_anonymous(auth_enabled) -> None:
    client = TestClient(app)
    response = client.get("/dashboard/summary")
    assert response.status_code == 401


def test_login_and_access(auth_db) -> None:
    client = TestClient(app)
    bad = client.post(
        "/auth/login",
        json={"email": "admin@firm.com", "password": "wrong"},
    )
    assert bad.status_code == 401

    login = client.post(
        "/auth/login",
        json={"email": "admin@firm.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "admin@firm.com"
    assert "pms_session" in login.cookies

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["display_name"] == "Admin"

    # Dashboard still needs real data tables; auth gate is what we verify here.
    # Watchlists list may 500 without postgres schema specifics — use /auth/me + logout.
    protected = client.get("/watchlists/settings")
    # May be 200 or 500 depending on DB content, but must not be 401
    assert protected.status_code != 401

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_member_cannot_create_user(auth_db) -> None:
    client = TestClient(app)
    client.post(
        "/auth/login",
        json={"email": "member@firm.com", "password": "password123"},
    )
    response = client.post(
        "/auth/users",
        json={
            "email": "new@firm.com",
            "password": "password123",
            "display_name": "New",
            "role": "member",
        },
    )
    assert response.status_code == 403


def test_admin_can_create_user(auth_db) -> None:
    client = TestClient(app)
    client.post(
        "/auth/login",
        json={"email": "admin@firm.com", "password": "password123"},
    )
    response = client.post(
        "/auth/users",
        json={
            "email": "new@firm.com",
            "password": "password123",
            "display_name": "New Hire",
            "role": "member",
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "new@firm.com"


def test_username_login_and_client_role_scope(auth_db) -> None:
    client = TestClient(app)
    login = client.post("/auth/login", json={"email": "julesh", "password": "1234"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "client"

    charts = client.get("/strategy/charts/dashboard")
    assert charts.status_code != 401
    assert charts.status_code != 403

    insider = client.get("/market-data/insider-trading/today")
    assert insider.status_code != 401
    assert insider.status_code != 403

    blocked = client.get("/dashboard/summary")
    assert blocked.status_code == 403

    admin = TestClient(app)
    ok = admin.post(
        "/auth/login",
        json={"email": "admin@firm.com", "password": "password123"},
    )
    assert ok.status_code == 200
    summary = admin.get("/dashboard/summary")
    assert summary.status_code != 401
    assert summary.status_code != 403


def test_auth_disabled_allows_anonymous(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_disabled", True)
    client = TestClient(app)
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["auth_disabled"] is True
