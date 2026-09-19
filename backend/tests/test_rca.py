"""tests/test_rca.py
=================
Comprehensive automated test suite for Phase 11: Root-Cause Analysis (RCA) Engine.

Validates:
 1. test_deterministic_baseline_selection_precedence
 2. test_baseline_selection_fallback_when_preceding_before_boundary
 3. test_insufficient_history_for_baseline_rejected
 4. test_zero_net_change_handling
 5. test_waterfall_reconciliation_exact
 6. test_waterfall_reconciliation_pre_truncation
 7. test_statistical_z_score_calculation
 8. test_zero_and_near_zero_baseline_variance
 9. test_multidimensional_cardinality_and_ordering
10. test_secondary_metric_elasticity_and_direction
11. test_secondary_metric_elasticity_zero_denominators
12. test_evidence_provenance_completeness
13. test_deterministic_template_narrative
14. test_audit_log_entry_created
15. test_rbac_all_roles_can_execute_rca
16. test_unauthenticated_returns_401
17. test_cross_organization_dataset_rca_forbidden
18. test_cross_organization_anomaly_rca_forbidden
19. test_unknown_anomaly_id_returns_404
20. test_unknown_dataset_id_returns_404
21. test_inverted_dates_rejected
22. test_non_existent_column_rejected
23. test_get_anomaly_rca_endpoint
24. test_volume_contribution_vs_statistical_unusualness
25. test_event_window_inclusive_semantics
"""

from __future__ import annotations

import io
import shutil
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.audit import AuditLog
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

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


SQLITE_URL = "sqlite://"

_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
)

RCA_TEST_TABLES = [
    User.__table__,
    AuthSession.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
    Dataset.__table__,
    DatasetColumn.__table__,
    Anomaly.__table__,
    Forecast.__table__,
    AuditLog.__table__,
]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=RCA_TEST_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=RCA_TEST_TABLES)


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
def client(db: Session) -> TestClient:
    temp_upload_dir = tempfile.mkdtemp(prefix="if_rca_upload_")
    temp_processed_dir = tempfile.mkdtemp(prefix="if_rca_proc_")
    settings = get_settings()
    orig_upload = settings.upload_dir
    orig_proc = settings.processed_dir
    settings.upload_dir = temp_upload_dir
    settings.processed_dir = temp_processed_dir

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    settings.upload_dir = orig_upload
    settings.processed_dir = orig_proc
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


def _create_org(client: TestClient, token: str, name: str = "RCA Test Org") -> str:
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


def _upload_dataset(client: TestClient, token: str, org_id: str, name: str, csv_bytes: bytes) -> str:
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": name},
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert up_resp.status_code == 201
    return up_resp.json()["id"]


def _make_rca_csv(days: int = 30) -> bytes:
    """Generate 30 days of data with categories and secondary metrics."""
    np.random.seed(42)
    start_dt = date(2024, 1, 1)
    dates = [start_dt + timedelta(days=i) for i in range(days)]
    records = ["date,category,region,revenue,orders,discount"]

    categories = ["Electronics", "Fashion", "Home", "Beauty"]
    regions = ["North", "South", "East", "West"]

    for d in dates:
        for cat in categories:
            for reg in regions:
                rev = float(np.random.uniform(90, 110))
                orders = int(np.random.randint(5, 15))
                discount = float(np.random.uniform(5.0, 10.0))

                # Inject anomaly on 2024-01-20: Electronics drops significantly
                if d == date(2024, 1, 20):
                    if cat == "Electronics":
                        rev = 20.0
                        orders = 2
                    elif cat == "Fashion":
                        rev = 105.0
                    elif cat == "Home":
                        rev = 95.0
                    elif cat == "Beauty":
                        rev = 100.0

                records.append(f"{d.isoformat()},{cat},{reg},{round(rev, 2)},{orders},{round(discount, 2)}")

    return "\n".join(records).encode("utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_deterministic_baseline_selection_precedence(client: TestClient):
    _, token = _create_user_and_login(client, "rca_prec@example.com")
    org_id = _create_org(client, token, "Precedence Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_ds.csv", _make_rca_csv(30))

    # 1. Custom baseline precedence
    payload_custom = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
        "baseline_start": "2024-01-10",
        "baseline_end": "2024-01-10",
        "baseline_mode": "custom",
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload_custom,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["provenance"]["baseline_mode_applied"] == "custom"
    assert data["baseline_window"]["start"] == "2024-01-10"
    assert data["baseline_window"]["end"] == "2024-01-10"

    # 2. Preceding period auto-window (1-day event on 2024-01-20 -> baseline is 2024-01-19)
    payload_auto = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
    }
    r2 = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload_auto,
        headers=_auth_header(token),
    )
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["provenance"]["baseline_mode_applied"] == "prior_period"
    assert data2["baseline_window"]["start"] == "2024-01-19"
    assert data2["baseline_window"]["end"] == "2024-01-19"


