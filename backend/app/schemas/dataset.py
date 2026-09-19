"""Pydantic schemas for Dataset API responses."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetResponse(BaseModel):
    """Public dataset representation.

    Note: internal `storage_path` is intentionally omitted to prevent
    server filesystem detail exposure.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    uploaded_by: UUID | None = None
    name: str
    description: str | None = None
    original_filename: str
    file_type: str
    file_size: int
    row_count: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class DatasetListResponse(BaseModel):
    """Paginated list of datasets."""

    items: list[DatasetResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
