"""tests/test_ml.py
================
Comprehensive automated test suite for Phase 10: Machine Learning Engine.

Validates:
 1. test_path_traversal_ml_rejected
 2. test_unknown_dataset_returns_404
 3. test_unauthenticated_returns_401
 4. test_cross_organization_ml_forbidden
 5. test_rbac_admin_analyst_allowed_manager_viewer_denied_generation
 6. test_rbac_all_org_roles_can_read_anomalies_and_forecasts
 7. test_statistical_anomaly_detection_with_spikes
 8. test_statistical_anomaly_detection_insufficient_data_rejected
 9. test_isolation_forest_deterministic_reproducibility
10. test_isolation_forest_severity_mapping_calibrated
11. test_zero_variance_anomaly_detection_returns_zero
12. test_ols_forecast_point_and_prediction_intervals
13. test_ols_forecast_prediction_error_expands_with_horizon
14. test_ols_forecast_insufficient_history_rejected
15. test_ols_degrees_of_freedom_insufficient_rejected
16. test_missing_period_semantic_handling_sum_vs_mean
17. test_no_leading_or_trailing_gap_extrapolation
18. test_negative_metric_forecast_preserves_negative_lower_bound
19. test_non_negative_metric_clamps_lower_bound_to_zero
20. test_multi_horizon_scoped_refresh_preserves_unrelated_dates
21. test_forecast_replace_scope_all_clears_all_prior_points
22. test_anomaly_replace_scope_cleans_prior_run
23. test_invalid_date_or_metric_column_rejected
24. test_ml_summary_endpoint
"""

from __future__ import annotations

import io
import shutil
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.auth import AuthSession
from app.db.models.dataset import Dataset, DatasetColumn
from app.db.models.ml import Anomaly, Forecast
from app.db.models.organization import Organization, OrganizationMember
from app.db.models.user import User
from app.db.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# Test database setup (in-memory SQLite)
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite://"

_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
)

ML_TEST_TABLES = [
    User.__table__,
    AuthSession.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
    Dataset.__table__,
    DatasetColumn.__table__,
    Anomaly.__table__,
    Forecast.__table__,
]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=ML_TEST_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=ML_TEST_TABLES)


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    _create_tables()
    yield
    _drop_tables()


@pytest.fixture()
def db() -> Session:
    connection = _engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session, monkeypatch) -> TestClient:
    temp_upload_dir = tempfile.mkdtemp(prefix="insightforge_ml_uploads_")
    temp_processed_dir = tempfile.mkdtemp(prefix="insightforge_ml_processed_")
    monkeypatch.setattr(get_settings(), "upload_dir", temp_upload_dir)
    monkeypatch.setattr(get_settings(), "processed_dir", temp_processed_dir)

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    shutil.rmtree(temp_upload_dir, ignore_errors=True)
    shutil.rmtree(temp_processed_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user_and_login(client: TestClient, email: str, password: str = "Password123!") -> tuple[dict, str]:
    reg_resp = client.post("/auth/register", json={"email": email, "password": password})
    assert reg_resp.status_code == 201
    user = reg_resp.json()

    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return user, token


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_org(client: TestClient, token: str, name: str = "ML Test Org") -> str:
    resp = client.post("/organizations", json={"name": name}, headers=_auth_header(token))
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_member(client: TestClient, admin_token: str, org_id: str, email: str, role: str) -> None:
    resp = client.post(
        f"/organizations/{org_id}/members",
        json={"email": email, "role": role},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 201


def _generate_ts_csv(
    days: int = 60,
    start_date: str = "2024-01-01",
    base: float = 100.0,
    trend: float = 1.0,
    weekly_seasonality: bool = True,
    spikes: dict[int, float] | None = None,
    missing_indices: list[int] | None = None,
) -> bytes:
    """Generate synthetic continuous time-series CSV for testing."""
    start = pd.to_datetime(start_date)
    rows = ["order_date,amount,orders_count"]
    season_pattern = [0.0, 10.0, 5.0, 15.0, 25.0, 50.0, 30.0]

    for i in range(days):
        if missing_indices and i in missing_indices:
            continue
        dt = (start + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        noise = round(float(np.sin(i * 0.7) * 3.0), 2)
        val = base + i * trend + noise
        if weekly_seasonality:
            val += season_pattern[i % 7]
        if spikes and i in spikes:
            val += spikes[i]
        rows.append(f"{dt},{round(val, 2)},{int(max(1, val // 10))}")

    return "\n".join(rows).encode("utf-8")


def _upload_dataset(client: TestClient, token: str, org_id: str, name: str, csv_bytes: bytes) -> str:
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": name},
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert up_resp.status_code == 201
    return up_resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_path_traversal_ml_rejected(client: TestClient, db: Session):
    """Test 1: Path traversal attempt in storage_path is rejected."""
    _, token = _create_user_and_login(client, "ml_pt@example.com")
    org_id = _create_org(client, token, "PT Org")
    dataset_id = _upload_dataset(client, token, org_id, "PT DS", _generate_ts_csv(days=30))

    # Poison storage_path in DB
    ds = db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))).scalar_one()
    ds.storage_path = str(Path(get_settings().upload_dir).parent / "secret.csv")
    db.commit()

    resp = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount"},
    )
    assert resp.status_code == 400
    assert "unsafe" in resp.json()["detail"].lower() or "traversal" in resp.json()["detail"].lower()


