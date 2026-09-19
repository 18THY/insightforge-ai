"""
api/organizations.py
====================
FastAPI router for organization and membership management:
  * POST   /organizations                        Create organization (creator becomes ADMIN)
  * GET    /organizations                        List caller's organizations
  * GET    /organizations/{org_id}               Get organization details (member of org)
  * GET    /organizations/{org_id}/members       List members (member of org)
  * POST   /organizations/{org_id}/members       Add member (ADMIN only)
  * PATCH  /organizations/{org_id}/members/{uid} Update member role (ADMIN only)
  * DELETE /organizations/{org_id}/members/{uid} Remove member or leave (ADMIN or self)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_org_member, get_current_user, require_role
from app.db.models.organization import OrganizationMember
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import MessageResponse
from app.schemas.organization import (
    MemberAddRequest,
    MemberRoleUpdateRequest,
    OrganizationCreateRequest,
    OrganizationMemberResponse,
    OrganizationResponse,
)
from app.services.organization import (
    add_organization_member,
    create_organization,
    get_organization,
    list_organization_members,
    list_user_organizations,
    remove_organization_member,
    update_member_role,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization. Creator is assigned ADMIN.",
)
def create_org(
    payload: OrganizationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    return create_organization(current_user, payload, db)


@router.get(
    "",
    response_model=list[OrganizationResponse],
    summary="List all organizations the current user belongs to.",
)
def list_orgs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrganizationResponse]:
    return list_user_organizations(current_user, db)


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Get organization details for a member.",
)
def get_org(
    org_id: uuid.UUID,
    member: OrganizationMember = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    return get_organization(org_id, member, db)


@router.get(
    "/{org_id}/members",
    response_model=list[OrganizationMemberResponse],
    summary="List all members of an organization.",
)
def get_members(
    org_id: uuid.UUID,
    member: OrganizationMember = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> list[OrganizationMemberResponse]:
    return list_organization_members(org_id, db)


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a registered user to the organization. (ADMIN only)",
)
def add_member(
    org_id: uuid.UUID,
    payload: MemberAddRequest,
    actor_member: OrganizationMember = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> OrganizationMemberResponse:
    return add_organization_member(org_id, actor_member, payload, db)


@router.patch(
    "/{org_id}/members/{target_user_id}",
    response_model=OrganizationMemberResponse,
    summary="Update a member's role. (ADMIN only)",
)
def update_role(
    org_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: MemberRoleUpdateRequest,
    actor_member: OrganizationMember = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> OrganizationMemberResponse:
    return update_member_role(org_id, target_user_id, actor_member, payload, db)


@router.delete(
    "/{org_id}/members/{target_user_id}",
    response_model=MessageResponse,
    summary="Remove a member from the organization or leave. (ADMIN or self)",
)
def delete_member(
    org_id: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_member: OrganizationMember = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> MessageResponse:
    remove_organization_member(org_id, target_user_id, actor_member, db)
    return MessageResponse(message="Member removed successfully.")
