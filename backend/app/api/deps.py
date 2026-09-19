"""
api/deps.py
===========
FastAPI dependencies shared across routers:
  * ``get_current_user``: Extracts Bearer token, validates identity.
  * ``get_current_org_member``: Verifies organization membership (tenant isolation).
  * ``require_role``: Role-based authorization dependency factory.
  * ``require_permission``: Granular permission authorization dependency factory.
"""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import has_permission, normalize_role
from app.db.models.organization import OrganizationMember
from app.db.models.user import User
from app.db.session import get_db
from app.services.auth import get_current_user_from_token

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency -- validate Bearer token and return the active user.

    Raises HTTP 401 if token is invalid, expired, or user is inactive.
    """
    return get_current_user_from_token(credentials.credentials, db)


def get_current_org_member(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationMember:
    """FastAPI dependency -- enforce organization-level tenant isolation.

    Verifies that the authenticated user is an active member of the target
    organization. Raises HTTP 403 Forbidden if the user is not a member.
    """
    member = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of this organization.",
        )

    return member


def require_role(*allowed_roles: str) -> Callable:
    """Dependency factory that ensures the caller has one of *allowed_roles* in the target org."""
    normalized_allowed = {normalize_role(r) for r in allowed_roles}

    def _role_checker(
        member: OrganizationMember = Depends(get_current_org_member),
    ) -> OrganizationMember:
        if normalize_role(member.role) not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action.",
            )
        return member

    return _role_checker


def require_permission(permission: str) -> Callable:
    """Dependency factory that ensures the caller possesses *permission* in the target org."""

    def _perm_checker(
        member: OrganizationMember = Depends(get_current_org_member),
    ) -> OrganizationMember:
        if not has_permission(member.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action.",
            )
        return member

    return _perm_checker