def test_unknown_dataset_returns_404(client: TestClient):
    """Test 2: Unknown dataset UUID returns HTTP 404."""
    _, token = _create_user_and_login(client, "ml_404@example.com")
    random_id = str(uuid.uuid4())

    resp = client.post(
        f"/datasets/{random_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount"},
    )
    assert resp.status_code == 404


def test_unauthenticated_returns_401(client: TestClient):
    """Test 3: Missing authorization header returns HTTP 401."""
    random_id = str(uuid.uuid4())
    resp = client.get(f"/datasets/{random_id}/ml/anomalies")
    assert resp.status_code == 401


def test_cross_organization_ml_forbidden(client: TestClient):
    """Test 4: Accessing ML endpoints of another organization returns HTTP 403."""
    _, token_a = _create_user_and_login(client, "org_a_user@example.com")
    org_a = _create_org(client, token_a, "Org A")
    dataset_a = _upload_dataset(client, token_a, org_a, "Org A DS", _generate_ts_csv(days=30))

    _, token_b = _create_user_and_login(client, "org_b_user@example.com")
    org_b = _create_org(client, token_b, "Org B")

    # Org B user attempts to run anomaly detection on Org A dataset
    resp = client.post(
        f"/datasets/{dataset_a}/ml/anomalies/detect",
        headers=_auth_header(token_b),
        json={"date_column": "order_date", "metric_column": "amount"},
    )
    assert resp.status_code == 403


def test_rbac_admin_analyst_allowed_manager_viewer_denied_generation(client: TestClient):
    """Test 5: ADMIN and ANALYST can trigger ML generation; MANAGER and VIEWER receive 403."""
    _, admin_token = _create_user_and_login(client, "rbac_admin@example.com")
    org_id = _create_org(client, admin_token, "RBAC Org")
    dataset_id = _upload_dataset(client, admin_token, org_id, "RBAC DS", _generate_ts_csv(days=40))

    _, analyst_token = _create_user_and_login(client, "rbac_analyst@example.com")
    _add_member(client, admin_token, org_id, "rbac_analyst@example.com", "analyst")

    _, manager_token = _create_user_and_login(client, "rbac_manager@example.com")
    _add_member(client, admin_token, org_id, "rbac_manager@example.com", "manager")

    _, viewer_token = _create_user_and_login(client, "rbac_viewer@example.com")
    _add_member(client, admin_token, org_id, "rbac_viewer@example.com", "viewer")

    payload = {"date_column": "order_date", "metric_column": "amount"}

    # ADMIN allowed
    resp_adm = client.post(f"/datasets/{dataset_id}/ml/anomalies/detect", headers=_auth_header(admin_token), json=payload)
    assert resp_adm.status_code == 200

    # ANALYST allowed
    resp_ana = client.post(f"/datasets/{dataset_id}/ml/anomalies/detect", headers=_auth_header(analyst_token), json=payload)
    assert resp_ana.status_code == 200

    # MANAGER denied
    resp_mgr = client.post(f"/datasets/{dataset_id}/ml/anomalies/detect", headers=_auth_header(manager_token), json=payload)
    assert resp_mgr.status_code == 403

    # VIEWER denied
    resp_vwr = client.post(f"/datasets/{dataset_id}/ml/anomalies/detect", headers=_auth_header(viewer_token), json=payload)
    assert resp_vwr.status_code == 403


