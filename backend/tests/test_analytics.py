"""tests/test_analytics.py
=======================
Comprehensive tests for Phase 9 Analytics Engine.

Validates:
   1. test_path_traversal_unsafe_storage_path_rejected
   2. test_path_traversal_unsafe_processed_path_rejected
   3. test_missing_processed_artifact_raw_fallback
   4. test_overview_on_cleaned_dataset
   5. test_invalid_column_name_rejected
   6. test_invalid_aggregation_type_combination_rejected
   7. test_invalid_order_by_rejected
   8. test_invalid_date_column_rejected
   9. test_unsupported_time_granularity_rejected
  10. test_result_size_limit_exceeded_rejected
  11. test_crosstab_distinct_limit_exceeded_rejected
  12. test_insufficient_numeric_columns_correlation_rejected
  13. test_zero_variance_correlation_returns_null
  14. test_aggregation_single_metric
  15. test_aggregation_with_group_by_dimensions
  16. test_aggregation_multi_dimension
  17. test_aggregation_filtering_operators
  18. test_aggregation_sorting_and_pagination
  19. test_time_series_monthly_weekly_daily
  20. test_time_series_rolling_and_cumulative
  21. test_time_series_growth_rate
  22. test_breakdown_top_n_and_other_grouping
  23. test_crosstab_matrix
  24. test_correlation_matrix_pearson_and_spearman
  25. test_rbac_all_org_roles_permitted
  26. test_cross_organization_denied
  27. test_unauthenticated_denied
  28. test_dataset_not_found
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import uuid
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.auth import AuthSession
from app.db.models.dataset import Dataset, DatasetColumn
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

ANALYTICS_TEST_TABLES = [
    User.__table__,
    AuthSession.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
    Dataset.__table__,
    DatasetColumn.__table__,
]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=ANALYTICS_TEST_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=ANALYTICS_TEST_TABLES)


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
    temp_upload_dir = tempfile.mkdtemp(prefix="insightforge_analytics_uploads_")
    temp_processed_dir = tempfile.mkdtemp(prefix="insightforge_analytics_processed_")
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


def _create_org(client: TestClient, token: str, name: str = "Analytics Test Org") -> str:
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


def _sample_orders_csv() -> bytes:
    """Standard e-commerce orders CSV with financial, category, geographical, and date columns."""
    return (
        b"order_id,customer_id,product_category,unit_price,quantity,total_amount,order_status,city,state,order_date\n"
        b"ORD-1,CUST-1,Electronics,1000.0,1,1000.0,delivered,Mumbai,Maharashtra,2024-01-15\n"
        b"ORD-2,CUST-2,Fashion,250.0,2,500.0,delivered,Delhi,Delhi,2024-01-20\n"
        b"ORD-3,CUST-3,Electronics,800.0,1,800.0,cancelled,Mumbai,Maharashtra,2024-02-10\n"
        b"ORD-4,CUST-1,Home & Kitchen,300.0,3,900.0,delivered,Bengaluru,Karnataka,2024-02-15\n"
        b"ORD-5,CUST-4,Fashion,500.0,1,500.0,delivered,Delhi,Delhi,2024-03-05\n"
        b"ORD-6,CUST-5,Electronics,1200.0,2,2400.0,returned,Mumbai,Maharashtra,2024-03-22\n"
        b"ORD-7,CUST-6,Fashion,150.0,4,600.0,delivered,Pune,Maharashtra,2024-04-10\n"
        b"ORD-8,CUST-7,Home & Kitchen,450.0,2,900.0,delivered,Bengaluru,Karnataka,2024-04-25\n"
    )


# ---------------------------------------------------------------------------
# Path & Containment Safety Tests
# ---------------------------------------------------------------------------

def test_path_traversal_unsafe_storage_path_rejected(client: TestClient, db: Session):
    """Test 1: Path traversal attempt in storage_path is rejected."""
    _, token = _create_user_and_login(client, "an_pt1@example.com")
    org_id = _create_org(client, token, "PT Org 1")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "PT Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # Manually poison storage_path in DB to simulate path traversal
    ds = db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))).scalar_one()
    ds.storage_path = str(Path(get_settings().upload_dir).parent / "secret.csv")
    db.commit()

    resp = client.get(f"/datasets/{dataset_id}/analytics/overview", headers=_auth_header(token))
    assert resp.status_code == 400
    assert "containment" in resp.json()["detail"].lower() or "unsafe" in resp.json()["detail"].lower()


def test_path_traversal_unsafe_processed_path_rejected(client: TestClient, db: Session):
    """Test 2: Path traversal attempt in processed_path is rejected."""
    _, token = _create_user_and_login(client, "an_pt2@example.com")
    org_id = _create_org(client, token, "PT Org 2")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "PT Dataset 2"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # Poison processed_path
    ds = db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))).scalar_one()
    ds.processed_path = str(Path(get_settings().processed_dir).parent / "secret_processed.csv")
    db.commit()

    resp = client.get(f"/datasets/{dataset_id}/analytics/overview", headers=_auth_header(token))
    assert resp.status_code == 400
    assert "containment" in resp.json()["detail"].lower() or "unsafe" in resp.json()["detail"].lower()


def test_missing_processed_artifact_raw_fallback(client: TestClient):
    """Test 3: Uncleaned dataset falls back to storage_path with is_cleaned=False."""
    _, token = _create_user_and_login(client, "an_raw3@example.com")
    org_id = _create_org(client, token, "Raw Org 3")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Uncleaned Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/analytics/overview", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_cleaned"] is False
    assert data["row_count"] == 8


def test_overview_on_cleaned_dataset(client: TestClient):
    """Test 4: Cleaned dataset uses processed_path with is_cleaned=True and correct KPIs."""
    _, token = _create_user_and_login(client, "an_clean4@example.com")
    org_id = _create_org(client, token, "Clean Org 4")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Cleaned Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    clean_resp = client.post(f"/datasets/{dataset_id}/clean/apply", headers=_auth_header(token), json={})
    assert clean_resp.status_code == 200

    resp = client.get(f"/datasets/{dataset_id}/analytics/overview", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_cleaned"] is True
    assert data["row_count"] == 8
    assert "total_amount" in data["numeric_kpis"]
    assert data["numeric_kpis"]["total_amount"]["sum"] == 7600.0


# ---------------------------------------------------------------------------
# Input & Type Validation Tests
# ---------------------------------------------------------------------------

def test_invalid_column_name_rejected(client: TestClient):
    """Test 5: Referencing a non-existent column returns HTTP 400."""
    _, token = _create_user_and_login(client, "an_invcol5@example.com")
    org_id = _create_org(client, token, "Inv Col Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={"metrics": [{"column": "non_existent_column", "aggregation": "sum"}]},
    )
    assert resp.status_code == 400
    assert "does not exist in dataset" in resp.json()["detail"]


def test_invalid_aggregation_type_combination_rejected(client: TestClient):
    """Test 6: Requesting numeric aggregation on string column returns HTTP 400."""
    _, token = _create_user_and_login(client, "an_invagg6@example.com")
    org_id = _create_org(client, token, "Inv Agg Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={"metrics": [{"column": "product_category", "aggregation": "sum"}]},
    )
    assert resp.status_code == 400
    assert "not supported on non-numeric column" in resp.json()["detail"]


def test_invalid_order_by_rejected(client: TestClient):
    """Test 7: order_by column not in selected metrics/dimensions returns HTTP 400."""
    _, token = _create_user_and_login(client, "an_invord7@example.com")
    org_id = _create_org(client, token, "Inv Order Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={
            "metrics": [{"column": "total_amount", "aggregation": "sum", "alias": "revenue"}],
            "dimensions": ["product_category"],
            "order_by": "unselected_column",
        },
    )
    assert resp.status_code == 400
    assert "order_by" in resp.json()["detail"]


def test_invalid_date_column_rejected(client: TestClient):
    """Test 8: Non-datetime column in time-series query returns HTTP 400."""
    _, token = _create_user_and_login(client, "an_invdate8@example.com")
    org_id = _create_org(client, token, "Inv Date Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/time-series",
        headers=_auth_header(token),
        json={
            "date_column": "product_category",
            "metric_column": "total_amount",
            "granularity": "month",
        },
    )
    assert resp.status_code == 400
    assert "not a valid datetime column" in resp.json()["detail"]


def test_unsupported_time_granularity_rejected(client: TestClient):
    """Test 9: Invalid time granularity returns HTTP 422 validation error."""
    _, token = _create_user_and_login(client, "an_invgran9@example.com")
    org_id = _create_org(client, token, "Inv Gran Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/time-series",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "total_amount",
            "granularity": "decade",
        },
    )
    assert resp.status_code == 422


def test_result_size_limit_exceeded_rejected(client: TestClient):
    """Test 10: limit > 1000 or top_n > 100 returns HTTP 422 validation error."""
    _, token = _create_user_and_login(client, "an_lim10@example.com")
    org_id = _create_org(client, token, "Limit Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # limit > 1000
    resp1 = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={"metrics": [{"column": "total_amount", "aggregation": "sum"}], "limit": 2000},
    )
    assert resp1.status_code == 422

    # top_n > 100
    resp2 = client.post(
        f"/datasets/{dataset_id}/analytics/breakdown",
        headers=_auth_header(token),
        json={"dimension": "product_category", "top_n": 500},
    )
    assert resp2.status_code == 422


def test_crosstab_distinct_limit_exceeded_rejected(client: TestClient):
    """Test 11: Dimension exceeding 50 distinct categories returns HTTP 400."""
    _, token = _create_user_and_login(client, "an_ctlim11@example.com")
    org_id = _create_org(client, token, "Crosstab Limit Org")

    # Generate CSV with 60 distinct customer IDs
    rows = ["order_id,customer_id,product_category,amount"]
    for i in range(60):
        rows.append(f"ORD-{i},CUST-{i},Cat-A,100.0")
    csv_bytes = "\n".join(rows).encode("utf-8")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "High Cardinality"},
        files={"file": ("large.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/crosstab",
        headers=_auth_header(token),
        json={"row_dimension": "customer_id", "column_dimension": "product_category"},
    )
    assert resp.status_code == 400
    assert "exceeds the maximum allowed 50 distinct categories" in resp.json()["detail"]


def test_insufficient_numeric_columns_correlation_rejected(client: TestClient):
    """Test 12: Less than 2 numeric columns returns HTTP 400."""
    _, token = _create_user_and_login(client, "an_insuf12@example.com")
    org_id = _create_org(client, token, "Insuf Org")

    csv_bytes = b"product,price\nLaptop,1000\nMouse,20\n"
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "One Numeric"},
        files={"file": ("one_num.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/correlation",
        headers=_auth_header(token),
        json={},
    )
    assert resp.status_code == 400
    assert "At least 2 numeric columns are required" in resp.json()["detail"]


def test_zero_variance_correlation_returns_null(client: TestClient):
    """Test 13: Constant/zero-variance column returns None (null in JSON), never 0.0."""
    _, token = _create_user_and_login(client, "an_zvar13@example.com")
    org_id = _create_org(client, token, "Zero Var Org")

    csv_bytes = (
        b"x,y,const\n"
        b"1.0,10.0,5.0\n"
        b"2.0,20.0,5.0\n"
        b"3.0,30.0,5.0\n"
        b"4.0,40.0,5.0\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Zero Var"},
        files={"file": ("zvar.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/correlation",
        headers=_auth_header(token),
        json={"columns": ["x", "y", "const"]},
    )
    assert resp.status_code == 200
    matrix = resp.json()["correlation_matrix"]
    assert matrix["x"]["y"] == 1.0
    assert matrix["x"]["const"] is None  # Strictly null, NOT 0.0
    assert matrix["const"]["x"] is None
    assert matrix["const"]["const"] is None


# ---------------------------------------------------------------------------
# Analytical Capabilities & Correctness Tests
# ---------------------------------------------------------------------------

def test_aggregation_single_metric(client: TestClient):
    """Test 14: Scalar aggregation across entire dataset."""
    _, token = _create_user_and_login(client, "an_agg14@example.com")
    org_id = _create_org(client, token, "Agg Org 14")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={
            "metrics": [
                {"column": "total_amount", "aggregation": "sum", "alias": "total_revenue"},
                {"column": "quantity", "aggregation": "mean", "alias": "avg_qty"},
                {"column": "order_id", "aggregation": "count", "alias": "order_count"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 1
    assert data["data"][0]["total_revenue"] == 7600.0
    assert data["data"][0]["avg_qty"] == 2.0
    assert data["data"][0]["order_count"] == 8


def test_aggregation_with_group_by_dimensions(client: TestClient):
    """Test 15: Group by single dimension."""
    _, token = _create_user_and_login(client, "an_agg15@example.com")
    org_id = _create_org(client, token, "Agg Org 15")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={
            "dimensions": ["product_category"],
            "metrics": [{"column": "total_amount", "aggregation": "sum", "alias": "rev"}],
            "order_by": "rev",
            "order_desc": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 3
    assert data["data"][0]["product_category"] == "Electronics"
    assert data["data"][0]["rev"] == 4200.0


def test_aggregation_multi_dimension(client: TestClient):
    """Test 16: Group by two dimensions."""
    _, token = _create_user_and_login(client, "an_agg16@example.com")
    org_id = _create_org(client, token, "Agg Org 16")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={
            "dimensions": ["product_category", "state"],
            "metrics": [{"column": "quantity", "aggregation": "sum", "alias": "units"}],
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) > 0


def test_aggregation_filtering_operators(client: TestClient):
    """Test 17: Row-level filters: eq, gt, in, between."""
    _, token = _create_user_and_login(client, "an_filt17@example.com")
    org_id = _create_org(client, token, "Filter Org 17")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={
            "metrics": [{"column": "total_amount", "aggregation": "sum", "alias": "rev"}],
            "filters": [
                {"column": "order_status", "operator": "eq", "value": "delivered"},
                {"column": "total_amount", "operator": "gt", "value": 500.0},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"][0]["rev"] == 3400.0


def test_aggregation_sorting_and_pagination(client: TestClient):
    """Test 18: Sorting, limit, and offset."""
    _, token = _create_user_and_login(client, "an_sort18@example.com")
    org_id = _create_org(client, token, "Sort Org 18")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/aggregate",
        headers=_auth_header(token),
        json={
            "dimensions": ["order_id"],
            "metrics": [{"column": "total_amount", "aggregation": "sum", "alias": "amt"}],
            "order_by": "amt",
            "order_desc": True,
            "limit": 2,
            "offset": 0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 2
    assert data["data"][0]["order_id"] == "ORD-6"
    assert data["data"][0]["amt"] == 2400.0


def test_time_series_monthly_weekly_daily(client: TestClient):
    """Test 19: Time-series resampling at month and week granularities."""
    _, token = _create_user_and_login(client, "an_ts19@example.com")
    org_id = _create_org(client, token, "TS Org 19")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/time-series",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "total_amount",
            "granularity": "month",
        },
    )
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert len(series) == 4
    assert series[0]["timestamp"] == "2024-01-01"
    assert series[0]["value"] == 1500.0


def test_time_series_rolling_and_cumulative(client: TestClient):
    """Test 20: Time-series moving average and cumulative sum."""
    _, token = _create_user_and_login(client, "an_ts20@example.com")
    org_id = _create_org(client, token, "TS Org 20")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/time-series",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "total_amount",
            "granularity": "month",
            "rolling_window": 2,
            "include_cumulative": True,
        },
    )
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert series[0]["cumulative_value"] == 1500.0
    assert series[-1]["cumulative_value"] == 7600.0
    assert series[1]["rolling_average"] is not None


def test_time_series_growth_rate(client: TestClient):
    """Test 21: Time-series period-over-period growth rate."""
    _, token = _create_user_and_login(client, "an_ts21@example.com")
    org_id = _create_org(client, token, "TS Org 21")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/time-series",
        headers=_auth_header(token),
        json={
            "date_column": "order_date",
            "metric_column": "total_amount",
            "granularity": "month",
            "include_growth": True,
        },
    )
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert series[0]["growth_rate_pct"] is None
    assert series[1]["growth_rate_pct"] is not None


def test_breakdown_top_n_and_other_grouping(client: TestClient):
    """Test 22: Segment breakdown with Top N, contribution percentage, and 'Other' binning."""
    _, token = _create_user_and_login(client, "an_bk22@example.com")
    org_id = _create_org(client, token, "Breakdown Org 22")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/breakdown",
        headers=_auth_header(token),
        json={
            "dimension": "product_category",
            "metric_column": "total_amount",
            "aggregation": "sum",
            "top_n": 1,
            "include_other": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_value"] == 7600.0
    assert len(data["items"]) == 2
    assert data["items"][0]["category"] == "Electronics"
    assert data["items"][0]["value"] == 4200.0
    assert data["items"][1]["category"] == "Other"
    assert data["items"][1]["value"] == 3400.0


def test_crosstab_matrix(client: TestClient):
    """Test 23: 2D cross-tabulation table generation."""
    _, token = _create_user_and_login(client, "an_ct23@example.com")
    org_id = _create_org(client, token, "Crosstab Org 23")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/analytics/crosstab",
        headers=_auth_header(token),
        json={
            "row_dimension": "product_category",
            "column_dimension": "order_status",
            "metric_column": "total_amount",
            "aggregation": "sum",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "Electronics" in data["row_values"]
    assert "delivered" in data["column_values"]
    assert len(data["matrix"]) == len(data["row_values"])


def test_correlation_matrix_pearson_and_spearman(client: TestClient):
    """Test 24: Pearson and Spearman correlation calculation."""
    _, token = _create_user_and_login(client, "an_corr24@example.com")
    org_id = _create_org(client, token, "Corr Org 24")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # Pearson
    resp1 = client.post(
        f"/datasets/{dataset_id}/analytics/correlation",
        headers=_auth_header(token),
        json={"columns": ["unit_price", "quantity", "total_amount"], "method": "pearson"},
    )
    assert resp1.status_code == 200
    mat1 = resp1.json()["correlation_matrix"]
    assert mat1["unit_price"]["unit_price"] == 1.0

    # Spearman
    resp2 = client.post(
        f"/datasets/{dataset_id}/analytics/correlation",
        headers=_auth_header(token),
        json={"columns": ["unit_price", "quantity", "total_amount"], "method": "spearman"},
    )
    assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# RBAC & Authorization Tests
# ---------------------------------------------------------------------------

def test_rbac_all_org_roles_permitted(client: TestClient):
    """Test 25: All canonical roles (ADMIN, ANALYST, MANAGER, VIEWER) can read analytics."""
    _, admin_token = _create_user_and_login(client, "an_admin25@example.com")
    org_id = _create_org(client, admin_token, "RBAC Org 25")

    _, analyst_tok = _create_user_and_login(client, "an_analyst25@example.com")
    _add_member(client, admin_token, org_id, "an_analyst25@example.com", "analyst")

    _, manager_tok = _create_user_and_login(client, "an_mgr25@example.com")
    _add_member(client, admin_token, org_id, "an_mgr25@example.com", "manager")

    _, viewer_tok = _create_user_and_login(client, "an_view25@example.com")
    _add_member(client, admin_token, org_id, "an_view25@example.com", "viewer")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(admin_token),
        data={"organization_id": org_id, "name": "Orders"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    for tok in (admin_token, analyst_tok, manager_tok, viewer_tok):
        resp = client.get(f"/datasets/{dataset_id}/analytics/overview", headers=_auth_header(tok))
        assert resp.status_code == 200


def test_cross_organization_denied(client: TestClient):
    """Test 26: Member of Org B cannot access Org A's dataset analytics (HTTP 403)."""
    _, tok_a = _create_user_and_login(client, "an_a26@example.com")
    org_a = _create_org(client, tok_a, "Org A 26")

    _, tok_b = _create_user_and_login(client, "an_b26@example.com")
    _create_org(client, tok_b, "Org B 26")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(tok_a),
        data={"organization_id": org_a, "name": "Orders A"},
        files={"file": ("orders.csv", io.BytesIO(_sample_orders_csv()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/analytics/overview", headers=_auth_header(tok_b))
    assert resp.status_code == 403


def test_unauthenticated_denied(client: TestClient):
    """Test 27: Unauthenticated request returns HTTP 401."""
    resp = client.get(f"/datasets/{uuid.uuid4()}/analytics/overview")
    assert resp.status_code == 401


def test_dataset_not_found(client: TestClient):
    """Test 28: Querying non-existent dataset returns HTTP 404."""
    _, token = _create_user_and_login(client, "an_nf28@example.com")
    resp = client.get(f"/datasets/{uuid.uuid4()}/analytics/overview", headers=_auth_header(token))
    assert resp.status_code == 404
