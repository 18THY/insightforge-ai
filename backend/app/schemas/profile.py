"""schemas/profile.py
==================
Pydantic response models for dataset profiling results and data quality scores.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryFrequency(BaseModel):
    """Frequency count and percentage for a single categorical value."""

    value: str
    count: int = Field(ge=0)
    percentage: float = Field(ge=0.0, le=100.0)


class CategoricalStats(BaseModel):
    """Categorical column analysis."""

    num_categories: int = Field(ge=0)
    top_categories: list[CategoryFrequency] = Field(default_factory=list)


class NumericStats(BaseModel):
    """Numeric distribution statistics."""

    min: float
    max: float
    mean: float
    median: float
    std_dev: float | None = None
    percentiles: dict[str, float] = Field(default_factory=dict)


class DatetimeStats(BaseModel):
    """Datetime column analysis."""

    min_date: str | None = None
    max_date: str | None = None
    date_range_days: int | None = None
    invalid_date_count: int = Field(default=0, ge=0)


class ColumnProfile(BaseModel):
    """Detailed profile of an individual column."""

    name: str
    inferred_datatype: str
    classification: str
    null_count: int = Field(ge=0)
    null_percentage: float = Field(ge=0.0, le=100.0)
    unique_count: int = Field(ge=0)
    unique_percentage: float = Field(ge=0.0, le=100.0)
    sample_values: list[Any] = Field(default_factory=list)

    # Type-specific deep dive metrics
    numeric_stats: NumericStats | None = None
    categorical_stats: CategoricalStats | None = None
    datetime_stats: DatetimeStats | None = None


class DataQualityComponents(BaseModel):
    """The 5 individual sub-scores (0-100) comprising the overall quality score."""

    completeness: float = Field(ge=0.0, le=100.0, description="Completeness sub-score (weight: 30%)")
    uniqueness: float = Field(ge=0.0, le=100.0, description="Uniqueness sub-score (weight: 25%)")
    type_consistency: float = Field(ge=0.0, le=100.0, description="Type consistency sub-score (weight: 20%)")
    date_validity: float = Field(ge=0.0, le=100.0, description="Date validity sub-score (weight: 15%)")
    reasonableness: float = Field(ge=0.0, le=100.0, description="Value reasonableness sub-score (weight: 10%)")


class DataQualityMetrics(BaseModel):
    """Underlying counts and measurements used in data quality scoring."""

    total_cells: int = Field(ge=0)
    missing_cells: int = Field(ge=0)
    missing_cells_pct: float = Field(ge=0.0, le=100.0)
    duplicate_rows: int = Field(ge=0)
    duplicate_rows_pct: float = Field(ge=0.0, le=100.0)
    inconsistent_type_cells: int = Field(ge=0)
    invalid_date_count: int = Field(ge=0)
    suspicious_value_count: int = Field(ge=0)


class DataQualityScore(BaseModel):
    """Overall transparent data quality score and its explainability components."""

    score: float = Field(ge=0.0, le=100.0)
    grade: str
    formula: str
    components: DataQualityComponents
    metrics: DataQualityMetrics


class DatasetProfileResponse(BaseModel):
    """Comprehensive dataset profile response."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    column_names: list[str] = Field(default_factory=list)
    memory_size_bytes: int = Field(ge=0)
    duplicate_row_count: int = Field(ge=0)
    duplicate_row_percentage: float = Field(ge=0.0, le=100.0)
    total_missing_cells: int = Field(ge=0)
    missing_cells_percentage: float = Field(ge=0.0, le=100.0)
    columns: list[ColumnProfile] = Field(default_factory=list)
    quality_score: DataQualityScore
