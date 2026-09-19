"""services/dataset.py
===================
Dataset ingestion, retrieval, listing, and deletion service.

Enforces organization-level tenant isolation, RBAC role permissions,
content validation, safe storage handling, and database metadata updates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.rbac import can_mutate_data
from app.core.storage import (
    delete_stored_file,
    sanitize_filename,
    save_upload_file,
    validate_file_content,
)
from app.db.models.dataset import Dataset, DatasetColumn
from app.db.models.organization import OrganizationMember
from app.db.models.user import User
from app.schemas.cleaning import (
    CleaningConfig,
    CleaningPreviewResponse,
    CleaningReportResponse,
)
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
from app.services.analytics import (
    compute_overview,
    resolve_and_load_dataset,
    run_aggregation,
    run_breakdown,
    run_correlation,
    run_crosstab,
    run_time_series,
)
from app.db.models.ml import Anomaly, Forecast
from app.schemas.ml import (
    AnomalyDetectRequest,
    AnomalyItemResponse,
    AnomalyListResponse,
    ForecastGenerateRequest,
    ForecastPointResponse,
    ForecastResponse,
    MLSummaryResponse,
)
from app.services.cleaner import (
    apply_dataset_cleaning as clean_apply,
    preview_dataset_cleaning as clean_preview,
)
from app.services.ml import detect_anomalies, generate_forecast
from app.services.profiler import profile_dataframe, profile_dataset


def get_user_org_membership(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> OrganizationMember:
    """Verify that a user is an active member of an organization.

    Raises HTTP 403 Forbidden if not a member.
    """
    member = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    ).scalar_one_or_none()

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of this organization.",
        )
    return member


async def upload_dataset(
    *,
    user: User,
    organization_id: uuid.UUID,
    file: UploadFile,
    name: str,
    description: str | None = None,
    db: Session,
) -> Dataset:
    """Validate, store, and record a new dataset upload.

    Enforces:
      - Active membership in the target organization.
      - RBAC permission: only ADMIN and ANALYST can upload datasets.
      - Unique dataset name within the organization.
      - Content safety & format validation (CSV / XLSX).
      - Dedicated filesystem storage outside source code.
    """
    # 1. Authorization & Membership
    member = get_user_org_membership(organization_id, user.id, db)
    if not can_mutate_data(member.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only ADMIN and ANALYST can upload datasets.",
        )

    # 2. Name validation and uniqueness
    name = (name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset name cannot be empty.",
        )

    existing = db.execute(
        select(Dataset).where(
            Dataset.organization_id == organization_id,
            Dataset.name == name,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A dataset named '{name}' already exists in this organization.",
        )

    # 3. Read and validate file content
    raw_filename = file.filename or "upload"
    safe_filename = sanitize_filename(raw_filename)

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {e}",
        ) from e

    try:
        file_type, file_size, row_count = validate_file_content(
            content,
            filename=safe_filename,
            content_type=file.content_type,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # 4. Save to dedicated storage
    dataset_id = uuid.uuid4()
    try:
        storage_path = save_upload_file(content, organization_id, dataset_id, file_type)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save upload to disk: {e}",
        ) from e

    # 5. Persist metadata to database
    dataset = Dataset(
        id=dataset_id,
        organization_id=organization_id,
        created_by=user.id,
        name=name,
        description=description.strip() if description else None,
        source_filename=safe_filename,
        storage_path=storage_path,
        file_type=file_type,
        file_size=file_size,
        row_count=row_count,
        status="uploaded",
    )

    try:
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    except Exception as e:
        db.rollback()
        # Clean up physical file on database failure
        delete_stored_file(storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record dataset metadata.",
        ) from e

    return dataset


def list_datasets(
    *,
    organization_id: uuid.UUID,
    user: User,
    limit: int = 50,
    offset: int = 0,
    db: Session,
) -> tuple[Sequence[Dataset], int]:
    """List datasets belonging strictly to the specified organization.

    Enforces:
      - Authenticated user must belong to that organization.
      - Never leaks datasets across tenant boundaries.
      - Paginated results.
    """
    # Verify membership
    get_user_org_membership(organization_id, user.id, db)

    # Count total
    total = db.execute(
        select(func.count(Dataset.id)).where(Dataset.organization_id == organization_id)
    ).scalar_one()

    # Query items
    query = (
        select(Dataset)
        .where(Dataset.organization_id == organization_id)
        .order_by(Dataset.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = db.execute(query).scalars().all()

    return items, total


def get_dataset(
    *,
    dataset_id: uuid.UUID,
    user: User,
    db: Session,
) -> Dataset:
    """Retrieve dataset metadata by ID.

    Enforces:
      - 404 if dataset does not exist.
      - 403 if user is not a member of the dataset's organization.
    """
    dataset = db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    ).scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    # Organization membership check
    get_user_org_membership(dataset.organization_id, user.id, db)

    return dataset


def delete_dataset(
    *,
    dataset_id: uuid.UUID,
    user: User,
    db: Session,
) -> None:
    """Delete a dataset and its stored file.

    Enforces:
      - 404 if dataset does not exist.
      - 403 if caller is not an active member.
      - 403 if caller lacks ADMIN or ANALYST role.
      - Removes physical storage file safely.
    """
    dataset = db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    ).scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    member = get_user_org_membership(dataset.organization_id, user.id, db)
    if not can_mutate_data(member.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only ADMIN and ANALYST can delete datasets.",
        )

    storage_path = dataset.storage_path

    # Delete database record
    db.delete(dataset)
    db.commit()

    # Clean up physical file
    delete_stored_file(storage_path)


def get_dataset_profile(
    *,
    dataset_id: uuid.UUID,
    user: User,
    db: Session,
) -> DatasetProfileResponse:
    """Retrieve or compute the dataset data-quality and schema profile.

    Enforces:
      - 404 if dataset does not exist.
      - 403 if caller is not an active member of dataset's organization.
      - 404 if storage file is missing on disk.
      - 400 if dataset file is empty or malformed.
      - All canonical roles (ADMIN, ANALYST, MANAGER, VIEWER) may access profiling (read-only).
      - Synchronizes dataset.status = "ready", dataset.row_count, and dataset_columns in DB.
    """
    dataset = db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    ).scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    # Organization membership check (all 4 roles permitted)
    get_user_org_membership(dataset.organization_id, user.id, db)

    # Run profiling
    try:
        profile_res = profile_dataset(
            file_path=dataset.storage_path,
            file_type=dataset.file_type,
            dataset_id=dataset.id,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file not found in storage.",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Synchronize database state: status, row_count, and dataset_columns
    try:
        dataset.status = "ready"
        dataset.row_count = profile_res.row_count

        # Clean existing column records if any to avoid duplication
        db.execute(
            delete(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id)
        )
        for idx, col in enumerate(profile_res.columns):
            ds_col = DatasetColumn(
                id=uuid.uuid4(),
                dataset_id=dataset.id,
                name=col.name,
                data_type=col.inferred_datatype,
                ordinal_position=idx + 1,
                is_nullable=(col.null_count > 0),
            )
            db.add(ds_col)

        db.commit()
    except Exception:
        db.rollback()

    return profile_res


def preview_dataset_cleaning(
    *,
    dataset_id: uuid.UUID,
    config: CleaningConfig | None = None,
    user: User,
    db: Session,
) -> CleaningPreviewResponse:
    """Non-destructive preview of dataset cleaning transformations.

    Enforces:
      - 404 if dataset does not exist.
      - 403 if user does not belong to dataset's organization.
      - 404 if raw storage file is missing.
      - Read-only: permitted for all active members (ADMIN, ANALYST, MANAGER, VIEWER).
      - Original raw file is never modified.
    """
    dataset = db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    ).scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    get_user_org_membership(dataset.organization_id, user.id, db)

    try:
        return clean_preview(
            file_path=dataset.storage_path,
            file_type=dataset.file_type,
            dataset_id=dataset.id,
            config=config,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset source file not found in storage.",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


def apply_dataset_cleaning(
    *,
    dataset_id: uuid.UUID,
    config: CleaningConfig | None = None,
    user: User,
    db: Session,
) -> CleaningReportResponse:
    """Apply cleaning transformations, write processed dataset, and update metadata.

    Enforces:
      - 404 if dataset does not exist.
      - 403 if user does not belong to dataset's organization.
      - 403 if user role is MANAGER or VIEWER (only ADMIN and ANALYST may apply).
      - Raw source file remains intact and immutable.
      - Processed file is saved to data/processed/{org_id}/{dataset_id}.csv.
      - Dataset status set to 'ready', row_count updated, and dataset_columns re-synced.
    """
    dataset = db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    ).scalar_one_or_none()

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    member = get_user_org_membership(dataset.organization_id, user.id, db)
    if not can_mutate_data(member.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only ADMIN and ANALYST can apply cleaning.",
        )

    try:
        cleaned_df, report = clean_apply(
            file_path=dataset.storage_path,
            file_type=dataset.file_type,
            dataset_id=dataset.id,
            org_id=dataset.organization_id,
            config=config,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset source file not found in storage.",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Update database metadata
    try:
        dataset.status = "ready"
        dataset.row_count = report.rows_after
        dataset.processed_path = report.output_location

        # Re-profile cleaned dataframe and sync dataset_columns
        profile_res = profile_dataframe(cleaned_df, dataset_id=dataset.id)

        db.execute(
            delete(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id)
        )
        for idx, col in enumerate(profile_res.columns):
            ds_col = DatasetColumn(
                id=uuid.uuid4(),
                dataset_id=dataset.id,
                name=col.name,
                data_type=col.inferred_datatype,
                ordinal_position=idx + 1,
                is_nullable=(col.null_count > 0),
            )
            db.add(ds_col)

        db.commit()
    except Exception:
        db.rollback()

    return report


# ---------------------------------------------------------------------------
# Phase 9: Analytics Engine Orchestrations
# ---------------------------------------------------------------------------

def get_dataset_analytics_overview(
    *,
    dataset_id: uuid.UUID,
    user: User,
    db: Session,
) -> DatasetOverviewResponse:
    """Compute high-level summary KPIs and statistics for a dataset."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    try:
        df, is_cleaned = resolve_and_load_dataset(dataset)
        return compute_overview(df, dataset.id, is_cleaned)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def query_dataset_aggregation(
    *,
    dataset_id: uuid.UUID,
    query: AggregationQuery,
    user: User,
    db: Session,
) -> AggregationResult:
    """Execute multi-dimensional grouping and metric aggregation."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    try:
        df, is_cleaned = resolve_and_load_dataset(dataset)
        return run_aggregation(df, dataset.id, is_cleaned, query)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def query_dataset_time_series(
    *,
    dataset_id: uuid.UUID,
    query: TimeSeriesQuery,
    user: User,
    db: Session,
) -> TimeSeriesResult:
    """Execute temporal time-series resampling and trend analysis."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    try:
        df, is_cleaned = resolve_and_load_dataset(dataset)
        return run_time_series(df, dataset.id, is_cleaned, query)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def query_dataset_breakdown(
    *,
    dataset_id: uuid.UUID,
    query: BreakdownQuery,
    user: User,
    db: Session,
) -> BreakdownResult:
    """Compute single-dimension segment distribution and ranking."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    try:
        df, is_cleaned = resolve_and_load_dataset(dataset)
        return run_breakdown(df, dataset.id, is_cleaned, query)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def query_dataset_crosstab(
    *,
    dataset_id: uuid.UUID,
    query: CrossTabQuery,
    user: User,
    db: Session,
) -> CrossTabResult:
    """Compute 2D cross-tabulation / contingency matrix."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    try:
        df, is_cleaned = resolve_and_load_dataset(dataset)
        return run_crosstab(df, dataset.id, is_cleaned, query)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def query_dataset_correlation(
    *,
    dataset_id: uuid.UUID,
    query: CorrelationQuery,
    user: User,
    db: Session,
) -> CorrelationResult:
    """Compute correlation matrix across numeric columns."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    try:
        df, is_cleaned = resolve_and_load_dataset(dataset)
        return run_correlation(df, dataset.id, is_cleaned, query)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Phase 10: Machine Learning Engine Orchestrations
# ---------------------------------------------------------------------------

def run_dataset_anomaly_detection(
    *,
    dataset_id: uuid.UUID,
    req: AnomalyDetectRequest,
    user: User,
    db: Session,
) -> AnomalyListResponse:
    """Execute anomaly detection and optionally persist results to database."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)
    member = get_user_org_membership(dataset.organization_id, user.id, db)
    if not can_mutate_data(member.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only ADMIN and ANALYST can trigger anomaly detection.",
        )

    try:
        df, _ = resolve_and_load_dataset(dataset)
        anomalies_data, provenance = detect_anomalies(df, req, dataset.id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    items: list[AnomalyItemResponse] = []
    if req.persist:
        if req.replace_scope == "all":
            db.query(Anomaly).filter(
                Anomaly.organization_id == dataset.organization_id,
                Anomaly.dataset_id == dataset.id,
                Anomaly.metric_name == req.metric_column,
            ).delete(synchronize_session=False)
        elif req.replace_scope == "date_range" and anomalies_data:
            min_dt = min(a["detected_at"] for a in anomalies_data)
            max_dt = max(a["detected_at"] for a in anomalies_data)
            db.query(Anomaly).filter(
                Anomaly.organization_id == dataset.organization_id,
                Anomaly.dataset_id == dataset.id,
                Anomaly.metric_name == req.metric_column,
                Anomaly.detected_at.between(min_dt, max_dt),
            ).delete(synchronize_session=False)

        for a in anomalies_data:
            record = Anomaly(
                organization_id=dataset.organization_id,
                dataset_id=dataset.id,
                metric_name=a["metric_name"],
                detected_at=a["detected_at"],
                severity=a["severity"],
                description=a["description"],
                value=a["value"],
                expected_value=a["expected_value"],
            )
            db.add(record)
            db.flush()
            items.append(
                AnomalyItemResponse(
                    id=record.id,
                    metric_name=record.metric_name,
                    detected_at=record.detected_at,
                    severity=record.severity,
                    value=float(record.value) if record.value is not None else None,
                    expected_value=float(record.expected_value) if record.expected_value is not None else None,
                    deviation_pct=a.get("deviation_pct"),
                    description=record.description,
                    algorithm=a.get("algorithm"),
                )
            )
        db.commit()
    else:
        for a in anomalies_data:
            items.append(
                AnomalyItemResponse(
                    id=None,
                    metric_name=a["metric_name"],
                    detected_at=a["detected_at"],
                    severity=a["severity"],
                    value=a.get("value"),
                    expected_value=a.get("expected_value"),
                    deviation_pct=a.get("deviation_pct"),
                    description=a.get("description"),
                    algorithm=a.get("algorithm"),
                )
            )

    return AnomalyListResponse(
        dataset_id=dataset.id,
        metric_name=req.metric_column,
        total_anomalies=len(items),
        anomalies=items,
        provenance=provenance,
    )


def list_dataset_anomalies(
    *,
    dataset_id: uuid.UUID,
    metric_name: str | None = None,
    severity: str | None = None,
    user: User,
    db: Session,
) -> AnomalyListResponse:
    """List persisted anomalies for a dataset with tenant isolation."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    query = db.query(Anomaly).filter(
        Anomaly.organization_id == dataset.organization_id,
        Anomaly.dataset_id == dataset.id,
    )
    if metric_name:
        query = query.filter(Anomaly.metric_name == metric_name)
    if severity:
        query = query.filter(Anomaly.severity == severity.lower())

    records = query.order_by(Anomaly.detected_at.desc()).all()
    items = [
        AnomalyItemResponse(
            id=r.id,
            metric_name=r.metric_name,
            detected_at=r.detected_at,
            severity=r.severity,
            value=float(r.value) if r.value is not None else None,
            expected_value=float(r.expected_value) if r.expected_value is not None else None,
            deviation_pct=round(((float(r.value) - float(r.expected_value)) / max(abs(float(r.expected_value)), 1e-6)) * 100.0, 2) if r.value is not None and r.expected_value is not None else None,
            description=r.description,
            algorithm="persisted",
        )
        for r in records
    ]

    return AnomalyListResponse(
        dataset_id=dataset.id,
        metric_name=metric_name or "all",
        total_anomalies=len(items),
        anomalies=items,
        provenance={
            "dataset_id": str(dataset.id),
            "source": "database_persisted",
            "count": len(items),
            "metric_filter": metric_name,
            "severity_filter": severity,
        },
    )


def run_dataset_forecasting(
    *,
    dataset_id: uuid.UUID,
    req: ForecastGenerateRequest,
    user: User,
    db: Session,
) -> ForecastResponse:
    """Generate predictive time-series forecast with OLS and prediction intervals."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)
    member = get_user_org_membership(dataset.organization_id, user.id, db)
    if not can_mutate_data(member.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only ADMIN and ANALYST can generate forecasts.",
        )

    try:
        df, _ = resolve_and_load_dataset(dataset)
        points_data, provenance = generate_forecast(df, req, dataset.id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    items: list[ForecastPointResponse] = []
    now_utc = datetime.now(timezone.utc)

    if req.persist and points_data:
        if req.replace_scope == "horizon_range":
            min_d = min(p["forecast_date"] for p in points_data)
            max_d = max(p["forecast_date"] for p in points_data)
            db.query(Forecast).filter(
                Forecast.organization_id == dataset.organization_id,
                Forecast.dataset_id == dataset.id,
                Forecast.metric_name == req.metric_column,
                Forecast.forecast_date.between(min_d, max_d),
            ).delete(synchronize_session=False)
        else:
            db.query(Forecast).filter(
                Forecast.organization_id == dataset.organization_id,
                Forecast.dataset_id == dataset.id,
                Forecast.metric_name == req.metric_column,
            ).delete(synchronize_session=False)

        for p in points_data:
            record = Forecast(
                organization_id=dataset.organization_id,
                dataset_id=dataset.id,
                metric_name=req.metric_column,
                forecast_date=p["forecast_date"],
                predicted_value=p["predicted_value"],
                lower_bound=p["lower_bound"],
                upper_bound=p["upper_bound"],
                model_name=p["model_name"],
                generated_at=now_utc,
            )
            db.add(record)
            items.append(
                ForecastPointResponse(
                    forecast_date=p["forecast_date"],
                    predicted_value=p["predicted_value"],
                    lower_bound=p["lower_bound"],
                    upper_bound=p["upper_bound"],
                    model_name=p["model_name"],
                )
            )
        db.commit()
    else:
        for p in points_data:
            items.append(
                ForecastPointResponse(
                    forecast_date=p["forecast_date"],
                    predicted_value=p["predicted_value"],
                    lower_bound=p["lower_bound"],
                    upper_bound=p["upper_bound"],
                    model_name=p["model_name"],
                )
            )

    return ForecastResponse(
        dataset_id=dataset.id,
        metric_name=req.metric_column,
        horizon_days=req.horizon_days,
        model_name=provenance.get("model_name", "OLSTrend"),
        generated_at=now_utc,
        forecasts=items,
        provenance=provenance,
    )


def get_dataset_forecasts(
    *,
    dataset_id: uuid.UUID,
    metric_name: str | None = None,
    user: User,
    db: Session,
) -> ForecastResponse:
    """Retrieve persisted forecasts for a dataset."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    query = db.query(Forecast).filter(
        Forecast.organization_id == dataset.organization_id,
        Forecast.dataset_id == dataset.id,
    )
    if metric_name:
        query = query.filter(Forecast.metric_name == metric_name)

    records = query.order_by(Forecast.forecast_date.asc()).all()
    items = [
        ForecastPointResponse(
            forecast_date=r.forecast_date,
            predicted_value=float(r.predicted_value),
            lower_bound=float(r.lower_bound) if r.lower_bound is not None else None,
            upper_bound=float(r.upper_bound) if r.upper_bound is not None else None,
            model_name=r.model_name,
        )
        for r in records
    ]

    latest_gen = max((r.generated_at for r in records), default=datetime.now(timezone.utc))
    first_model = records[0].model_name if records else "Unknown"

    return ForecastResponse(
        dataset_id=dataset.id,
        metric_name=metric_name or (records[0].metric_name if records else "all"),
        horizon_days=len(items),
        model_name=first_model,
        generated_at=latest_gen,
        forecasts=items,
        provenance={
            "dataset_id": str(dataset.id),
            "source": "database_persisted",
            "metric_filter": metric_name,
            "total_points": len(items),
        },
    )


def get_dataset_ml_summary(
    *,
    dataset_id: uuid.UUID,
    user: User,
    db: Session,
) -> MLSummaryResponse:
    """Retrieve executive summary of active anomalies and forecast points."""
    dataset = get_dataset(dataset_id=dataset_id, user=user, db=db)

    anomalies = db.query(Anomaly).filter(
        Anomaly.organization_id == dataset.organization_id,
        Anomaly.dataset_id == dataset.id,
    ).all()

    sev_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    anom_metrics = set()
    for a in anomalies:
        if a.severity in sev_counts:
            sev_counts[a.severity] += 1
        anom_metrics.add(a.metric_name)

    forecast_records = db.query(Forecast).filter(
        Forecast.organization_id == dataset.organization_id,
        Forecast.dataset_id == dataset.id,
    ).all()

    fc_metrics = {f.metric_name for f in forecast_records}
    all_metrics = sorted(anom_metrics.union(fc_metrics))

    return MLSummaryResponse(
        dataset_id=dataset.id,
        total_anomalies_active=len(anomalies),
        anomalies_by_severity=sev_counts,
        forecasts_active_count=len(forecast_records),
        metrics_analyzed=all_metrics,
    )

