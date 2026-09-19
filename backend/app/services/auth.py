"""
services/auth.py
================
Authentication business logic for InsightForge AI.

This module handles:
  * User registration with duplicate-email detection
  * Login with credential verification
  * Refresh-token issuance and rotation
  * Logout / session revocation

Database access is performed through SQLAlchemy sessions passed in as
arguments — this module owns no global state and is fully unit-testable.

Security guarantees
-------------------
* Passwords are hashed before storage; the plain-text value is discarded
  immediately after hashing.
* Raw refresh tokens are hashed before the session row is written; the raw
  token is returned to the caller for delivery to the client but is never
  stored.
* Authentication errors always return the same generic message regardless
  of whether the email exists or the password is wrong, to avoid user
  enumeration.
* Passwords and raw tokens are never written to any log.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.models.auth import AuthSession
from app.db.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

# Generic credential-error message — intentionally vague to prevent
# user enumeration.
_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def _build_token_response(user: User, db: Session) -> TokenResponse:
    """Create a new access + refresh token pair and persist the session."""
    settings = get_settings()

    access_token, _ = create_access_token(str(user.id))
    raw_refresh = generate_refresh_token()
    token_hash = hash_refresh_token(raw_refresh)

    now = datetime.now(timezone.utc)
    from datetime import timedelta
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)

    session = AuthSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        revoked=False,
        revoked_at=None,
        created_at=now,
    )
    db.add(session)
    db.commit()

    # raw_refresh is returned to the caller; it is NOT logged or persisted.
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def register_user(payload: RegisterRequest, db: Session) -> UserResponse:
    """Register a new user.

    Raises
    ------
    HTTPException 409
        If the email is already registered.
    """
    existing = _get_user_by_email(db, payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    hashed = hash_password(payload.password)
    # plain-text password is no longer referenced after this point.

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hashed,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("New user registered: %s", user.id)
    return UserResponse.model_validate(user)


def login_user(payload: LoginRequest, db: Session) -> TokenResponse:
    """Verify credentials and issue tokens.

    Raises
    ------
    HTTPException 401
        If the email is not found or the password is wrong.
    """
    user = _get_user_by_email(db, payload.email)

    # Always run verify_password even if user is None, to avoid timing
    # attacks that could reveal whether an email is registered.
    dummy_hash = "$2b$12$placeholderplaceholderplaceholderplaceholderplacehold"
    password_ok = verify_password(
        payload.password,
        user.hashed_password if (user and user.hashed_password) else dummy_hash,
    )

    if user is None or not password_ok or not user.is_active:
        raise _CREDENTIALS_ERROR

    logger.info("User logged in: %s", user.id)
    return _build_token_response(user, db)


def get_current_user_from_token(token: str, db: Session) -> User:
    """Decode *token* and return the corresponding active user.

    Raises
    ------
    HTTPException 401
        If the token is invalid, expired, or the user is not found/active.
    """
    invalid_token_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise invalid_token_error
        user_uuid = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise invalid_token_error

    user = db.get(User, user_uuid)
    if user is None or not user.is_active:
        raise invalid_token_error

    return user


def refresh_tokens(payload: RefreshRequest, db: Session) -> TokenResponse:
    """Rotate a refresh token: revoke old session, issue new tokens.

    Raises
    ------
    HTTPException 401
        If the refresh token is invalid, expired, or already revoked.
    """
    token_hash = hash_refresh_token(payload.refresh_token)
    now = datetime.now(timezone.utc)

    session: AuthSession | None = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalar_one_or_none()

    if session is None:
        raise _CREDENTIALS_ERROR

    if session.revoked:
        logger.warning("Attempt to use revoked refresh token for user %s", session.user_id)
        raise _CREDENTIALS_ERROR

    if session.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Revoke the old session (token rotation)
    session.revoked = True
    session.revoked_at = now
    db.add(session)

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        db.commit()
        raise _CREDENTIALS_ERROR

    logger.info("Refresh token rotated for user %s", user.id)
    return _build_token_response(user, db)


def logout_user(payload: RefreshRequest, db: Session) -> None:
    """Revoke the session corresponding to the provided refresh token.

    Silent success if the token is already revoked or not found (idempotent).
    """
    token_hash = hash_refresh_token(payload.refresh_token)
    now = datetime.now(timezone.utc)

    session: AuthSession | None = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).scalar_one_or_none()

    if session is None or session.revoked:
        return  # already gone — nothing to do

    session.revoked = True
    session.revoked_at = now
    db.add(session)
    db.commit()
    logger.info("Session revoked for user %s", session.user_id)