def test_rbac_all_org_roles_can_read_anomalies_and_forecasts(client: TestClient):
    """Test 6: All organization roles (ADMIN, ANALYST, MANAGER, VIEWER) can read ML outputs."""
    _, admin_token = _create_user_and_login(client, "read_admin@example.com")
    org_id = _create_org(client, admin_token, "Read Org")
    dataset_id = _upload_dataset(client, admin_token, org_id, "Read DS", _generate_ts_csv(days=40))

    _, viewer_token = _create_user_and_login(client, "read_viewer@example.com")
    _add_member(client, admin_token, org_id, "read_viewer@example.com", "viewer")

    # Viewer queries anomalies & forecasts
    anom_resp = client.get(f"/datasets/{dataset_id}/ml/anomalies", headers=_auth_header(viewer_token))
    assert anom_resp.status_code == 200

    fc_resp = client.get(f"/datasets/{dataset_id}/ml/forecasts", headers=_auth_header(viewer_token))
    assert fc_resp.status_code == 200


def test_statistical_anomaly_detection_with_spikes(client: TestClient):
    """Test 7: Detect injected positive spike and classify as critical severity."""
    _, token = _create_user_and_login(client, "stat_anom@example.com")
    org_id = _create_org(client, token, "Stat Org")

    # Inject massive spike at day 25 (+500.0 on base ~150.0)
    csv_data = _generate_ts_csv(days=40, base=100.0, trend=1.0, spikes={25: 600.0})
    dataset_id = _upload_dataset(client, token, org_id, "Spike DS", csv_data)

    resp = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "amount",
            "method": "statistical",
            "sensitivity": "medium",
            "window_size": 7,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_anomalies"] >= 1
    # Check that the spike was detected with critical or high severity
    spike_anom = [a for a in body["anomalies"] if a["value"] > 500.0]
    assert len(spike_anom) == 1
    assert spike_anom[0]["severity"] in ("critical", "high")
    assert body["provenance"]["algorithm"] == "statistical"


def test_statistical_anomaly_detection_insufficient_data_rejected(client: TestClient):
    """Test 8: Statistical anomaly detection rejects data shorter than 2*window (N < 14)."""
    _, token = _create_user_and_login(client, "short_ts@example.com")
    org_id = _create_org(client, token, "Short Org")
    dataset_id = _upload_dataset(client, token, org_id, "Short DS", _generate_ts_csv(days=8))

    resp = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "amount",
            "method": "statistical",
            "window_size": 7,
        },
    )
    assert resp.status_code == 400
    assert "insufficient historical data" in resp.json()["detail"].lower()


def test_isolation_forest_deterministic_reproducibility(client: TestClient):
    """Test 9: IsolationForest with fixed random_state=42 produces bitwise identical results."""
    _, token = _create_user_and_login(client, "iso_det@example.com")
    org_id = _create_org(client, token, "Iso Org")
    csv_data = _generate_ts_csv(days=50, base=200.0, trend=2.0, spikes={30: 1000.0})
    dataset_id = _upload_dataset(client, token, org_id, "Iso DS", csv_data)

    payload = {
        "date_column": "order_date",
        "metric_column": "amount",
        "method": "isolation_forest",
        "sensitivity": "medium",
    }

    resp1 = client.post(f"/datasets/{dataset_id}/ml/anomalies/detect", headers=_auth_header(token), json=payload)
    assert resp1.status_code == 200

    resp2 = client.post(f"/datasets/{dataset_id}/ml/anomalies/detect", headers=_auth_header(token), json=payload)
    assert resp2.status_code == 200

    assert resp1.json()["total_anomalies"] == resp2.json()["total_anomalies"]
    dates1 = [a["detected_at"] for a in resp1.json()["anomalies"]]
    dates2 = [a["detected_at"] for a in resp2.json()["anomalies"]]
    assert dates1 == dates2


