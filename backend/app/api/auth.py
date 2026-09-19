"""
api/auth.py
===========
Authentication router — five endpoints:

    POST  /auth/register   Register a new user
    POST  /auth/login      Issue access + refresh tokens
    GET   /auth/me         Return the authenticated user
    POST  /auth/refresh    Rotate refresh token, issue new tokens
    POST  /auth/logout     Revoke the current refresh-token session
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account.",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    return register_user(payload, db)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive access + refresh tokens.",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login_user(payload, db)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the currently authenticated user.",
)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate the refresh token and issue a new token pair.",
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return refresh_tokens(payload, db)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke the current refresh-token session.",
)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    logout_user(payload, db)
    return MessageResponse(message="Successfully logged out.")
