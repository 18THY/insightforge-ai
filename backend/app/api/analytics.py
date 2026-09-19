"""api/analytics.py
================
Endpoints for dataset business analytics:
  - GET  /datasets/{dataset_id}/analytics/overview
  - POST /datasets/{dataset_id}/analytics/aggregate
  - POST /datasets/{dataset_id}/analytics/time-series
  - POST /datasets/{dataset_id}/analytics/breakdown
  - POST /datasets/{dataset_id}/analytics/crosstab
  - POST /datasets/{dataset_id}/analytics/correlation
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.analytics import (
    AggregationQuery,
    AggregationResult,
    BreakdownQuery,
    BreakdownResult,
    CorrelationQuery,
    CorrelationResult,
    CrossTabQuery,
    CrossTabResult,
    DatasetOverviewResponse,
    TimeSeriesQuery,
    TimeSeriesResult,
)
from app.services import dataset as dataset_service

router = APIRouter(prefix="/datasets", tags=["analytics"])


@router.get(
    "/{dataset_id}/analytics/overview",
    response_model=DatasetOverviewResponse,
    summary="Get overall business KPIs and statistical summary for a dataset",
)
def get_dataset_analytics_overview(
    dataset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetOverviewResponse:
    """Retrieve high-level business metrics, temporal ranges, and dimension summaries.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.get_dataset_analytics_overview(
        dataset_id=dataset_id,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/analytics/aggregate",
    response_model=AggregationResult,
    summary="Execute multi-dimensional metric aggregation query",
)
def query_dataset_aggregation(
    dataset_id: uuid.UUID,
    query: AggregationQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AggregationResult:
    """Run multi-dimensional grouping and metric calculations with filtering and pagination.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.query_dataset_aggregation(
        dataset_id=dataset_id,
        query=query,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/analytics/time-series",
    response_model=TimeSeriesResult,
    summary="Execute time-series resampling and trend analysis",
)
def query_dataset_time_series(
    dataset_id: uuid.UUID,
    query: TimeSeriesQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TimeSeriesResult:
    """Resample metric across daily, weekly, monthly, quarterly, or yearly buckets.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.query_dataset_time_series(
        dataset_id=dataset_id,
        query=query,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/analytics/breakdown",
    response_model=BreakdownResult,
    summary="Compute segment breakdown and contribution percentages",
)
def query_dataset_breakdown(
    dataset_id: uuid.UUID,
    query: BreakdownQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BreakdownResult:
    """Group by dimension, rank top categories, and compute percentage share of total.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.query_dataset_breakdown(
        dataset_id=dataset_id,
        query=query,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/analytics/crosstab",
    response_model=CrossTabResult,
    summary="Compute 2D cross-tabulation matrix",
)
def query_dataset_crosstab(
    dataset_id: uuid.UUID,
    query: CrossTabQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CrossTabResult:
    """Compute 2D distribution / contingency matrix across two dimensions.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.query_dataset_crosstab(
        dataset_id=dataset_id,
        query=query,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/analytics/correlation",
    response_model=CorrelationResult,
    summary="Compute pairwise correlation matrix across numeric columns",
)
def query_dataset_correlation(
    dataset_id: uuid.UUID,
    query: CorrelationQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CorrelationResult:
    """Compute Pearson or Spearman correlation matrix with strict null handling for zero-variance.

    Requires:
      - Authenticated user
      - Active membership in the dataset's organization (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.query_dataset_correlation(
        dataset_id=dataset_id,
        query=query,
        user=current_user,
        db=db,
    )