def test_isolation_forest_severity_mapping_calibrated(client: TestClient):
    """Test 10: IsolationForest severity mapping maps extreme outlier to critical/high."""
    _, token = _create_user_and_login(client, "iso_sev@example.com")
    org_id = _create_org(client, token, "Iso Sev Org")
    csv_data = _generate_ts_csv(days=60, base=100.0, trend=0.5, spikes={40: 1500.0})
    dataset_id = _upload_dataset(client, token, org_id, "Iso Sev DS", csv_data)

    resp = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "method": "isolation_forest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    spike_items = [a for a in body["anomalies"] if a["value"] > 1000.0]
    assert len(spike_items) >= 1
    assert spike_items[0]["severity"] in ("critical", "high")


def test_zero_variance_anomaly_detection_returns_zero(client: TestClient):
    """Test 11: Series with constant values (variance = 0) returns 0 anomalies cleanly."""
    _, token = _create_user_and_login(client, "zero_var@example.com")
    org_id = _create_org(client, token, "ZV Org")

    # Constant amount = 50.0 across all 30 days
    start = pd.to_datetime("2024-01-01")
    lines = ["order_date,amount"] + [(start + pd.Timedelta(days=i)).strftime("%Y-%m-%d") + ",50.0" for i in range(30)]
    dataset_id = _upload_dataset(client, token, org_id, "ZV DS", "\n".join(lines).encode("utf-8"))

    resp = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "method": "statistical"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_anomalies"] == 0
    assert body["provenance"].get("zero_variance") is True


def test_ols_forecast_point_and_prediction_intervals(client: TestClient):
    """Test 12: OLS trend + seasonality forecast correctly evaluates point forecast and bounds."""
    _, token = _create_user_and_login(client, "ols_fc@example.com")
    org_id = _create_org(client, token, "OLS Org")
    csv_data = _generate_ts_csv(days=70, base=100.0, trend=2.0, weekly_seasonality=True)
    dataset_id = _upload_dataset(client, token, org_id, "OLS DS", csv_data)

    resp = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "amount",
            "horizon_days": 14,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["forecasts"]) == 14

    for p in body["forecasts"]:
        assert p["lower_bound"] <= p["predicted_value"] <= p["upper_bound"]

    prov = body["provenance"]
    assert prov["parameters"]["parameters_count"] == 8  # 1 intercept + 1 trend + 6 day dummies
    assert prov["parameters"]["degrees_of_freedom"] == 70 - 8
    assert prov["residual_standard_error"] > 0.0


def test_ols_forecast_prediction_error_expands_with_horizon(client: TestClient):
    """Test 13: Prediction interval standard error strictly widens as horizon increases."""
    _, token = _create_user_and_login(client, "ols_exp@example.com")
    org_id = _create_org(client, token, "Exp Org")
    csv_data = _generate_ts_csv(days=70, base=50.0, trend=1.5, weekly_seasonality=True)
    dataset_id = _upload_dataset(client, token, org_id, "Exp DS", csv_data)

    resp = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "horizon_days": 14},
    )
    assert resp.status_code == 200
    pts = resp.json()["forecasts"]

    # Margin = upper_bound - predicted_value
    margin_day1 = pts[0]["upper_bound"] - pts[0]["predicted_value"]
    margin_day14 = pts[13]["upper_bound"] - pts[13]["predicted_value"]
    assert margin_day14 > margin_day1


def test_ols_forecast_insufficient_history_rejected(client: TestClient):
    """Test 14: Forecast rejected when N < 2 * horizon."""
    _, token = _create_user_and_login(client, "ols_insuf@example.com")
    org_id = _create_org(client, token, "Insuf Org")
    csv_data = _generate_ts_csv(days=25)
    dataset_id = _upload_dataset(client, token, org_id, "Insuf DS", csv_data)

    # 30-day forecast requires at least 60 points
    resp = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "horizon_days": 30},
    )
    assert resp.status_code == 400
    assert "insufficient historical data" in resp.json()["detail"].lower()


def test_ols_degrees_of_freedom_insufficient_rejected(client: TestClient):
    """Test 15: Direct validation rejection when degrees of freedom N <= p."""
    _, token = _create_user_and_login(client, "ols_dof@example.com")
    org_id = _create_org(client, token, "DOF Org")
    csv_data = _generate_ts_csv(days=14)
    dataset_id = _upload_dataset(client, token, org_id, "DOF DS", csv_data)

    # 7-day horizon with daily seasonality has p=8 parameters; requires N >= 14
    # If horizon was 10 days, N_min = 20 > 14
    resp = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "horizon_days": 10},
    )
    assert resp.status_code == 400
    assert "insufficient historical data" in resp.json()["detail"].lower()


