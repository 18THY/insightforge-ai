"""schemas/cleaning.py
===================
Pydantic models for data cleaning configuration, preview, and execution reports.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CleaningConfig(BaseModel):
    """Configuration options for data cleaning pipeline."""

    remove_duplicates: bool = Field(default=True, description="Remove exact row duplicates")
    numeric_strategy: str = Field(
        default="median",
        description="Strategy for missing numeric values: 'median', 'mean', 'zero', 'none'",
    )
    categorical_strategy: str = Field(
        default="mode",
        description="Strategy for missing categorical values: 'mode', 'unknown', 'none'",
    )
    normalize_column_names: bool = Field(
        default=True,
        description="Convert column headers to standardized snake_case",
    )
    normalize_categories: bool = Field(
        default=True,
        description="Normalize casing and whitespace across categorical values",
    )
    outlier_handling: str = Field(
        default="detect_only",
        description="Outlier action: 'detect_only' (classify/report) or 'cap' (winsorize bounds)",
    )


class DatatypeChange(BaseModel):
    """Record of a datatype conversion attempted or applied on a column."""

    column: str
    from_type: str
    to_type: str
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)


class OutlierSummary(BaseModel):
    """Summary of outliers detected in a numeric column."""

    column: str
    count: int = Field(ge=0)
    method: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    sample_outliers: list[float] = Field(default_factory=list)


class ReferentialSummary(BaseModel):
    """Referential integrity audit for an identifier column."""

    column: str
    missing_count: int = Field(ge=0)
    invalid_reference_count: int = Field(ge=0)
    issues: list[str] = Field(default_factory=list)


class CleaningPreviewResponse(BaseModel):
    """Non-destructive dry run preview of proposed cleaning operations."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    rows_before: int = Field(ge=0)
    rows_after_estimate: int = Field(ge=0)
    duplicates_detected: int = Field(ge=0)
    duplicates_percentage: float = Field(ge=0.0, le=100.0)
    missing_values_detected: dict[str, int] = Field(default_factory=dict)
    columns_to_modify: list[str] = Field(default_factory=list)
    datatype_changes: list[DatatypeChange] = Field(default_factory=list)
    categorical_normalizations: dict[str, dict[str, str]] = Field(default_factory=dict)
    invalid_values: dict[str, int] = Field(default_factory=dict)
    outlier_summary: dict[str, OutlierSummary] = Field(default_factory=dict)
    referential_issues: dict[str, ReferentialSummary] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)


class CleaningReportResponse(BaseModel):
    """Structured report of executed cleaning operations."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    rows_before: int = Field(ge=0)
    rows_after: int = Field(ge=0)
    duplicates_removed: int = Field(ge=0)
    missing_values_handled: dict[str, int] = Field(default_factory=dict)
    datatype_changes: list[DatatypeChange] = Field(default_factory=list)
    normalized_categories: dict[str, dict[str, str]] = Field(default_factory=dict)
    invalid_values_found: dict[str, int] = Field(default_factory=dict)
    outliers_detected: dict[str, OutlierSummary] = Field(default_factory=dict)
    referential_issues: dict[str, ReferentialSummary] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    processing_time_ms: float = Field(ge=0.0)
    output_location: str
