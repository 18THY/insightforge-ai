"""tests/test_profiler.py
======================
Comprehensive tests for Phase 7 Reusable Dataset Profiling Engine.

Validates:
  1. normal CSV profile
  2. normal XLSX profile
  3. numeric statistics (min, max, mean, median, std_dev, percentiles)
  4. categorical statistics (num_categories, top_categories, frequencies, percentages)
  5. datetime detection and ranges (min_date, max_date, date_range_days)
  6. missing values calculations (total missing cells, missing percentage, per column)
  7. duplicate rows calculations (count and percentage)
  8. datatype inference (integer, float, string, boolean, datetime)
  9. identifier detection heuristics (customer_id, order_id, product_id, codes vs continuous metrics)
 10. quality-score calculation and transparent components (completeness, uniqueness, consistency, date validity, reasonableness)
 11. empty dataset handling (HTTP 400)
 12. malformed CSV handling (HTTP 400)
 13. malformed XLSX handling (HTTP 400)
 14. invalid dates handling (unparseable / out-of-range dates reflected in invalid_date_count)
 15. cross-organization access prevention (HTTP 403)
 16. authenticated access across all roles (ADMIN, ANALYST, MANAGER, VIEWER can view profile)
 17. missing dataset handling (HTTP 404)
 18. multiple datasets independent profiling
 19. database schema sync (dataset_columns rows populated, dataset.status = "ready", dataset.row_count updated)
 20. missing storage file on disk handling (HTTP 404)
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import uuid
import openpyxl
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

PROFILER_TEST_TABLES = [
    User.__table__,
    AuthSession.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
    Dataset.__table__,
    DatasetColumn.__table__,
]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=PROFILER_TEST_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=PROFILER_TEST_TABLES)


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
    temp_upload_dir = tempfile.mkdtemp(prefix="insightforge_profiler_uploads_")
    monkeypatch.setattr(get_settings(), "upload_dir", temp_upload_dir)

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    shutil.rmtree(temp_upload_dir, ignore_errors=True)


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


def _create_org(client: TestClient, token: str, name: str = "Profiler Test Org") -> str:
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


def _sample_csv_content() -> bytes:
    return (
        b"order_id,customer_id,product_category,unit_price,quantity,order_date,is_gift\n"
        b"ORD-101,CUST-001,Electronics,1200.50,1,2024-01-15,true\n"
        b"ORD-102,CUST-002,Fashion,350.00,2,2024-02-10,false\n"
        b"ORD-103,CUST-001,Electronics,800.00,1,2024-03-05,false\n"
        b"ORD-104,CUST-003,Home & Kitchen,450.75,3,2024-03-20,true\n"
        b"ORD-105,CUST-004,Fashion,999.00,1,2024-04-01,false\n"
    )


def _sample_xlsx_content() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["product_id", "product_name", "price", "stock", "launch_date", "is_active"])
    ws.append(["PROD-1", "Laptop Pro", 85000.0, 15, "2023-05-01", True])
    ws.append(["PROD-2", "Wireless Mouse", 1200.0, 150, "2023-06-15", True])
    ws.append(["PROD-3", "USB-C Hub", 2500.0, 80, "2023-08-20", False])
    ws.append(["PROD-4", "Noise Cancelling Headphones", 14500.0, 45, "2023-11-10", True])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_normal_csv_profile(client: TestClient):
    """1. Normal CSV file profile generates complete structure."""
    _, token = _create_user_and_login(client, "prof_csv_admin@example.com")
    org_id = _create_org(client, token, "CSV Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders Dataset"},
        files={"file": ("orders.csv", io.BytesIO(_sample_csv_content()), "text/csv")},
    )
    assert up_resp.status_code == 201
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset_id"] == dataset_id
    assert data["row_count"] == 5
    assert data["column_count"] == 7
    assert len(data["columns"]) == 7
    assert "quality_score" in data
    assert data["quality_score"]["score"] >= 90.0


def test_normal_xlsx_profile(client: TestClient):
    """2. Normal XLSX file profile generates complete structure."""
    _, token = _create_user_and_login(client, "prof_xlsx_admin@example.com")
    org_id = _create_org(client, token, "XLSX Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Products Dataset"},
        files={
            "file": (
                "products.xlsx",
                io.BytesIO(_sample_xlsx_content()),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert up_resp.status_code == 201
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 4
    assert data["column_count"] == 6
    assert data["columns"][0]["name"] == "product_id"
    assert data["columns"][0]["classification"] == "identifier"


def test_numeric_statistics_calculation(client: TestClient):
    """3. Numeric statistics calculate accurate min, max, mean, median, std_dev, and percentiles."""
    _, token = _create_user_and_login(client, "num_stats_admin@example.com")
    org_id = _create_org(client, token, "Numeric Org")

    csv_data = (
        b"metric_id,score\n"
        b"1,10.0\n"
        b"2,20.0\n"
        b"3,30.0\n"
        b"4,40.0\n"
        b"5,50.0\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Numeric Data"},
        files={"file": ("numeric.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    score_col = next(c for c in resp.json()["columns"] if c["name"] == "score")

    assert score_col["classification"] == "numeric"
    assert score_col["inferred_datatype"] in ("float", "integer")
    stats = score_col["numeric_stats"]
    assert stats["min"] == 10.0
    assert stats["max"] == 50.0
    assert stats["mean"] == 30.0
    assert stats["median"] == 30.0
    assert stats["std_dev"] is not None
    assert stats["percentiles"]["p50"] == 30.0
    assert stats["percentiles"]["p25"] == 20.0
    assert stats["percentiles"]["p75"] == 40.0


def test_categorical_statistics_calculation(client: TestClient):
    """4. Categorical statistics compute categories, frequencies, and percentages."""
    _, token = _create_user_and_login(client, "cat_stats_admin@example.com")
    org_id = _create_org(client, token, "Categorical Org")

    csv_data = (
        b"id,city\n"
        b"1,Mumbai\n"
        b"2,Delhi\n"
        b"3,Mumbai\n"
        b"4,Bengaluru\n"
        b"5,Mumbai\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Cities Data"},
        files={"file": ("cities.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    city_col = next(c for c in resp.json()["columns"] if c["name"] == "city")

    assert city_col["classification"] == "categorical"
    cat_stats = city_col["categorical_stats"]
    assert cat_stats["num_categories"] == 3
    top = cat_stats["top_categories"]
    assert top[0]["value"] == "Mumbai"
    assert top[0]["count"] == 3
    assert top[0]["percentage"] == 60.0


def test_datetime_detection_and_ranges(client: TestClient):
    """5. Datetime columns are correctly detected with min/max and date_range_days."""
    _, token = _create_user_and_login(client, "dt_admin@example.com")
    org_id = _create_org(client, token, "Datetime Org")

    csv_data = (
        b"id,event_date\n"
        b"1,2024-01-01\n"
        b"2,2024-01-11\n"
        b"3,2024-01-31\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Timeline Data"},
        files={"file": ("timeline.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    dt_col = next(c for c in resp.json()["columns"] if c["name"] == "event_date")

    assert dt_col["classification"] == "datetime"
    dt_stats = dt_col["datetime_stats"]
    assert "2024-01-01" in dt_stats["min_date"]
    assert "2024-01-31" in dt_stats["max_date"]
    assert dt_stats["date_range_days"] == 30
    assert dt_stats["invalid_date_count"] == 0


def test_missing_values_detection(client: TestClient):
    """6. Missing values are counted globally and per-column."""
    _, token = _create_user_and_login(client, "null_admin@example.com")
    org_id = _create_org(client, token, "Missing Org")

    csv_data = (
        b"id,name,age\n"
        b"1,Alice,25\n"
        b"2,,30\n"
        b"3,Charlie,\n"
        b"4,David,40\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Nulls Data"},
        files={"file": ("nulls.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_missing_cells"] == 2
    assert data["missing_cells_percentage"] == round((2 / 12) * 100.0, 2)

    name_col = next(c for c in data["columns"] if c["name"] == "name")
    assert name_col["null_count"] == 1
    assert name_col["null_percentage"] == 25.0

    age_col = next(c for c in data["columns"] if c["name"] == "age")
    assert age_col["null_count"] == 1
    assert age_col["null_percentage"] == 25.0


def test_duplicate_rows_detection(client: TestClient):
    """7. Duplicate rows are detected and quantified."""
    _, token = _create_user_and_login(client, "dupe_admin@example.com")
    org_id = _create_org(client, token, "Dupes Org")

    csv_data = (
        b"id,value\n"
        b"1,100\n"
        b"2,200\n"
        b"2,200\n"
        b"3,300\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Duplicates Data"},
        files={"file": ("dupes.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 4
    assert data["duplicate_row_count"] == 1
    assert data["duplicate_row_percentage"] == 25.0


def test_datatype_inference(client: TestClient):
    """8. Inferred datatypes correctly identify integer, float, string, boolean, datetime."""
    _, token = _create_user_and_login(client, "types_admin@example.com")
    org_id = _create_org(client, token, "Types Org")

    csv_data = (
        b"int_val,float_val,str_val,bool_val,date_val\n"
        b"10,12.50,Alpha,true,2024-05-01\n"
        b"20,15.75,Beta,false,2024-05-02\n"
        b"30,18.00,Gamma,true,2024-05-03\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Types Dataset"},
        files={"file": ("types.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    cols = {c["name"]: c for c in resp.json()["columns"]}

    assert cols["int_val"]["inferred_datatype"] == "integer"
    assert cols["float_val"]["inferred_datatype"] == "float"
    assert cols["str_val"]["inferred_datatype"] == "string"
    assert cols["bool_val"]["inferred_datatype"] == "boolean"
    assert cols["date_val"]["inferred_datatype"] == "datetime"


def test_identifier_detection_heuristics(client: TestClient):
    """9. Transparent identifier heuristics detect customer_id, order_id, product_id; continuous metrics are not IDs."""
    _, token = _create_user_and_login(client, "id_heur_admin@example.com")
    org_id = _create_org(client, token, "Heuristic Org")

    csv_data = (
        b"order_id,customer_id,product_id,unit_price,total_spend\n"
        b"O-1,C-1,P-1,100.25,100.25\n"
        b"O-2,C-2,P-1,200.50,401.00\n"
        b"O-3,C-1,P-2,300.75,300.75\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "IDs Dataset"},
        files={"file": ("ids.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    cols = {c["name"]: c for c in resp.json()["columns"]}

    assert cols["order_id"]["classification"] == "identifier"
    assert cols["customer_id"]["classification"] == "identifier"
    assert cols["product_id"]["classification"] == "identifier"

    # Continuous metrics must NOT be classified as identifiers
    assert cols["unit_price"]["classification"] == "numeric"
    assert cols["total_spend"]["classification"] == "numeric"


def test_quality_score_calculation_formula(client: TestClient):
    """10. Data quality score follows documented weighted 5-dimension formula."""
    _, token = _create_user_and_login(client, "score_admin@example.com")
    org_id = _create_org(client, token, "Score Org")

    # Clean dataset with 0 nulls, 0 dupes, valid dates
    csv_data = (
        b"id,name,price,order_date\n"
        b"1,A,100.0,2024-01-01\n"
        b"2,B,200.0,2024-01-02\n"
        b"3,C,300.0,2024-01-03\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Clean Dataset"},
        files={"file": ("clean.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    q = resp.json()["quality_score"]

    assert q["score"] == 100.0
    assert q["grade"] == "Excellent"
    assert q["components"]["completeness"] == 100.0
    assert q["components"]["uniqueness"] == 100.0
    assert q["components"]["type_consistency"] == 100.0
    assert q["components"]["date_validity"] == 100.0
    assert q["components"]["reasonableness"] == 100.0
    assert "Completeness" in q["formula"]


def test_empty_dataset_handling(client: TestClient, monkeypatch):
    """11. Profiling an empty dataset returns HTTP 400."""
    _, token = _create_user_and_login(client, "empty_prof_admin@example.com")
    org_id = _create_org(client, token, "Empty Org")

    # Upload valid dataset first
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Empty Test"},
        files={"file": ("empty.csv", io.BytesIO(b"col1,col2\n1,2\n"), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # Overwrite the physical file with an empty file (simulating empty contents)
    from app.core.storage import get_upload_path
    upload_path = get_upload_path(uuid.UUID(org_id), uuid.UUID(dataset_id), "csv")
    with open(upload_path, "wb") as f:
        f.write(b"")

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_malformed_csv_handling(client: TestClient):
    """12. Malformed CSV in storage returns HTTP 400."""
    _, token = _create_user_and_login(client, "malformed_csv_admin@example.com")
    org_id = _create_org(client, token, "Malformed CSV Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Malformed CSV Test"},
        files={"file": ("test.csv", io.BytesIO(b"col1,col2\n1,2\n"), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # Overwrite file with invalid format
    from app.core.storage import get_upload_path
    upload_path = get_upload_path(uuid.UUID(org_id), uuid.UUID(dataset_id), "csv")
    with open(upload_path, "wb") as f:
        f.write(b"col1,col2\n1,2,3,4,5\n6\n\"unclosed quote")

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 400
    assert "malformed" in resp.json()["detail"].lower() or "error" in resp.json()["detail"].lower()


def test_malformed_xlsx_handling(client: TestClient):
    """13. Corrupted XLSX in storage returns HTTP 400."""
    _, token = _create_user_and_login(client, "malformed_xlsx_admin@example.com")
    org_id = _create_org(client, token, "Malformed XLSX Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Malformed XLSX Test"},
        files={
            "file": (
                "test.xlsx",
                io.BytesIO(_sample_xlsx_content()),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    dataset_id = up_resp.json()["id"]

    from app.core.storage import get_upload_path
    upload_path = get_upload_path(uuid.UUID(org_id), uuid.UUID(dataset_id), "xlsx")
    with open(upload_path, "wb") as f:
        f.write(b"corrupted binary data that is not zip")

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 400


def test_invalid_dates_handling(client: TestClient):
    """14. Invalid/unparseable dates are detected and penalized in quality score."""
    _, token = _create_user_and_login(client, "inv_date_admin@example.com")
    org_id = _create_org(client, token, "Invalid Date Org")

    csv_data = (
        b"id,order_date\n"
        b"1,2024-01-01\n"
        b"2,not-a-date\n"
        b"3,1800-05-20\n"  # out-of-range (< 1900)
        b"4,2024-02-15\n"
    )
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Invalid Dates"},
        files={"file": ("inv_dates.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200
    dt_col = next(c for c in resp.json()["columns"] if c["name"] == "order_date")

    assert dt_col["classification"] == "datetime"
    assert dt_col["datetime_stats"]["invalid_date_count"] >= 1
    assert resp.json()["quality_score"]["components"]["date_validity"] < 100.0


def test_cross_organization_access_forbidden(client: TestClient):
    """15. User from another organization cannot retrieve dataset profile (HTTP 403)."""
    _, token1 = _create_user_and_login(client, "org1_owner@example.com")
    org1 = _create_org(client, token1, "Org One")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token1),
        data={"organization_id": org1, "name": "Secret Dataset"},
        files={"file": ("secret.csv", io.BytesIO(_sample_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    _, token2 = _create_user_and_login(client, "intruder_user@example.com")
    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token2))
    assert resp.status_code == 403
    assert "not a member" in resp.json()["detail"].lower()


def test_authenticated_access_all_roles_permitted(client: TestClient):
    """16. All 4 canonical roles (ADMIN, ANALYST, MANAGER, VIEWER) can read profile."""
    _, admin_token = _create_user_and_login(client, "all_roles_admin@example.com")
    org_id = _create_org(client, admin_token, "RBAC Profile Org")

    # Create users for all other roles
    _, analyst_token = _create_user_and_login(client, "analyst_prof@example.com")
    _add_member(client, admin_token, org_id, "analyst_prof@example.com", "analyst")

    _, manager_token = _create_user_and_login(client, "manager_prof@example.com")
    _add_member(client, admin_token, org_id, "manager_prof@example.com", "manager")

    _, viewer_token = _create_user_and_login(client, "viewer_prof@example.com")
    _add_member(client, admin_token, org_id, "viewer_prof@example.com", "viewer")

    # Upload dataset
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(admin_token),
        data={"organization_id": org_id, "name": "Shared Dataset"},
        files={"file": ("shared.csv", io.BytesIO(_sample_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # All roles can get profile
    for token, role_name in [
        (admin_token, "ADMIN"),
        (analyst_token, "ANALYST"),
        (manager_token, "MANAGER"),
        (viewer_token, "VIEWER"),
    ]:
        resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
        assert resp.status_code == 200, f"Role {role_name} failed with status {resp.status_code}"
        assert resp.json()["row_count"] == 5


def test_missing_dataset_not_found(client: TestClient):
    """17. Non-existent dataset ID returns HTTP 404."""
    _, token = _create_user_and_login(client, "missing_admin@example.com")
    fake_id = uuid.uuid4()

    resp = client.get(f"/datasets/{fake_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_multiple_datasets_independent_profiling(client: TestClient):
    """18. Multiple datasets within an organization profile independently."""
    _, token = _create_user_and_login(client, "multi_admin@example.com")
    org_id = _create_org(client, token, "Multi Org")

    # Dataset 1 (5 rows, 7 cols)
    up1 = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Dataset 1"},
        files={"file": ("d1.csv", io.BytesIO(_sample_csv_content()), "text/csv")},
    )
    id1 = up1.json()["id"]

    # Dataset 2 (3 rows, 2 cols)
    d2_csv = b"code,count\nC1,10\nC2,20\nC3,30\n"
    up2 = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Dataset 2"},
        files={"file": ("d2.csv", io.BytesIO(d2_csv), "text/csv")},
    )
    id2 = up2.json()["id"]

    resp1 = client.get(f"/datasets/{id1}/profile", headers=_auth_header(token))
    resp2 = client.get(f"/datasets/{id2}/profile", headers=_auth_header(token))

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["row_count"] == 5
    assert resp2.json()["row_count"] == 3
    assert resp1.json()["column_count"] == 7
    assert resp2.json()["column_count"] == 2


def test_sync_dataset_columns_in_db(client: TestClient, db: Session):
    """19. Profiling synchronizes Dataset status to 'ready' and populates dataset_columns table."""
    _, token = _create_user_and_login(client, "sync_admin@example.com")
    org_id = _create_org(client, token, "Sync Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Sync Dataset"},
        files={"file": ("sync.csv", io.BytesIO(_sample_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # Initial status is 'uploaded'
    ds_before = db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))).scalar_one()
    assert ds_before.status == "uploaded"

    # Call profile
    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 200

    # Verify status changed to 'ready'
    db.expire_all()
    ds_after = db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))).scalar_one()
    assert ds_after.status == "ready"
    assert ds_after.row_count == 5

    # Verify dataset_columns populated
    columns = db.execute(
        select(DatasetColumn)
        .where(DatasetColumn.dataset_id == uuid.UUID(dataset_id))
        .order_by(DatasetColumn.ordinal_position)
    ).scalars().all()

    assert len(columns) == 7
    col_names = [c.name for c in columns]
    assert col_names == [
        "order_id",
        "customer_id",
        "product_category",
        "unit_price",
        "quantity",
        "order_date",
        "is_gift",
    ]


def test_missing_storage_file_returns_404(client: TestClient):
    """20. Missing physical storage file returns HTTP 404."""
    _, token = _create_user_and_login(client, "missing_file_admin@example.com")
    org_id = _create_org(client, token, "Missing File Org")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Deleted File Dataset"},
        files={"file": ("dfile.csv", io.BytesIO(_sample_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    # Delete physical file
    from app.core.storage import get_upload_path
    p = get_upload_path(uuid.UUID(org_id), uuid.UUID(dataset_id), "csv")
    if p.exists():
        p.unlink()

    resp = client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))
    assert resp.status_code == 404
    assert "not found in storage" in resp.json()["detail"].lower()
