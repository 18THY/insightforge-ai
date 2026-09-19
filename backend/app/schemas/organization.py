"""
schemas/organization.py
=======================
Pydantic schemas for multi-tenant organization management and member RBAC.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.rbac import normalize_role


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("Organization name must be at least 2 characters.")
        return s


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberAddRequest(BaseModel):
    email: EmailStr
    role: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        return normalize_role(v)


class MemberRoleUpdateRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        return normalize_role(v)


class OrganizationMemberResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}