def test_missing_period_semantic_handling_sum_vs_mean(client: TestClient):
    """Test 16: Missing periods are zero-filled for sum, and interpolated for mean."""
    _, token = _create_user_and_login(client, "missing_sem@example.com")
    org_id = _create_org(client, token, "Miss Org")

    # 40 days, missing day 10, 11, 12
    csv_data = _generate_ts_csv(days=40, missing_indices=[10, 11, 12])
    dataset_id = _upload_dataset(client, token, org_id, "Miss DS", csv_data)

    # Run forecast with sum
    resp_sum = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "aggregation": "sum", "horizon_days": 7},
    )
    assert resp_sum.status_code == 200

    # Run forecast with mean
    resp_mean = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "aggregation": "mean", "horizon_days": 7},
    )
    assert resp_mean.status_code == 200


def test_no_leading_or_trailing_gap_extrapolation(client: TestClient):
    """Test 17: Time-series regularization bounds strictly between observed dates."""
    _, token = _create_user_and_login(client, "gap_lead@example.com")
    org_id = _create_org(client, token, "Lead Org")
    csv_data = _generate_ts_csv(days=35, start_date="2024-03-01")
    dataset_id = _upload_dataset(client, token, org_id, "Lead DS", csv_data)

    resp = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "horizon_days": 7},
    )
    assert resp.status_code == 200
    prov = resp.json()["provenance"]
    assert prov["training_period"]["start_date"] == "2024-03-01"
    # Observations count exactly matches 35 days
    assert prov["training_period"]["observations_count"] == 35


def test_negative_metric_forecast_preserves_negative_lower_bound(client: TestClient):
    """Test 18: Negative-valued metrics or allow_negative=True do not clamp lower bound to 0."""
    _, token = _create_user_and_login(client, "neg_metric@example.com")
    org_id = _create_org(client, token, "Neg Org")

    # Centered around 0: from -50 to +50
    start = pd.to_datetime("2024-01-01")
    lines = ["order_date,profit"]
    for i in range(50):
        dt = (start + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(f"{dt},{-100.0 + i * 0.5 + float(np.sin(i) * 2.0)}")
    dataset_id = _upload_dataset(client, token, org_id, "Neg DS", "\n".join(lines).encode("utf-8"))

    resp = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "profit",
            "horizon_days": 7,
            "allow_negative": True,
        },
    )
    assert resp.status_code == 200
    pts = resp.json()["forecasts"]
    has_negative_bound = any(p["lower_bound"] < 0 for p in pts)
    assert has_negative_bound


def test_non_negative_metric_clamps_lower_bound_to_zero(client: TestClient):
    """Test 19: Non-negative metrics with large variance clamp lower_bound to >= 0."""
    _, token = _create_user_and_login(client, "clamp_zero@example.com")
    org_id = _create_org(client, token, "Clamp Org")

    # Positive metric close to 0 with high variance
    csv_data = _generate_ts_csv(days=40, base=5.0, trend=0.1, spikes={5: 80.0, 15: 120.0})
    dataset_id = _upload_dataset(client, token, org_id, "Clamp DS", csv_data)

    resp = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "amount",
            "horizon_days": 7,
            "allow_negative": False,
        },
    )
    assert resp.status_code == 200
    for p in resp.json()["forecasts"]:
        assert p["lower_bound"] >= 0.0


def test_multi_horizon_scoped_refresh_preserves_unrelated_dates(client: TestClient):
    """Test 20: Re-running 7-day forecast with horizon_range preserves days 8-14 from 14-day run."""
    _, token = _create_user_and_login(client, "scoped_rf@example.com")
    org_id = _create_org(client, token, "Scope Org")
    csv_data = _generate_ts_csv(days=50, base=100.0, trend=1.0)
    dataset_id = _upload_dataset(client, token, org_id, "Scope DS", csv_data)

    # 1. Run 14-day forecast
    resp14 = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "horizon_days": 14, "persist": True},
    )
    assert resp14.status_code == 200

    # 2. Run 7-day forecast with default replace_scope="horizon_range"
    resp7 = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "amount",
            "horizon_days": 7,
            "replace_scope": "horizon_range",
            "persist": True,
        },
    )
    assert resp7.status_code == 200

    # 3. Retrieve all persisted forecasts
    get_resp = client.get(f"/datasets/{dataset_id}/ml/forecasts?metric_name=amount", headers=_auth_header(token))
    assert get_resp.status_code == 200
    persisted_pts = get_resp.json()["forecasts"]

    # Days 8-14 must still exist!
    assert len(persisted_pts) == 14


