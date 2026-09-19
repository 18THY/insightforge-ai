"""
services/organization.py
========================
Business logic for multi-tenant organization management and member RBAC.
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.rbac import RoleEnum, normalize_role
from app.db.models.organization import Organization, OrganizationMember
from app.db.models.user import User
from app.schemas.organization import (
    MemberAddRequest,
    MemberRoleUpdateRequest,
    OrganizationCreateRequest,
    OrganizationMemberResponse,
    OrganizationResponse,
)

logger = logging.getLogger(__name__)


def _generate_slug(name: str, db: Session) -> str:
    """Generate a clean, unique slug from an organization name."""
    base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not base_slug:
        base_slug = "org"

    slug = base_slug
    # Ensure uniqueness
    counter = 1
    while db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none() is not None:
        slug = f"{base_slug}-{counter}-{secrets.token_hex(2)}"
        counter += 1

    return slug


def create_organization(
    user: User,
    payload: OrganizationCreateRequest,
    db: Session,
) -> OrganizationResponse:
    """Create a new organization and assign the creator as ADMIN."""
    slug = _generate_slug(payload.name, db)

    org = Organization(name=payload.name, slug=slug)
    db.add(org)
    db.flush()

    # Creator receives ADMIN role
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=RoleEnum.ADMIN.value,
    )
    db.add(member)
    db.commit()
    db.refresh(org)

    logger.info("Organization '%s' created by user %s as ADMIN", org.id, user.id)
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        role=RoleEnum.ADMIN.value,
        created_at=org.created_at,
    )


def list_user_organizations(user: User, db: Session) -> list[OrganizationResponse]:
    """List all organizations the user is an active member of."""
    stmt = (
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user.id)
        .order_by(Organization.created_at.desc())
    )
    results = db.execute(stmt).all()
    return [
        OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            role=role,
            created_at=org.created_at,
        )
        for org, role in results
    ]


def get_organization(
    org_id: uuid.UUID,
    member: OrganizationMember,
    db: Session,
) -> OrganizationResponse:
    """Return organization details for an active member."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        role=member.role,
        created_at=org.created_at,
    )


def list_organization_members(
    org_id: uuid.UUID,
    db: Session,
) -> list[OrganizationMemberResponse]:
    """List all members of an organization with user details."""
    stmt = (
        select(OrganizationMember, User.email, User.full_name)
        .join(User, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == org_id)
        .order_by(OrganizationMember.created_at.asc())
    )
    rows = db.execute(stmt).all()
    return [
        OrganizationMemberResponse(
            id=m.id,
            organization_id=m.organization_id,
            user_id=m.user_id,
            email=email,
            full_name=full_name,
            role=m.role,
            created_at=m.created_at,
        )
        for m, email, full_name in rows
    ]


def add_organization_member(
    org_id: uuid.UUID,
    actor_member: OrganizationMember,
    payload: MemberAddRequest,
    db: Session,
) -> OrganizationMemberResponse:
    """Add a registered user to the organization with a designated role."""
    target_user = db.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with specified email not found.",
        )

    # Check if already a member
    existing = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user.id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organization.",
        )

    role_clean = normalize_role(payload.role)
    new_member = OrganizationMember(
        organization_id=org_id,
        user_id=target_user.id,
        role=role_clean,
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    logger.info("User %s added to org %s as %s by %s", target_user.id, org_id, role_clean, actor_member.user_id)
    return OrganizationMemberResponse(
        id=new_member.id,
        organization_id=new_member.organization_id,
        user_id=new_member.user_id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=new_member.role,
        created_at=new_member.created_at,
    )


def update_member_role(
    org_id: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_member: OrganizationMember,
    payload: MemberRoleUpdateRequest,
    db: Session,
) -> OrganizationMemberResponse:
    """Update a member's role. Protects against demoting the sole ADMIN."""
    target_member = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
        )
    ).scalar_one_or_none()

    if target_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization.",
        )

    new_role = normalize_role(payload.role)

    # If demoting an ADMIN, verify at least one other ADMIN remains
    if target_member.role == RoleEnum.ADMIN.value and new_role != RoleEnum.ADMIN.value:
        admin_count = db.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == RoleEnum.ADMIN.value,
            )
        ).scalar()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the only admin of the organization.",
            )

    target_member.role = new_role
    db.commit()
    db.refresh(target_member)

    target_user = db.get(User, target_user_id)
    logger.info("Member %s role updated to %s by %s", target_user_id, new_role, actor_member.user_id)
    return OrganizationMemberResponse(
        id=target_member.id,
        organization_id=target_member.organization_id,
        user_id=target_member.user_id,
        email=target_user.email if target_user else "",
        full_name=target_user.full_name if target_user else None,
        role=target_member.role,
        created_at=target_member.created_at,
    )


def remove_organization_member(
    org_id: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_member: OrganizationMember,
    db: Session,
) -> None:
    """Remove a member from the organization or leave. Protects against removing the sole ADMIN."""
    # Only ADMIN or the member themselves can perform removal
    if actor_member.user_id != target_user_id and actor_member.role != RoleEnum.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this action.",
        )

    target_member = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
        )
    ).scalar_one_or_none()

    if target_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization.",
        )

    # If removing an ADMIN, verify at least one other ADMIN remains
    if target_member.role == RoleEnum.ADMIN.value:
        admin_count = db.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == RoleEnum.ADMIN.value,
            )
        ).scalar()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the only admin of the organization.",
            )

    db.delete(target_member)
    db.commit()
    logger.info("Member %s removed from org %s by %s", target_user_id, org_id, actor_member.user_id)
