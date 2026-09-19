"""schemas/ml.py
=============
Pydantic schemas for Machine Learning (Phase 10): Anomaly Detection,
Time-Series Forecasting, and Statistical Provenance.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AnomalyMethod = Literal["statistical", "isolation_forest"]
AnomalySensitivity = Literal["low", "medium", "high"]
MetricAggregation = Literal["sum", "mean"]
TimeCadence = Literal["D", "W", "M"]


class AnomalyDetectRequest(BaseModel):
    """Request payload to execute anomaly detection over a metric time series."""

    date_column: str
    metric_column: str
    aggregation: MetricAggregation = "sum"
    cadence: TimeCadence = "D"
    method: AnomalyMethod = "statistical"
    sensitivity: AnomalySensitivity = "medium"
    window_size: int = Field(default=7, ge=3, le=30)
    replace_scope: Literal["all", "date_range"] = "all"
    persist: bool = True


class AnomalyItemResponse(BaseModel):
    """Individual detected anomaly point."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    metric_name: str
    detected_at: datetime
    severity: Literal["low", "medium", "high", "critical"]
    value: float | None = None
    expected_value: float | None = None
    deviation_pct: float | None = None
    description: str | None = None
    algorithm: str | None = None


class AnomalyListResponse(BaseModel):
    """List of anomalies detected for a dataset/metric with provenance metadata."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    metric_name: str
    total_anomalies: int
    anomalies: list[AnomalyItemResponse]
    provenance: dict[str, Any]


class ForecastGenerateRequest(BaseModel):
    """Request payload to generate predictive metric forecasts."""

    date_column: str
    metric_column: str
    aggregation: MetricAggregation = "sum"
    cadence: TimeCadence = "D"
    horizon_days: int = Field(default=30, ge=1, le=365)
    allow_negative: bool = False
    replace_scope: Literal["horizon_range", "all"] = "horizon_range"
    persist: bool = True


class ForecastPointResponse(BaseModel):
    """Predicted future metric value and 95% prediction interval."""

    model_config = ConfigDict(from_attributes=True)

    forecast_date: date
    predicted_value: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    model_name: str | None = None


class ForecastResponse(BaseModel):
    """Multi-horizon time-series forecasts with mathematical confidence intervals and provenance."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    metric_name: str
    horizon_days: int
    model_name: str
    generated_at: datetime
    forecasts: list[ForecastPointResponse]
    provenance: dict[str, Any]


class MLSummaryResponse(BaseModel):
    """Executive dataset summary of active anomalies and forecast outlook."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    total_anomalies_active: int
    anomalies_by_severity: dict[str, int]
    forecasts_active_count: int
    metrics_analyzed: list[str]
