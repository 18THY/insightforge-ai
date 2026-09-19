"""
tests/test_auth.py
==================
Security tests for Phase 4 authentication.

These tests run against an in-memory SQLite database — no live PostgreSQL
connection is required.  SQLite is used only for testing; the production
stack remains PostgreSQL.

The tests use pytest fixtures to create a fresh database and application
for each test session, and a dedicated per-test database override to ensure
isolation.

Tests
-----
 1  Successful registration
 2  Duplicate email rejected
 3  Invalid email format rejected
 4  Weak password rejected (< 8 characters)
 5  Successful login
 6  Wrong password rejected
 7  Invalid (malformed) access token rejected on /auth/me
 8  Expired access token rejected on /auth/me
 9  /auth/me without Authorization header → 401
10  /auth/me with valid token → returns user without password_hash
11  Invalid refresh token rejected
12  Expired refresh token rejected
13  Revoked refresh token rejected
14  Refresh-token rotation (old token fails after use)
15  Logout invalidates subsequent refresh
16  password_hash never appears in any response body
17  Password is never written to logs
18  Raw refresh token is not the value in auth_sessions.token_hash
19  Unauthenticated access to a protected endpoint fails
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.auth import AuthSession
from app.db.models.user import User
from app.db.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# Test database setup (in-memory SQLite, created fresh per test session)
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite://"  # in-memory

_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
)
_TestingSessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

AUTH_TABLES = [User.__table__, AuthSession.__table__]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=AUTH_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=AUTH_TABLES)


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    """Create all tables once for the module."""
    _create_tables()
    yield
    _drop_tables()


@pytest.fixture()
def db() -> Session:
    """Yield a per-test database session that is rolled back after use."""
    connection = _engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session) -> TestClient:
    """TestClient with the DB dependency overridden to use *db*."""

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGISTER_URL = "/auth/register"
_LOGIN_URL = "/auth/login"
_ME_URL = "/auth/me"
_REFRESH_URL = "/auth/refresh"
_LOGOUT_URL = "/auth/logout"

_VALID_EMAIL = "test.user@example.com"
_VALID_PASSWORD = "SecurePass1"


def _register(client: TestClient, email: str = _VALID_EMAIL, password: str = _VALID_PASSWORD) -> dict:
    resp = client.post(_REGISTER_URL, json={"email": email, "password": password})
    return resp


def _login(client: TestClient, email: str = _VALID_EMAIL, password: str = _VALID_PASSWORD) -> dict:
    return client.post(_LOGIN_URL, json={"email": email, "password": password})


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# 1. Successful registration
# ---------------------------------------------------------------------------

def test_register_success(client: TestClient):
    resp = _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == _VALID_EMAIL
    assert "id" in body
    assert "is_active" in body
    # password_hash must never appear
    assert "password_hash" not in body
    assert "hashed_password" not in body


# ---------------------------------------------------------------------------
# 2. Duplicate email rejected
# ---------------------------------------------------------------------------

def test_register_duplicate_email(client: TestClient):
    _register(client)
    resp = _register(client)  # same email
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 3. Invalid email format rejected
# ---------------------------------------------------------------------------

def test_register_invalid_email(client: TestClient):
    resp = client.post(_REGISTER_URL, json={"email": "not-an-email", "password": "SecurePass1"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Weak password rejected
# ---------------------------------------------------------------------------

def test_register_weak_password(client: TestClient):
    resp = client.post(_REGISTER_URL, json={"email": "weak@example.com", "password": "short"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Successful login
# ---------------------------------------------------------------------------

def test_login_success(client: TestClient):
    _register(client)
    resp = _login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


# ---------------------------------------------------------------------------
# 6. Wrong password rejected
# ---------------------------------------------------------------------------

def test_login_wrong_password(client: TestClient):
    _register(client)
    resp = _login(client, password="WrongPassword!")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. Invalid (malformed) access token rejected on /auth/me
# ---------------------------------------------------------------------------

def test_me_invalid_token(client: TestClient):
    resp = client.get(_ME_URL, headers={"Authorization": "Bearer this.is.garbage"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. Expired access token rejected on /auth/me
# ---------------------------------------------------------------------------

def test_me_expired_token(client: TestClient):
    settings = get_settings()
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_token = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001", "exp": past, "type": "access"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    resp = client.get(_ME_URL, headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 9. /auth/me without Authorization header → 401/403
# ---------------------------------------------------------------------------

def test_me_no_auth_header(client: TestClient):
    resp = client.get(_ME_URL)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 10. /auth/me with valid token → returns user without password_hash
# ---------------------------------------------------------------------------

def test_me_valid_token(client: TestClient):
    _register(client)
    login_resp = _login(client)
    token = login_resp.json()["access_token"]
    resp = client.get(_ME_URL, headers=_auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == _VALID_EMAIL
    assert "hashed_password" not in body
    assert "password_hash" not in body


# ---------------------------------------------------------------------------
# 11. Invalid refresh token rejected
# ---------------------------------------------------------------------------

def test_refresh_invalid_token(client: TestClient):
    resp = client.post(_REFRESH_URL, json={"refresh_token": "completely-invalid-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 12. Expired refresh token rejected
# ---------------------------------------------------------------------------

def test_refresh_expired_token(client: TestClient, db: Session):
    _register(client)
    login_resp = _login(client)
    raw_refresh = login_resp.json()["refresh_token"]
    token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()

    # Manually expire the session in the DB
    session_row = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalar_one()
    session_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    resp = client.post(_REFRESH_URL, json={"refresh_token": raw_refresh})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 13. Revoked refresh token rejected
# ---------------------------------------------------------------------------

def test_refresh_revoked_token(client: TestClient, db: Session):
    _register(client)
    login_resp = _login(client)
    raw_refresh = login_resp.json()["refresh_token"]
    token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()

    # Manually revoke the session
    session_row = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalar_one()
    session_row.revoked = True
    session_row.revoked_at = datetime.now(timezone.utc)
    db.commit()

    resp = client.post(_REFRESH_URL, json={"refresh_token": raw_refresh})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 14. Refresh-token rotation (old token invalid after use)
# ---------------------------------------------------------------------------

def test_refresh_token_rotation(client: TestClient):
    _register(client)
    login_resp = _login(client)
    original_refresh = login_resp.json()["refresh_token"]

    # Use the refresh token once — should succeed and return a new pair
    refresh_resp = client.post(_REFRESH_URL, json={"refresh_token": original_refresh})
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert new_tokens["refresh_token"] != original_refresh

    # Using the old refresh token again must now fail
    second_resp = client.post(_REFRESH_URL, json={"refresh_token": original_refresh})
    assert second_resp.status_code == 401


# ---------------------------------------------------------------------------
# 15. Logout invalidates subsequent refresh
# ---------------------------------------------------------------------------

def test_logout_invalidates_refresh(client: TestClient):
    _register(client)
    login_resp = _login(client)
    tokens = login_resp.json()
    refresh_token = tokens["refresh_token"]

    logout_resp = client.post(_LOGOUT_URL, json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 200

    # Refresh attempt after logout must fail
    resp = client.post(_REFRESH_URL, json={"refresh_token": refresh_token})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 16. password_hash never appears in any response body
# ---------------------------------------------------------------------------

def test_password_hash_never_in_response(client: TestClient):
    reg_resp = _register(client)
    login_resp = _login(client)
    token = login_resp.json()["access_token"]
    me_resp = client.get(_ME_URL, headers=_auth_headers(token))

    for resp in (reg_resp, login_resp, me_resp):
        body_text = resp.text
        assert "hashed_password" not in body_text
        assert "password_hash" not in body_text


# ---------------------------------------------------------------------------
# 17. Password is never written to logs
# ---------------------------------------------------------------------------

def test_password_not_logged(client: TestClient, caplog):
    with caplog.at_level(logging.DEBUG):
        _register(client, email="logtest@example.com")
        _login(client, email="logtest@example.com")

    for record in caplog.records:
        assert _VALID_PASSWORD not in record.getMessage()
        assert "SecurePass1" not in record.getMessage()


# ---------------------------------------------------------------------------
# 18. Raw refresh token is not the value stored in auth_sessions.token_hash
# ---------------------------------------------------------------------------

def test_raw_refresh_token_not_stored(client: TestClient, db: Session):
    _register(client)
    login_resp = _login(client)
    raw_refresh = login_resp.json()["refresh_token"]

    # The raw token must NOT appear as token_hash
    sessions = db.execute(select(AuthSession)).scalars().all()
    for s in sessions:
        assert s.token_hash != raw_refresh, "Raw refresh token was stored — must be hashed"

    # Verify the stored value is the SHA-256 hash
    expected_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
    hashes = {s.token_hash for s in sessions}
    assert expected_hash in hashes


# ---------------------------------------------------------------------------
# 19. Unauthenticated access to protected endpoint fails
# ---------------------------------------------------------------------------

def test_protected_endpoint_requires_auth(client: TestClient):
    # /auth/me is the existing protected endpoint
    resp = client.get(_ME_URL)
    assert resp.status_code in (401, 403)
