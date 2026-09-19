"""
core/security.py
================
Cryptographic helpers for InsightForge AI authentication.

Responsibilities
----------------
* Password hashing and verification  (bcrypt via passlib)
* JWT access-token encoding / decoding  (HS256 via python-jose)
* Refresh-token generation  (secrets.token_urlsafe)
* Refresh-token hashing  (SHA-256, stored in DB instead of raw token)

Nothing in this module touches the database or FastAPI request/response
objects — those concerns belong in services/auth.py and api/auth.py.

Security notes
--------------
* Raw refresh tokens are NEVER logged or persisted.
* Passwords are NEVER logged.
* The JWT secret key comes from Settings, which reads it from an
  environment variable; there is no hard-coded fallback in production.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return the bcrypt hash of *plain*. Never log *plain*."""
    pwd_bytes = plain.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*. Never log *plain*."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

_TOKEN_TYPE_ACCESS = "access"


def create_access_token(subject: str) -> tuple[str, datetime]:
    """Encode a short-lived JWT access token.

    Parameters
    ----------
    subject:
        The user's UUID (as a string) — placed in the ``sub`` claim.

    Returns
    -------
    token:
        The signed JWT string.
    expires_at:
        The UTC datetime at which the token expires.
    """
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expires_at,
        "type": _TOKEN_TYPE_ACCESS,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Raises
    ------
    JWTError
        If the token is invalid, expired, or not an access token.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise

    if payload.get("type") != _TOKEN_TYPE_ACCESS:
        raise JWTError("Not an access token")

    return payload


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

def generate_refresh_token() -> str:
    """Return a cryptographically random URL-safe refresh token string.

    The raw token is returned to the caller (to be sent to the client) and
    MUST NOT be stored in the database.  Only its hash should be persisted.
    """
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of *raw_token*.

    This digest is what is stored in ``auth_sessions.token_hash``.
    The raw token is NEVER stored anywhere server-side.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()
