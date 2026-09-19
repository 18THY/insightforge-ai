"""api/rca.py
==========
FastAPI endpoints for Root-Cause Analysis (RCA) Engine (Phase 11).

Provides:
- POST /datasets/{dataset_id}/rca/analyze: Full multi-dimensional root-cause analysis
- GET /datasets/{dataset_id}/rca/anomaly/{anomaly_id}: Automated RCA on a specific anomaly record
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models.user import User
from app.schemas.rca import RCAAnalyzeRequest, RCAResponse
from app.services.dataset import run_dataset_rca

router = APIRouter(prefix="/datasets/{dataset_id}/rca", tags=["rca"])


@router.post(
    "/analyze",
    response_model=RCAResponse,
    summary="Execute Root-Cause Analysis on dataset",
    description=(
        "Performs deterministic waterfall dimension decomposition, multi-dimensional driver ranking, "
        "secondary metric elasticity analysis, and statistical significance z-score evaluation."
    ),
)
def analyze_root_cause(
    dataset_id: uuid.UUID,
    body: RCAAnalyzeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> RCAResponse:
    client_ip = request.client.host if request.client else None
    return run_dataset_rca(
        dataset_id=dataset_id,
        req=body,
        user=current_user,
        db=db,
        client_ip=client_ip,
    )


@router.get(
    "/anomaly/{anomaly_id}",
    response_model=RCAResponse,
    summary="Run automated RCA for a specific persisted anomaly",
    description="Loads the specified anomaly record and automatically performs root-cause analysis against preceding baseline.",
)
def analyze_anomaly_root_cause(
    dataset_id: uuid.UUID,
    anomaly_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> RCAResponse:
    client_ip = request.client.host if request.client else None
    req = RCAAnalyzeRequest(anomaly_id=anomaly_id)
    return run_dataset_rca(
        dataset_id=dataset_id,
        req=req,
        user=current_user,
        db=db,
        client_ip=client_ip,
    )
