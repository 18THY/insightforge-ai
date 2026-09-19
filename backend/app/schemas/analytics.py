"""schemas/analytics.py
====================
Pydantic models for analytics queries, time-series, breakdowns, cross-tabulations,
and dataset overview metrics.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FilterOperator = Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "between"]
MetricAggregation = Literal["sum", "mean", "median", "count", "min", "max", "std"]
TimeGranularity = Literal["day", "week", "month", "quarter", "year"]


class FilterClause(BaseModel):
    """Row-level filter condition."""

    column: str
    operator: FilterOperator
    value: Any


class MetricSpec(BaseModel):
    """Specification of a metric calculation."""

    column: str
    aggregation: MetricAggregation
    alias: str | None = None


class AggregationQuery(BaseModel):
    """Query parameters for multi-dimensional aggregation."""

    metrics: list[MetricSpec] = Field(min_length=1, max_length=20)
    dimensions: list[str] = Field(default_factory=list, max_length=10)
    filters: list[FilterClause] = Field(default_factory=list, max_length=20)
    order_by: str | None = None
    order_desc: bool = True
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0, le=50000)


class AggregationResult(BaseModel):
    """Result of an aggregation query."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    is_cleaned: bool
    total_rows: int
    data: list[dict[str, Any]]


class TimeSeriesQuery(BaseModel):
    """Query parameters for temporal time-series trend analysis."""

    date_column: str
    metric_column: str
    aggregation: MetricAggregation = "sum"
    granularity: TimeGranularity = "month"
    rolling_window: int | None = Field(default=None, ge=2, le=365)
    include_cumulative: bool = False
    include_growth: bool = False
    filters: list[FilterClause] = Field(default_factory=list, max_length=20)


class TimeSeriesPoint(BaseModel):
    """Individual data point in a time series."""

    timestamp: str
    value: float
    rolling_average: float | None = None
    cumulative_value: float | None = None
    growth_rate_pct: float | None = None


class TimeSeriesResult(BaseModel):
    """Result of a time-series query."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    is_cleaned: bool
    date_column: str
    metric_column: str
    granularity: str
    series: list[TimeSeriesPoint]


class BreakdownQuery(BaseModel):
    """Query parameters for single-dimension segment breakdown."""

    dimension: str
    metric_column: str | None = None
    aggregation: MetricAggregation = "count"
    top_n: int = Field(default=10, ge=1, le=100)
    include_other: bool = True
    filters: list[FilterClause] = Field(default_factory=list, max_length=20)


class BreakdownItem(BaseModel):
    """Individual segment in a breakdown."""

    category: str
    value: float
    percentage_of_total: float


class BreakdownResult(BaseModel):
    """Result of a breakdown query."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    is_cleaned: bool
    dimension: str
    metric: str
    total_value: float
    items: list[BreakdownItem]


class CrossTabQuery(BaseModel):
    """Query parameters for 2D cross-tabulation matrix."""

    row_dimension: str
    column_dimension: str
    metric_column: str | None = None
    aggregation: MetricAggregation = "count"
    filters: list[FilterClause] = Field(default_factory=list, max_length=20)


class CrossTabResult(BaseModel):
    """Result of a 2D cross-tabulation."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    is_cleaned: bool
    row_dimension: str
    column_dimension: str
    row_values: list[str]
    column_values: list[str]
    matrix: list[list[float]]


class CorrelationQuery(BaseModel):
    """Query parameters for numeric correlation matrix."""

    columns: list[str] = Field(default_factory=list, max_length=50)
    method: Literal["pearson", "spearman"] = "pearson"


class CorrelationResult(BaseModel):
    """Result of a correlation matrix query."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    is_cleaned: bool
    columns: list[str]
    correlation_matrix: dict[str, dict[str, float | None]]


class DatasetOverviewResponse(BaseModel):
    """Overall dataset business KPIs and statistical summary."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    is_cleaned: bool
    row_count: int
    column_count: int
    numeric_kpis: dict[str, dict[str, float]]
    temporal_kpi: dict[str, Any] | None = None
    top_dimension_kpis: dict[str, list[dict[str, Any]]]
