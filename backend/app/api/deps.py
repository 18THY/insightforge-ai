"""
api/deps.py
===========
FastAPI dependencies shared across routers.

``get_current_user`` is the standard dependency for any endpoint that
requires a valid, active user.  It extracts the Bearer token from the
Authorization header, validates it, and returns the corresponding User row.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.db.session import get_db
from app.services.auth import get_current_user_from_token

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency — validate Bearer token and return the active user.

    Raises HTTP 401 if the token is missing, malformed, expired, or if the
    corresponding user does not exist or is inactive.
    """
    return get_current_user_from_token(credentials.credentials, db)
