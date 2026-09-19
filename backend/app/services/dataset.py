"""services/dataset.py
===================
Dataset ingestion, retrieval, listing, and deletion service.

Enforces organization-level tenant isolation, RBAC role permissions,
content validation, safe storage handling, and database metadata updates.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.rbac import can_mutate_data
from app.core.storage import (
    delete_stored_file,
    sanitize_filename,
    save_upload_file,
    validate_file_content,
)
from app.db.models.dataset import Dataset
from app.db.models.organization import OrganizationMember
from app.db.models.user import User


def get_user_org_membership(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> OrganizationMember:
    """Verify that a user is an active member of an organization.

    Raises HTTP 403 Forbidden if not a member.
    """
    member = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    ).scalar_one_or_none()

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of this organization.",
        )
    return member


async def upload_dataset(
    *,
    user: User,
    organization_id: uuid.UUID,
    file: UploadFile,
    name: str,
    description: str | None = None,
    db: Session,
) -> Dataset:
    """Validate, store, and record a new dataset upload.

    Enforces:
      - Active membership in the target organization.
      - RBAC permission: only ADMIN and ANALYST can upload datasets.
      - Unique dataset name within the organization.
      - Content safety & format validation (CSV / XLSX).
      - Dedicated filesystem storage outside source code.
    """
    # 1. Authorization & Membership
    member = get_user_org_membership(organization_id, user.id, db)
    if not can_mutate_data(member.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only ADMIN and ANALYST can upload datasets.",
        )

    # 2. Name validation and uniqueness
    name = (name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset name cannot be empty.",
        )

    existing = db.execute(
        select(Dataset).where(
            Dataset.organization_id == organization_id,
            Dataset.name == name,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A dataset named '{name}' already exists in this organization.",
        )

    # 3. Read and validate file content
    raw_filename = file.filename or "upload"
    safe_filename = sanitize_filename(raw_filename)

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {e}",
        ) from e

    try:
        file_type, file_size, row_count = validate_file_content(
            content,
            filename=safe_filename,
            content_type=file.content_type,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # 4. Save to dedicated storage
    dataset_id = uuid.uuid4()
    try:
        storage_path = save_upload_file(content, organization_id, dataset_id, file_type)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save upload to disk: {e}",
        ) from e

    # 5. Persist metadata to database
    dataset = Dataset(
        id=dataset_id,
        organization_id=organization_id,
        created_by=user.id,
        name=name,
        description=description.strip() if description else None,
        source_filename=safe_filename,
        storage_path=storage_path,
        file_type=file_type,
        file_size=file_size,
        row_count=row_count,
        status="uploaded",
    )

    try:
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    except Exception as e:
        db.rollback()
        # Clean up physical file on database failure
        delete_stored_file(storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record dataset metadata.",
        ) from e

    return dataset


def list_datasets(
    *,
    organization_id: uuid.UUID,
    user: User,
    limit: int = 50,
    offset: int = 0,
    db: Session,
) -> tuple[Sequence[Dataset], int]:
    """List datasets belonging strictly to the specified organization.

    Enforces:
      - Authenticated user must belong to that organization.
      - Never leaks datasets across tenant boundaries.
      - Paginated results.
    """
    # Verify membership
    get_user_org_membership(organization_id, user.id, db)

    # Count total
    total = db.execute(
        select(func.count(Dataset.id)).where(Dataset.organization_id == organization_id)
    ).scalar_one()

    # Query items
    query = (
        select(Dataset)
        .where(Dataset.organization_id == organization_id)
        .order_by(Dataset.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = db.execute(query).scalars().all()

    return items, total


def get_dataset(
    *,
    dataset_id: uuid.UUID,
    user: User,
    db: Session,
) -> Dataset:
    """Retrieve dataset metadata by ID.

    Enforces:
      - 404 if dataset does not exist.
      - 403 if user is not a member of the dataset's organization.
    """
    dataset = db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    ).scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    # Organization membership check
    get_user_org_membership(dataset.organization_id, user.id, db)

    return dataset


def delete_dataset(
    *,
    dataset_id: uuid.UUID,
    user: User,
    db: Session,
) -> None:
    """Delete a dataset and its stored file.

    Enforces:
      - 404 if dataset does not exist.
      - 403 if caller is not an active member.
      - 403 if caller lacks ADMIN or ANALYST role.
      - Removes physical storage file safely.
    """
    dataset = db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    ).scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    member = get_user_org_membership(dataset.organization_id, user.id, db)
    if not can_mutate_data(member.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only ADMIN and ANALYST can delete datasets.",
        )

    storage_path = dataset.storage_path

    # Delete database record
    db.delete(dataset)
    db.commit()

    # Clean up physical file
    delete_stored_file(storage_path)
