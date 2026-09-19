"""schemas/rca.py
================
Pydantic request and response schemas for Root-Cause Analysis (RCA) Engine (Phase 11).

Provides strongly-typed contracts for:
- Waterfall dimension decomposition
- Multi-dimensional driver intersections
- Exact statistical z-scores and variance handling
- Secondary metric co-movement and elasticity
- Full pre-truncation reconciliation metadata
- Traceable evidence bundles and deterministic template narratives
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class RCAAnalyzeRequest(BaseModel):
    """Request payload to execute Root-Cause Analysis on a dataset."""

    # Target specification: either anomaly_id OR explicit metric + dates
    anomaly_id: UUID | None = None
    metric_column: str | None = None
    date_column: str | None = None
    aggregation: Literal["sum", "avg", "count"] = "sum"

    # Event & Baseline Windows (inclusive calendar dates)
    event_start: date | None = None
    event_end: date | None = None
    baseline_start: date | None = None
    baseline_end: date | None = None
    baseline_mode: Literal["prior_period", "custom"] = "prior_period"

    # Dimensions & Secondary Metrics
    dimension_columns: list[str] | None = None  # None = auto-detect categorical columns
    secondary_metrics: list[str] | None = None  # None = auto-detect other numeric columns
    max_dimensions: int = Field(default=3, ge=1, le=3)
    top_k_drivers: int = Field(default=5, ge=1, le=20)
    min_contribution_pct: float = Field(default=1.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_target_specification(self) -> RCAAnalyzeRequest:
        if self.anomaly_id is None:
            if not self.metric_column:
                raise ValueError("Either 'anomaly_id' or 'metric_column' must be provided.")
            if not self.date_column:
                raise ValueError("When 'anomaly_id' is not provided, 'date_column' must be specified.")
            if not self.event_start or not self.event_end:
                raise ValueError("When 'anomaly_id' is not provided, 'event_start' and 'event_end' must be specified.")
            if self.event_start > self.event_end:
                raise ValueError(f"'event_start' ({self.event_start}) cannot be after 'event_end' ({self.event_end}).")
        if self.baseline_start and self.baseline_end and self.baseline_start > self.baseline_end:
            raise ValueError(f"'baseline_start' ({self.baseline_start}) cannot be after 'baseline_end' ({self.baseline_end}).")
        return self


class StatisticalScore(BaseModel):
    """Statistical significance details for a segment driver shift."""

    z_score: float | None = None
    baseline_mean: float
    baseline_std: float | None = None
    is_significant: bool
    variance_note: str | None = None


class SegmentDriver(BaseModel):
    """An individual segment driver contributing to a metric change."""

    dataset_id: UUID
    anomaly_id: UUID | None = None
    dimension: str
    segment_value: str
    baseline_value: float
    event_value: float
    delta: float
    contribution_pct: float | None = None
    growth_pct: float
    statistical_score: StatisticalScore
    event_window: dict[str, str]
    baseline_window: dict[str, str]
    metric_name: str


class DimensionDriverBreakdown(BaseModel):
    """Decomposition of a metric delta across segments of a single dimension or intersection."""

    dimension: str
    total_segments: int
    top_positive_drivers: list[SegmentDriver]
    top_negative_drivers: list[SegmentDriver]
    coverage_pct: float


class SecondaryMetricImpact(BaseModel):
    """Co-movement, percentage shift, and elasticity for a secondary metric."""

    metric_name: str
    baseline_value: float
    event_value: float
    delta: float
    growth_pct: float
    direction: Literal["concordant", "divergent", "neutral"]
    elasticity: float | None = None
    elasticity_status: str = "ok"


class WaterfallReconciliation(BaseModel):
    """Reconciliation metadata confirming complete pre-truncation driver delta equality."""

    sum_segment_deltas_full: float
    total_metric_delta: float
    discrepancy: float
    is_reconciled: bool
    truncated_display_count: int
    total_segments_count: int
    reconciliation_warning: str | None = None


class RCAResponse(BaseModel):
    """Complete, evidence-grounded response for Root-Cause Analysis."""

    dataset_id: UUID
    anomaly_id: UUID | None = None
    metric_name: str
    aggregation: str
    event_window: dict[str, Any]
    baseline_window: dict[str, Any]
    total_delta: float
    percentage_change: float
    contribution_status: str = "ok"
    contribution_explanation: str | None = None
    reconciliation: WaterfallReconciliation
    primary_drivers: list[SegmentDriver]
    dimension_breakdowns: list[DimensionDriverBreakdown]
    secondary_metrics: list[SecondaryMetricImpact]
    narrative_summary: str
    provenance: dict[str, Any]
