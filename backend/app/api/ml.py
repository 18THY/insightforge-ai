"""api/ml.py
=========
FastAPI routes for Machine Learning (Phase 10): Anomaly Detection and Time-Series Forecasting.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.ml import (
    AnomalyDetectRequest,
    AnomalyListResponse,
    ForecastGenerateRequest,
    ForecastResponse,
    MLSummaryResponse,
)
from app.services import dataset as dataset_service

router = APIRouter(prefix="/datasets", tags=["machine-learning"])


@router.post(
    "/{dataset_id}/ml/anomalies/detect",
    response_model=AnomalyListResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute deterministic anomaly detection",
)
def detect_dataset_anomalies(
    dataset_id: uuid.UUID,
    req: AnomalyDetectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnomalyListResponse:
    """Execute rolling Z-score or IsolationForest anomaly detection over a metric.

    Permissions:
      - Authenticated user
      - ADMIN or ANALYST in the owning organization (MANAGER and VIEWER receive 403)
    """
    return dataset_service.run_dataset_anomaly_detection(
        dataset_id=dataset_id,
        req=req,
        user=current_user,
        db=db,
    )


@router.get(
    "/{dataset_id}/ml/anomalies",
    response_model=AnomalyListResponse,
    summary="List persisted anomalies for a dataset",
)
def list_dataset_anomalies(
    dataset_id: uuid.UUID,
    metric_name: str | None = Query(default=None, description="Filter by metric name"),
    severity: str | None = Query(default=None, description="Filter by severity (low, medium, high, critical)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnomalyListResponse:
    """Retrieve persisted anomalies.

    Permissions:
      - Authenticated user
      - Any active organization member (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.list_dataset_anomalies(
        dataset_id=dataset_id,
        metric_name=metric_name,
        severity=severity,
        user=current_user,
        db=db,
    )


@router.post(
    "/{dataset_id}/ml/forecasts/generate",
    response_model=ForecastResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate time-series forecast with 95% prediction intervals",
)
def generate_dataset_forecasts(
    dataset_id: uuid.UUID,
    req: ForecastGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Fit OLS linear trend + calendar seasonality model and generate forward predictions.

    Permissions:
      - Authenticated user
      - ADMIN or ANALYST in the owning organization (MANAGER and VIEWER receive 403)
    """
    return dataset_service.run_dataset_forecasting(
        dataset_id=dataset_id,
        req=req,
        user=current_user,
        db=db,
    )


@router.get(
    "/{dataset_id}/ml/forecasts",
    response_model=ForecastResponse,
    summary="Retrieve persisted forecasts for a dataset",
)
def get_dataset_forecasts(
    dataset_id: uuid.UUID,
    metric_name: str | None = Query(default=None, description="Filter by metric name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Retrieve persisted forecasts and prediction bounds.

    Permissions:
      - Authenticated user
      - Any active organization member (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.get_dataset_forecasts(
        dataset_id=dataset_id,
        metric_name=metric_name,
        user=current_user,
        db=db,
    )


@router.get(
    "/{dataset_id}/ml/summary",
    response_model=MLSummaryResponse,
    summary="Executive ML summary of active anomalies and forecast outlook",
)
def get_dataset_ml_summary(
    dataset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MLSummaryResponse:
    """Retrieve active anomaly counts by severity and forecast count.

    Permissions:
      - Authenticated user
      - Any active organization member (ADMIN, ANALYST, MANAGER, VIEWER)
    """
    return dataset_service.get_dataset_ml_summary(
        dataset_id=dataset_id,
        user=current_user,
        db=db,
    )
