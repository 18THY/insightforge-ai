"""api/datasets.py
===============
Dataset management endpoints: upload, list, detail, delete.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.cleaning import (
    CleaningConfig,
    CleaningPreviewResponse,
    CleaningReportResponse,
)
from app.schemas.dataset import DatasetListResponse, DatasetResponse
from app.schemas.profile import DatasetProfileResponse
from app.services import dataset as dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post(
    "/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new CSV or XLSX dataset",
)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV or XLSX file to upload"),
    organization_id: uuid.UUID = Form(..., description="Target organization ID"),
    name: str = Form(..., description="Human-readable dataset name"),
    description: str | None = Form(None, description="Optional dataset description"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetResponse:
    """Upload a dataset file (CSV or XLSX).

    Requires:
      - Authenticated user
      - Membership in the target organization
      - Role of ADMIN or ANALYST in that organization
    """
    dataset = await dataset_service.upload_dataset(
        user=current_user,
        organization_id=organization_id,
        file=file,
        name=name,
        description=description,
        db=db,
    )
    return DatasetResponse.model_validate(dataset)


@router.get(
    "",
    response_model=DatasetListResponse,
    summary="List datasets for an organization",
)
def list_datasets(
    organization_id: uuid.UUID = Query(..., description="Organization ID to list datasets for"),
    limit: int = Query(50, ge=1, le=100, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetListResponse:
    """List datasets belonging to a specific organization.

    Requires:
      - Authenticated user
      - Active membership in the target organization
    """
    items, total = dataset_service.list_datasets(
        organization_id=organization_id,
        user=current_user,
        limit=limit,
        offset=offset,
        db=db,
    )
    return DatasetListResponse(
        items=[DatasetResponse.model_validate(ds) for ds in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    summary="Get dataset metadata by ID",
)
def get_dataset(
    dataset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetResponse:
    """Retrieve metadata for a single dataset.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization
    """
    dataset = dataset_service.get_dataset(
        dataset_id=dataset_id,
        user=current_user,
        db=db,
    )
    return DatasetResponse.model_validate(dataset)


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a dataset",
)
def delete_dataset(
    dataset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a dataset and its stored file.

    Requires:
      - Authenticated user
      - Role of ADMIN or ANALYST in the dataset's organization
    """
    dataset_service.delete_dataset(
        dataset_id=dataset_id,
        user=current_user,
        db=db,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{dataset_id}/profile",
    response_model=DatasetProfileResponse,
    summary="Get dataset schema and data quality profile",
)
def get_dataset_profile(
    dataset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetProfileResponse:
    """Retrieve comprehensive profile, statistics, and quality score for a dataset.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.get_dataset_profile(
        dataset_id=dataset_id,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/clean/preview",
    response_model=CleaningPreviewResponse,
    summary="Preview data-cleaning transformations non-destructively",
)
def preview_dataset_cleaning(
    dataset_id: uuid.UUID,
    config: CleaningConfig | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CleaningPreviewResponse:
    """Dry-run preview of dataset cleaning transformations.

    Does NOT modify the raw stored source file.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.preview_dataset_cleaning(
        dataset_id=dataset_id,
        config=config,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/clean/apply",
    response_model=CleaningReportResponse,
    summary="Apply data cleaning, persist to processed directory, and update metadata",
)
def apply_dataset_cleaning(
    dataset_id: uuid.UUID,
    config: CleaningConfig | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CleaningReportResponse:
    """Apply cleaning transformations and save processed dataset.

    Preserves the raw uploaded source file untouched and writes the cleaned
    dataset to data/processed/{org_id}/{dataset_id}.csv.

    Requires:
      - Authenticated user
      - Role of ADMIN or ANALYST in the dataset's organization
    """
    return dataset_service.apply_dataset_cleaning(
        dataset_id=dataset_id,
        config=config,
        user=current_user,
        db=db,
    )