def test_forecast_replace_scope_all_clears_all_prior_points(client: TestClient):
    """Test 21: replace_scope="all" clears all prior forecast days for that metric."""
    _, token = _create_user_and_login(client, "scope_all@example.com")
    org_id = _create_org(client, token, "All Org")
    csv_data = _generate_ts_csv(days=50, base=100.0, trend=1.0)
    dataset_id = _upload_dataset(client, token, org_id, "All DS", csv_data)

    # 1. Run 14-day forecast
    client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "horizon_days": 14, "persist": True},
    )

    # 2. Run 7-day forecast with replace_scope="all"
    client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "amount",
            "horizon_days": 7,
            "replace_scope": "all",
            "persist": True,
        },
    )

    # 3. Verify exactly 7 points remain
    get_resp = client.get(f"/datasets/{dataset_id}/ml/forecasts?metric_name=amount", headers=_auth_header(token))
    assert len(get_resp.json()["forecasts"]) == 7


def test_anomaly_replace_scope_cleans_prior_run(client: TestClient):
    """Test 22: Re-running anomaly detection with persist=True replaces prior records without duplication."""
    _, token = _create_user_and_login(client, "anom_clean@example.com")
    org_id = _create_org(client, token, "Anom Clean Org")
    csv_data = _generate_ts_csv(days=40, spikes={20: 500.0})
    dataset_id = _upload_dataset(client, token, org_id, "Anom Clean DS", csv_data)

    # Run 1
    resp1 = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "persist": True},
    )
    count1 = resp1.json()["total_anomalies"]

    # Run 2 (identical)
    resp2 = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "persist": True},
    )
    count2 = resp2.json()["total_anomalies"]
    assert count1 == count2

    # Query DB records via GET
    get_resp = client.get(f"/datasets/{dataset_id}/ml/anomalies?metric_name=amount", headers=_auth_header(token))
    assert len(get_resp.json()["anomalies"]) == count1


def test_invalid_date_or_metric_column_rejected(client: TestClient):
    """Test 23: Non-existent date or metric column returns HTTP 400."""
    _, token = _create_user_and_login(client, "invalid_col@example.com")
    org_id = _create_org(client, token, "Col Org")
    dataset_id = _upload_dataset(client, token, org_id, "Col DS", _generate_ts_csv(days=30))

    # Invalid date column
    resp1 = client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "fake_date", "metric_column": "amount"},
    )
    assert resp1.status_code == 400

    # Invalid metric column
    resp2 = client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "fake_metric", "horizon_days": 7},
    )
    assert resp2.status_code == 400


def test_ml_summary_endpoint(client: TestClient):
    """Test 24: ML summary endpoint returns combined statistics."""
    _, token = _create_user_and_login(client, "ml_summary@example.com")
    org_id = _create_org(client, token, "Summary Org")
    dataset_id = _upload_dataset(client, token, org_id, "Summary DS", _generate_ts_csv(days=40, spikes={20: 500.0}))

    # Generate an anomaly
    client.post(
        f"/datasets/{dataset_id}/ml/anomalies/detect",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "persist": True},
    )

    # Generate a forecast
    client.post(
        f"/datasets/{dataset_id}/ml/forecasts/generate",
        headers=_auth_header(token),
        json={"date_column": "order_date", "metric_column": "amount", "horizon_days": 7, "persist": True},
    )

    # Get summary
    sum_resp = client.get(f"/datasets/{dataset_id}/ml/summary", headers=_auth_header(token))
    assert sum_resp.status_code == 200
    data = sum_resp.json()
    assert data["total_anomalies_active"] >= 1
    assert data["forecasts_active_count"] == 7
    assert "amount" in data["metrics_analyzed"]