def test_baseline_selection_fallback_when_preceding_before_boundary(client: TestClient):
    _, token = _create_user_and_login(client, "rca_fallback@example.com")
    org_id = _create_org(client, token, "Fallback Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_fallback_ds.csv", _make_rca_csv(30))

    # Event starts on day 4 (2024-01-04 to 2024-01-05 = 2 days)
    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-04",
        "event_end": "2024-01-05",
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["baseline_window"]["start"] == "2024-01-02"
    assert data["baseline_window"]["end"] == "2024-01-03"


def test_insufficient_history_for_baseline_rejected(client: TestClient):
    _, token = _create_user_and_login(client, "rca_insuff@example.com")
    org_id = _create_org(client, token, "Insuff Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_insuff_ds.csv", _make_rca_csv(3))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-01",
        "event_end": "2024-01-03",
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 400
    assert "Insufficient historical data" in r.json()["detail"]


def test_zero_net_change_handling(client: TestClient):
    _, token = _create_user_and_login(client, "rca_zero_net@example.com")
    org_id = _create_org(client, token, "Zero Net Org")

    # Baseline: A=100, B=100 (total 200). Event: A=150, B=50 (total 200, delta = 0.0)
    csv_content = (
        """date,cat,val\n2024-01-01,A,100.0\n2024-01-01,B,100.0\n2024-01-02,A,150.0\n2024-01-02,B,50.0\n"""
    ).encode("utf-8")
    dataset_id = _upload_dataset(client, token, org_id, "zero_net.csv", csv_content)

    payload = {
        "metric_column": "val",
        "date_column": "date",
        "event_start": "2024-01-02",
        "event_end": "2024-01-02",
        "baseline_start": "2024-01-01",
        "baseline_end": "2024-01-01",
        "dimension_columns": ["cat"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["total_delta"] == 0.0
    assert data["contribution_status"] == "undefined_zero_net_change"
    assert "Total metric change is zero" in data["contribution_explanation"]

    drivers = data["primary_drivers"]
    assert len(drivers) == 2
    for d in drivers:
        assert d["contribution_pct"] is None
        if d["segment_value"] == "A":
            assert d["delta"] == 50.0
        elif d["segment_value"] == "B":
            assert d["delta"] == -50.0


def test_waterfall_reconciliation_exact(client: TestClient):
    _, token = _create_user_and_login(client, "rca_recon@example.com")
    org_id = _create_org(client, token, "Recon Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_recon_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
        "dimension_columns": ["category"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    recon = data["reconciliation"]
    assert recon["is_reconciled"] is True
    assert recon["discrepancy"] <= 1e-4
    assert abs(recon["total_metric_delta"] - recon["sum_segment_deltas_full"]) <= 1e-4
    assert recon["reconciliation_warning"] is None


def test_waterfall_reconciliation_pre_truncation(client: TestClient):
    _, token = _create_user_and_login(client, "rca_pretrunc@example.com")
    org_id = _create_org(client, token, "PreTrunc Org")

    # 40 categories
    rows = ["date,category,val"]
    for i in range(40):
        c = f"Cat_{i:02d}"
        rows.append(f"2024-01-01,{c},10.0")
        rows.append(f"2024-01-02,{c},{15.0 if c == 'Cat_00' else 8.0}")

    csv_content = "\n".join(rows).encode("utf-8")
    dataset_id = _upload_dataset(client, token, org_id, "pretrunc.csv", csv_content)

    payload = {
        "metric_column": "val",
        "date_column": "date",
        "event_start": "2024-01-02",
        "event_end": "2024-01-02",
        "dimension_columns": ["category"],
        "top_k_drivers": 5,
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    recon = data["reconciliation"]
    assert recon["is_reconciled"] is True
    assert recon["total_segments_count"] == 21  # 20 + "Other"
    assert recon["discrepancy"] <= 1e-4


def test_statistical_z_score_calculation(client: TestClient):
    _, token = _create_user_and_login(client, "rca_zscore@example.com")
    org_id = _create_org(client, token, "ZScore Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_z_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
        "baseline_start": "2024-01-05",
        "baseline_end": "2024-01-19",
        "dimension_columns": ["category"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    drivers = data["primary_drivers"]
    elec = next(d for d in drivers if d["segment_value"] == "Electronics")
    stat = elec["statistical_score"]
    assert stat["z_score"] is not None
    assert stat["z_score"] < -2.0
    assert stat["is_significant"] is True


def test_zero_and_near_zero_baseline_variance(client: TestClient):
    _, token = _create_user_and_login(client, "rca_zero_var@example.com")
    org_id = _create_org(client, token, "ZeroVar Org")

    rows = ["date,cat,val"]
    for i in range(1, 6):
        rows.append(f"2024-01-0{i},Fixed,50.0")
    rows.append("2024-01-06,Fixed,100.0")
    dataset_id = _upload_dataset(client, token, org_id, "zero_var.csv", "\n".join(rows).encode("utf-8"))

    payload = {
        "metric_column": "val",
        "date_column": "date",
        "event_start": "2024-01-06",
        "event_end": "2024-01-06",
        "baseline_start": "2024-01-01",
        "baseline_end": "2024-01-05",
        "dimension_columns": ["cat"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    d = data["primary_drivers"][0]
    stat = d["statistical_score"]

    assert stat["baseline_std"] == 0.0
    assert stat["z_score"] is None
    assert stat["is_significant"] is True
    assert "deterministic step shift" in stat["variance_note"]


def test_multidimensional_cardinality_and_ordering(client: TestClient):
    _, token = _create_user_and_login(client, "rca_multi@example.com")
    org_id = _create_org(client, token, "MultiCard Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_multi_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
        "dimension_columns": ["category", "region"],
        "top_k_drivers": 3,
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert len(data["dimension_breakdowns"]) == 2
    deltas = [abs(d["delta"]) for d in data["primary_drivers"]]
    assert deltas == sorted(deltas, reverse=True)


def test_secondary_metric_elasticity_and_direction(client: TestClient):
    _, token = _create_user_and_login(client, "rca_elast@example.com")
    org_id = _create_org(client, token, "Elast Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_elast_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
        "secondary_metrics": ["orders"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert len(data["secondary_metrics"]) == 1
    orders_impact = data["secondary_metrics"][0]
    assert orders_impact["metric_name"] == "orders"
    assert orders_impact["direction"] == "concordant"
    assert orders_impact["elasticity"] is not None
    assert orders_impact["elasticity"] > 0.0


def test_secondary_metric_elasticity_zero_denominators(client: TestClient):
    _, token = _create_user_and_login(client, "rca_elast_zero@example.com")
    org_id = _create_org(client, token, "ElastZero Org")

    rows = (
        """date,rev,qty\n2024-01-01,100.0,10.0\n2024-01-02,100.0,15.0\n"""
    ).encode("utf-8")
    dataset_id = _upload_dataset(client, token, org_id, "elast_zero.csv", rows)

    payload = {
        "metric_column": "rev",
        "date_column": "date",
        "event_start": "2024-01-02",
        "event_end": "2024-01-02",
        "baseline_start": "2024-01-01",
        "baseline_end": "2024-01-01",
        "secondary_metrics": ["qty"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    sec = data["secondary_metrics"][0]
    assert sec["elasticity"] is None
    assert sec["elasticity_status"] == "undefined_zero_primary_change"


def test_evidence_provenance_completeness(client: TestClient):
    _, token = _create_user_and_login(client, "rca_prov@example.com")
    org_id = _create_org(client, token, "Prov Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_prov_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
        "dimension_columns": ["category"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    driver = data["primary_drivers"][0]
    assert "dataset_id" in driver
    assert "event_window" in driver
    assert "baseline_window" in driver
    assert "metric_name" in driver
    assert "dimension" in driver
    assert "segment_value" in driver
    assert "event_value" in driver
    assert "baseline_value" in driver
    assert "delta" in driver
    assert "contribution_pct" in driver
    assert "statistical_score" in driver


def test_deterministic_template_narrative(client: TestClient):
    _, token = _create_user_and_login(client, "rca_narr@example.com")
    org_id = _create_org(client, token, "Narr Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_narr_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
        "dimension_columns": ["category"],
    }

    r1 = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    r2 = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )

    narr1 = r1.json()["narrative_summary"]
    narr2 = r2.json()["narrative_summary"]

    assert narr1 == narr2
    assert "Root-Cause Analysis for 'revenue'" in narr1
    assert "The primary driver was category='Electronics'" in narr1


def test_audit_log_entry_created(client: TestClient, db: Session):
    _, token = _create_user_and_login(client, "rca_audit@example.com")
    org_id = _create_org(client, token, "Audit Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_audit_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text

    audit = db.query(AuditLog).filter(
        AuditLog.action == "rca.executed",
        AuditLog.resource_id == uuid.UUID(dataset_id),
    ).first()

    assert audit is not None
    assert audit.organization_id == uuid.UUID(org_id)
    assert audit.meta["metric_name"] == "revenue"
    assert audit.meta["status"] == "success"
    assert "records" not in audit.meta
    assert "rows" not in audit.meta


def test_rbac_all_roles_can_execute_rca(client: TestClient):
    _, admin_token = _create_user_and_login(client, "rca_rbac_admin@example.com")
    org_id = _create_org(client, admin_token, "RBAC Org")
    dataset_id = _upload_dataset(client, admin_token, org_id, "rca_rbac_ds.csv", _make_rca_csv(30))

    roles = ["admin", "analyst", "manager", "viewer"]
    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
    }

    for role in roles:
        email = f"rca_{role}@example.com"
        _, role_token = _create_user_and_login(client, email)
        _add_member(client, admin_token, org_id, email, role)

        res = client.post(
            f"/datasets/{dataset_id}/rca/analyze",
            json=payload,
            headers=_auth_header(role_token),
        )
        assert res.status_code == 200, f"Role {role} failed: {res.text}"


def test_unauthenticated_returns_401(client: TestClient):
    random_id = uuid.uuid4()
    r = client.post(f"/datasets/{random_id}/rca/analyze", json={})
    assert r.status_code == 401


def test_cross_organization_dataset_rca_forbidden(client: TestClient):
    _, t1 = _create_user_and_login(client, "u1@example.com")
    _create_org(client, t1, "Org 1")

    _, t2 = _create_user_and_login(client, "u2@example.com")
    org2_id = _create_org(client, t2, "Org 2")
    ds2_id = _upload_dataset(client, t2, org2_id, "ds2.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
    }
    r = client.post(
        f"/datasets/{ds2_id}/rca/analyze",
        json=payload,
        headers=_auth_header(t1),
    )
    assert r.status_code == 403


def test_cross_organization_anomaly_rca_forbidden(client: TestClient, db: Session):
    _, t1 = _create_user_and_login(client, "u1_anom@example.com")
    org1_id = _create_org(client, t1, "Org 1")
    ds1_id = _upload_dataset(client, t1, org1_id, "ds1.csv", _make_rca_csv(30))

    _, t2 = _create_user_and_login(client, "u2_anom@example.com")
    org2_id = _create_org(client, t2, "Org 2")

    anom2 = Anomaly(
        id=uuid.uuid4(),
        organization_id=uuid.UUID(org2_id),
        metric_name="revenue",
        detected_at=datetime(2024, 1, 20, tzinfo=timezone.utc),
        severity="high",
    )
    db.add(anom2)
    db.commit()

    payload = {"anomaly_id": str(anom2.id)}
    r = client.post(
        f"/datasets/{ds1_id}/rca/analyze",
        json=payload,
        headers=_auth_header(t1),
    )
    assert r.status_code == 403


def test_unknown_anomaly_id_returns_404(client: TestClient):
    _, token = _create_user_and_login(client, "rca_unk_anom@example.com")
    org_id = _create_org(client, token, "Unk Anom Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_unk_anom_ds.csv", _make_rca_csv(30))

    fake_id = uuid.uuid4()
    payload = {"anomaly_id": str(fake_id)}
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 404


def test_unknown_dataset_id_returns_404(client: TestClient):
    _, token = _create_user_and_login(client, "rca_unk_ds@example.com")
    fake_id = uuid.uuid4()
    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
    }
    r = client.post(
        f"/datasets/{fake_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 404


def test_inverted_dates_rejected(client: TestClient):
    _, token = _create_user_and_login(client, "rca_inv@example.com")
    org_id = _create_org(client, token, "Inv Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_inv_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "revenue",
        "date_column": "date",
        "event_start": "2024-01-25",
        "event_end": "2024-01-20",
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code in (400, 422)


def test_non_existent_column_rejected(client: TestClient):
    _, token = _create_user_and_login(client, "rca_col_err@example.com")
    org_id = _create_org(client, token, "ColErr Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_col_ds.csv", _make_rca_csv(30))

    payload = {
        "metric_column": "non_existent_col",
        "date_column": "date",
        "event_start": "2024-01-20",
        "event_end": "2024-01-20",
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 400


def test_get_anomaly_rca_endpoint(client: TestClient, db: Session):
    _, token = _create_user_and_login(client, "rca_get_anom@example.com")
    org_id = _create_org(client, token, "GetAnom Org")
    dataset_id = _upload_dataset(client, token, org_id, "rca_get_anom_ds.csv", _make_rca_csv(30))

    anom = Anomaly(
        id=uuid.uuid4(),
        organization_id=uuid.UUID(org_id),
        dataset_id=uuid.UUID(dataset_id),
        metric_name="revenue",
        detected_at=datetime(2024, 1, 20, tzinfo=timezone.utc),
        severity="critical",
    )
    db.add(anom)
    db.commit()

    r = client.get(
        f"/datasets/{dataset_id}/rca/anomaly/{anom.id}",
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["anomaly_id"] == str(anom.id)
    assert data["event_window"]["start"] == "2024-01-20"


def test_volume_contribution_vs_statistical_unusualness(client: TestClient):
    _, token = _create_user_and_login(client, "rca_vol_vs_z@example.com")
    org_id = _create_org(client, token, "VolZ Org")

    rows = ["date,cat,val"]
    for i in range(1, 10):
        rows.append(f"2024-01-0{i},Huge,{10000.0 + (i * 100)}")
        rows.append(f"2024-01-0{i},Tiny,{10.0 + (i * 0.1)}")
    rows.append("2024-01-10,Huge,9000.0")
    rows.append("2024-01-10,Tiny,200.0")

    csv_content = "\n".join(rows).encode("utf-8")
    dataset_id = _upload_dataset(client, token, org_id, "vol_z.csv", csv_content)

    payload = {
        "metric_column": "val",
        "date_column": "date",
        "event_start": "2024-01-10",
        "event_end": "2024-01-10",
        "baseline_start": "2024-01-01",
        "baseline_end": "2024-01-09",
        "dimension_columns": ["cat"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    drivers = {d["segment_value"]: d for d in data["primary_drivers"]}
    assert "Huge" in drivers and "Tiny" in drivers
    assert abs(drivers["Huge"]["delta"]) > abs(drivers["Tiny"]["delta"])
    assert drivers["Tiny"]["statistical_score"]["z_score"] > 50.0
    assert drivers["Tiny"]["statistical_score"]["is_significant"] is True


def test_event_window_inclusive_semantics(client: TestClient):
    _, token = _create_user_and_login(client, "rca_inc@example.com")
    org_id = _create_org(client, token, "Inclusive Org")

    rows = (
        """date,cat,val\n2024-01-01 12:00:00,A,10.0\n2024-01-02 08:30:00,A,20.0\n2024-01-03 23:45:00,A,30.0\n"""
    ).encode("utf-8")
    dataset_id = _upload_dataset(client, token, org_id, "inc.csv", rows)

    payload = {
        "metric_column": "val",
        "date_column": "date",
        "event_start": "2024-01-02",
        "event_end": "2024-01-03",
        "baseline_start": "2024-01-01",
        "baseline_end": "2024-01-01",
        "dimension_columns": ["cat"],
    }
    r = client.post(
        f"/datasets/{dataset_id}/rca/analyze",
        json=payload,
        headers=_auth_header(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["event_window"]["value"] == 50.0
    assert data["baseline_window"]["value"] == 20.0
    assert data["total_delta"] == 30.0
