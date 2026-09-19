"""tests/test_cleaner.py
====================
Comprehensive tests for Phase 8 Reusable Data-Cleaning Engine.

Validates:
   1. test_duplicate_detection
   2. test_duplicate_removal
   3. test_missing_numeric_values
   4. test_missing_categorical_values
   5. test_invalid_dates_handling
   6. test_datatype_conversion
   7. test_column_name_normalization
   8. test_categorical_normalization
   9. test_identifier_protection_no_imputation
  10. test_outlier_detection_iqr
  11. test_referential_integrity_checks
  12. test_preview_does_not_modify_raw_file
  13. test_apply_creates_processed_file
  14. test_raw_file_remains_unchanged_after_apply
  15. test_admin_allowed_on_apply
  16. test_analyst_allowed_on_apply
  17. test_manager_denied_on_apply (HTTP 403)
  18. test_viewer_denied_on_apply (HTTP 403)
  19. test_cross_organization_access_denied (HTTP 403)
  20. test_malformed_dataset_handling (HTTP 400)
  21. test_sync_dataset_columns_and_status_after_apply
  22. test_xlsx_input_converts_to_csv_processed_output
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import tempfile
import uuid
import openpyxl
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.storage import get_upload_path
from app.db.base import Base
from app.db.models.auth import AuthSession
from app.db.models.dataset import Dataset, DatasetColumn
from app.db.models.organization import Organization, OrganizationMember
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.schemas.cleaning import CleaningConfig
from app.services.cleaner import (
    normalize_all_columns,
    normalize_categories,
    normalize_column_name,
    run_cleaning_pipeline,
)

# ---------------------------------------------------------------------------
# Test database setup (in-memory SQLite)
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite://"

_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
)

CLEANER_TEST_TABLES = [
    User.__table__,
    AuthSession.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
    Dataset.__table__,
    DatasetColumn.__table__,
]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=CLEANER_TEST_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=CLEANER_TEST_TABLES)


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
    temp_upload_dir = tempfile.mkdtemp(prefix="insightforge_cleaner_uploads_")
    temp_processed_dir = tempfile.mkdtemp(prefix="insightforge_cleaner_processed_")
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


def _create_org(client: TestClient, token: str, name: str = "Cleaner Test Org") -> str:
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


def _dirty_csv_content() -> bytes:
    """CSV containing duplicates, missing values, inconsistent casing, outliers, placeholder IDs."""
    return (
        b"Order ID, Customer ID , Product Category , Unit Price , Quantity , Order Date\n"
        b"ORD-101,CUST-001,Electronics,100.0,1,2024-01-15\n"
        b"ORD-101,CUST-001,Electronics,100.0,1,2024-01-15\n"
        b"ORD-102,CUST-002,fashion,200.0,2,2024-02-10\n"
        b"ORD-103,CUST-003,Fashion,,1,2024-03-05\n"
        b"ORD-104,,Electronics,150.0,3,2024-03-20\n"
        b"ORD-105,CUST-004,ELECTRONICS,5000.0,1,invalid-date\n"
        b"ORD-106,PROD9999,Fashion,120.0,,2024-04-01\n"
    )


# ---------------------------------------------------------------------------
# Unit / Algorithm Tests
# ---------------------------------------------------------------------------

def test_column_name_normalization():
    """Test 7: Column name normalization and collision safety."""
    assert normalize_column_name(" Customer Name ") == "customer_name"
    assert normalize_column_name("Total $ Sales (2024)") == "total_sales_2024"
    assert normalize_column_name("___Leading__Trailing___") == "leading_trailing"
    assert normalize_column_name("") == "unnamed_col"

    df_collision = pd.DataFrame({
        "Col A": [1, 2],
        "col_a": [3, 4],
    })
    with pytest.raises(ValueError, match="Column name collision detected"):
        normalize_all_columns(df_collision)

    df_valid = pd.DataFrame({
        " Order ID ": [1],
        "Unit Price ($)": [20.0],
    })
    df_norm, mapping = normalize_all_columns(df_valid)
    assert list(df_norm.columns) == ["order_id", "unit_price"]
    assert mapping[" Order ID "] == "order_id"
    assert mapping["Unit Price ($)"] == "unit_price"


def test_categorical_normalization():
    """Test 8: Categorical whitespace stripping and casing reconciliation."""
    series = pd.Series([" Electronics ", "fashion", "Fashion", "ELECTRONICS", None, "fashion"])
    norm_series, cat_map = normalize_categories(series)

    assert norm_series.isna().sum() == 1
    assert "ELECTRONICS" in cat_map or "fashion" in cat_map
    assert not any(v.startswith(" ") or v.endswith(" ") for v in norm_series.dropna())


def test_duplicate_detection():
    """Test 1: Exact duplicates detected in dry-run preview without modification."""
    df = pd.DataFrame({
        "id": [1, 1, 2],
        "val": ["a", "a", "b"],
    })
    config = CleaningConfig(remove_duplicates=True)
    df_out, rows_before, rows_after_est, dup_cnt, dup_pct, *rest = run_cleaning_pipeline(
        df, config, is_preview=True
    )
    assert rows_before == 3
    assert rows_after_est == 2
    assert dup_cnt == 1
    assert dup_pct == pytest.approx(33.33, abs=0.1)
    assert len(df_out) == 3


def test_duplicate_removal():
    """Test 2: Exact duplicate rows dropped during execution."""
    df = pd.DataFrame({
        "id": [1, 1, 2],
        "val": ["a", "a", "b"],
    })
    config = CleaningConfig(remove_duplicates=True)
    df_out, rows_before, rows_after, dup_cnt, dup_pct, *rest = run_cleaning_pipeline(
        df, config, is_preview=False
    )
    assert rows_before == 3
    assert rows_after == 2
    assert dup_cnt == 1
    assert len(df_out) == 2


def test_missing_numeric_values():
    """Test 3: Missing numeric values imputed using median and mean."""
    df1 = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "score": [10.0, 20.0, 30.0, None],
    })
    config_median = CleaningConfig(numeric_strategy="median")
    df_med, _, _, _, _, missing_handled, *rest = run_cleaning_pipeline(
        df1, config_median, is_preview=False
    )
    assert missing_handled.get("score") == 1
    assert df_med["score"].iloc[3] == 20.0

    df2 = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "score": [10.0, 20.0, 60.0, None],
    })
    config_mean = CleaningConfig(numeric_strategy="mean")
    df_mean, _, _, _, _, missing_handled, *rest = run_cleaning_pipeline(
        df2, config_mean, is_preview=False
    )
    assert missing_handled.get("score") == 1
    assert df_mean["score"].iloc[3] == 30.0


def test_missing_categorical_values():
    """Test 4: Missing categorical values handled using mode and unknown."""
    df1 = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "city": ["Mumbai", "Delhi", "Mumbai", None],
    })
    config_mode = CleaningConfig(categorical_strategy="mode")
    df_mode, _, _, _, _, missing_handled, *rest = run_cleaning_pipeline(
        df1, config_mode, is_preview=False
    )
    assert missing_handled.get("city") == 1
    assert df_mode["city"].iloc[3] == "Mumbai"

    df2 = pd.DataFrame({
        "id": [1, 2, 3],
        "city": ["Mumbai", "Delhi", None],
    })
    config_unk = CleaningConfig(categorical_strategy="unknown")
    df_unk, _, _, _, _, missing_handled, *rest = run_cleaning_pipeline(
        df2, config_unk, is_preview=False
    )
    assert missing_handled.get("city") == 1
    assert df_unk["city"].iloc[2] == "Unknown"


def test_invalid_dates_handling():
    """Test 5: Unparseable dates are preserved as null, never invented."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "order_date": ["2024-01-01", "2024-02-01", "2024-03-01", "not-a-date", None],
    })
    config = CleaningConfig()
    df_clean, _, _, _, _, _, datatype_changes, *rest = run_cleaning_pipeline(
        df, config, is_preview=False
    )
    dt_change = next((c for c in datatype_changes if c.column == "order_date"), None)
    assert dt_change is not None
    assert dt_change.success_count == 3
    assert dt_change.failure_count == 1
    assert pd.isna(df_clean["order_date"].iloc[3])
    assert pd.isna(df_clean["order_date"].iloc[4])


def test_datatype_conversion():
    """Test 6: Datatype conversions and ISO 8601 formatting."""
    df = pd.DataFrame({
        "transaction_date": ["2023/12/01", "2024-05-10"],
        "amount_str": ["120.50", "99.00"],
    })
    config = CleaningConfig()
    df_clean, _, _, _, _, _, datatype_changes, *rest = run_cleaning_pipeline(
        df, config, is_preview=False
    )
    assert df_clean["transaction_date"].iloc[0] == "2023-12-01"
    assert df_clean["transaction_date"].iloc[1] == "2024-05-10"


def test_identifier_protection_no_imputation():
    """Test 9: Identifier columns are NEVER imputed with mean/median/mode."""
    df = pd.DataFrame({
        "customer_id": ["CUST-1", "CUST-2", None, "CUST-3"],
        "order_id": ["ORD-1", None, "ORD-3", "ORD-4"],
        "unit_price": [10.0, 20.0, 30.0, 40.0],
    })
    config = CleaningConfig(numeric_strategy="median", categorical_strategy="mode")
    df_clean, _, _, _, _, missing_handled, _, _, _, _, _, warnings, _ = run_cleaning_pipeline(
        df, config, is_preview=False
    )
    assert pd.isna(df_clean["customer_id"].iloc[2])
    assert pd.isna(df_clean["order_id"].iloc[1])
    assert "customer_id" not in missing_handled
    assert "order_id" not in missing_handled
    assert any("customer_id" in w and "NOT fabricated" in w for w in warnings)
    assert any("order_id" in w and "NOT fabricated" in w for w in warnings)


def test_outlier_detection_iqr():
    """Test 10: Outlier detection with IQR (1.5x) and optional capping."""
    data = [10.0] * 19 + [10000.0]
    df = pd.DataFrame({"id": range(20), "unit_price": data})

    config_detect = CleaningConfig(outlier_handling="detect_only")
    df_det, _, _, _, _, _, _, _, _, outliers_det, _, _, proposed = run_cleaning_pipeline(
        df, config_detect, is_preview=False
    )
    assert "unit_price" in outliers_det
    assert outliers_det["unit_price"].count == 1
    assert df_det["unit_price"].max() == 10000.0

    config_cap = CleaningConfig(outlier_handling="cap")
    df_cap, _, _, _, _, _, _, _, _, outliers_cap, _, _, _ = run_cleaning_pipeline(
        df, config_cap, is_preview=False
    )
    assert "unit_price" in outliers_cap
    upper_bound = outliers_cap["unit_price"].upper_bound
    assert df_cap["unit_price"].max() == upper_bound
    assert df_cap["unit_price"].max() < 10000.0


def test_referential_integrity_checks():
    """Test 11: Referential integrity flags null IDs and suspicious placeholder IDs."""
    df = pd.DataFrame({
        "product_id": ["PROD-1", "PROD9999", None, "PROD-2", "dummy_ref"],
        "order_id": ["ORD-1", "ORD-2", "ORD-3", "ORD-4", "ORD-5"],
    })
    config = CleaningConfig()
    _, _, _, _, _, _, _, _, _, _, referential_issues, _, _ = run_cleaning_pipeline(
        df, config, is_preview=False
    )
    assert "product_id" in referential_issues
    ref = referential_issues["product_id"]
    assert ref.missing_count == 1
    assert ref.invalid_reference_count >= 2


# ---------------------------------------------------------------------------
# API / Integration Tests
# ---------------------------------------------------------------------------

def test_preview_does_not_modify_raw_file(client: TestClient):
    """Test 12: Preview endpoint does NOT modify the raw stored file."""
    _, token = _create_user_and_login(client, "clean_admin12@example.com")
    org_id = _create_org(client, token, "Clean Org 12")

    raw_bytes = _dirty_csv_content()
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Dirty Orders"},
        files={"file": ("orders.csv", io.BytesIO(raw_bytes), "text/csv")},
    )
    assert up_resp.status_code == 201
    dataset_id = up_resp.json()["id"]

    prev_resp = client.post(
        f"/datasets/{dataset_id}/clean/preview",
        headers=_auth_header(token),
        json={"remove_duplicates": True, "numeric_strategy": "median"},
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["dataset_id"] == dataset_id
    assert prev_data["duplicates_detected"] == 1
    assert prev_data["rows_before"] == 7
    assert prev_data["rows_after_estimate"] == 6

    upload_path = os.path.join(get_settings().upload_dir, org_id, f"{dataset_id}.csv")
    with open(upload_path, "rb") as f:
        stored_bytes = f.read()
    assert hashlib.sha256(stored_bytes).hexdigest() == hashlib.sha256(raw_bytes).hexdigest()


def test_apply_creates_processed_file(client: TestClient):
    """Test 13: Apply endpoint persists cleaned file to processed directory."""
    _, token = _create_user_and_login(client, "clean_admin13@example.com")
    org_id = _create_org(client, token, "Clean Org 13")

    raw_bytes = _dirty_csv_content()
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Dirty Orders 13"},
        files={"file": ("orders.csv", io.BytesIO(raw_bytes), "text/csv")},
    )
    assert up_resp.status_code == 201
    dataset_id = up_resp.json()["id"]

    apply_resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(token),
        json={"remove_duplicates": True, "numeric_strategy": "median"},
    )
    assert apply_resp.status_code == 200
    report = apply_resp.json()
    assert report["dataset_id"] == dataset_id
    assert report["duplicates_removed"] == 1
    assert report["rows_after"] == 6
    assert report["output_location"] == f"data/processed/{org_id}/{dataset_id}.csv"

    proc_path = os.path.join(get_settings().processed_dir, org_id, f"{dataset_id}.csv")
    assert os.path.exists(proc_path)
    df_cleaned = pd.read_csv(proc_path)
    assert len(df_cleaned) == 6


def test_raw_file_remains_unchanged_after_apply(client: TestClient):
    """Test 14: Raw source file remains completely unchanged after cleaning apply."""
    _, token = _create_user_and_login(client, "clean_admin14@example.com")
    org_id = _create_org(client, token, "Clean Org 14")

    raw_bytes = _dirty_csv_content()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Dirty Orders 14"},
        files={"file": ("orders.csv", io.BytesIO(raw_bytes), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(token),
        json={},
    )

    upload_path = os.path.join(get_settings().upload_dir, org_id, f"{dataset_id}.csv")
    with open(upload_path, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    assert current_hash == raw_hash


def test_admin_allowed_on_apply(client: TestClient):
    """Test 15: ADMIN role is authorized to execute cleaning apply."""
    _, token = _create_user_and_login(client, "clean_admin15@example.com")
    org_id = _create_org(client, token, "Org 15")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Orders 15"},
        files={"file": ("orders.csv", io.BytesIO(_dirty_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(token),
        json={},
    )
    assert resp.status_code == 200


def test_analyst_allowed_on_apply(client: TestClient):
    """Test 16: ANALYST role is authorized to execute cleaning apply."""
    _, admin_token = _create_user_and_login(client, "clean_admin16@example.com")
    org_id = _create_org(client, admin_token, "Org 16")

    _, analyst_token = _create_user_and_login(client, "clean_analyst16@example.com")
    _add_member(client, admin_token, org_id, "clean_analyst16@example.com", "analyst")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(analyst_token),
        data={"organization_id": org_id, "name": "Orders 16"},
        files={"file": ("orders.csv", io.BytesIO(_dirty_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(analyst_token),
        json={},
    )
    assert resp.status_code == 200


def test_manager_denied_on_apply(client: TestClient):
    """Test 17: MANAGER role is denied (HTTP 403) on cleaning apply, but allowed on preview."""
    _, admin_token = _create_user_and_login(client, "clean_admin17@example.com")
    org_id = _create_org(client, admin_token, "Org 17")

    _, mgr_token = _create_user_and_login(client, "clean_mgr17@example.com")
    _add_member(client, admin_token, org_id, "clean_mgr17@example.com", "manager")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(admin_token),
        data={"organization_id": org_id, "name": "Orders 17"},
        files={"file": ("orders.csv", io.BytesIO(_dirty_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    prev_resp = client.post(
        f"/datasets/{dataset_id}/clean/preview",
        headers=_auth_header(mgr_token),
        json={},
    )
    assert prev_resp.status_code == 200

    apply_resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(mgr_token),
        json={},
    )
    assert apply_resp.status_code == 403


def test_viewer_denied_on_apply(client: TestClient):
    """Test 18: VIEWER role is denied (HTTP 403) on cleaning apply, but allowed on preview."""
    _, admin_token = _create_user_and_login(client, "clean_admin18@example.com")
    org_id = _create_org(client, admin_token, "Org 18")

    _, viewer_token = _create_user_and_login(client, "clean_viewer18@example.com")
    _add_member(client, admin_token, org_id, "clean_viewer18@example.com", "viewer")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(admin_token),
        data={"organization_id": org_id, "name": "Orders 18"},
        files={"file": ("orders.csv", io.BytesIO(_dirty_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    prev_resp = client.post(
        f"/datasets/{dataset_id}/clean/preview",
        headers=_auth_header(viewer_token),
        json={},
    )
    assert prev_resp.status_code == 200

    apply_resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(viewer_token),
        json={},
    )
    assert apply_resp.status_code == 403


def test_cross_organization_access_denied(client: TestClient):
    """Test 19: User belonging to Org B cannot preview or apply clean on Org A's dataset."""
    _, token_a = _create_user_and_login(client, "clean_a19@example.com")
    org_a = _create_org(client, token_a, "Org A 19")

    _, token_b = _create_user_and_login(client, "clean_b19@example.com")
    _create_org(client, token_b, "Org B 19")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token_a),
        data={"organization_id": org_a, "name": "Orders A"},
        files={"file": ("orders.csv", io.BytesIO(_dirty_csv_content()), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    prev_resp = client.post(
        f"/datasets/{dataset_id}/clean/preview",
        headers=_auth_header(token_b),
        json={},
    )
    assert prev_resp.status_code == 403

    apply_resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(token_b),
        json={},
    )
    assert apply_resp.status_code == 403


def test_malformed_dataset_handling(client: TestClient):
    """Test 20: Malformed/corrupt files in storage return HTTP 400 Bad Request."""
    _, token = _create_user_and_login(client, "clean_mal20@example.com")
    org_id = _create_org(client, token, "Malformed Org 20")

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Malformed CSV Test"},
        files={"file": ("test.csv", io.BytesIO(b"col1,col2\n1,2\n"), "text/csv")},
    )
    assert up_resp.status_code == 201
    dataset_id = up_resp.json()["id"]

    # Overwrite file with invalid format
    upload_path = get_upload_path(uuid.UUID(org_id), uuid.UUID(dataset_id), "csv")
    with open(upload_path, "wb") as f:
        f.write(b"col1,col2\n1,2,3,4,5\n6\n\"unclosed quote")

    resp = client.post(
        f"/datasets/{dataset_id}/clean/preview",
        headers=_auth_header(token),
        json={},
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_sync_dataset_columns_and_status_after_apply(client: TestClient, db: Session):
    """Test 21: dataset.processed_path is set, row_count updated, status='ready', and columns re-synced."""
    _, token = _create_user_and_login(client, "clean_sync21@example.com")
    org_id = _create_org(client, token, "Sync Org 21")

    raw_bytes = _dirty_csv_content()
    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Sync Orders"},
        files={"file": ("orders.csv", io.BytesIO(raw_bytes), "text/csv")},
    )
    dataset_id = up_resp.json()["id"]

    client.get(f"/datasets/{dataset_id}/profile", headers=_auth_header(token))

    apply_resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(token),
        json={"remove_duplicates": True, "numeric_strategy": "median"},
    )
    assert apply_resp.status_code == 200

    ds_row = db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))).scalar_one()
    assert ds_row.status == "ready"
    assert ds_row.row_count == 6
    assert ds_row.processed_path is not None
    assert f"data/processed/{org_id}/{dataset_id}.csv" in ds_row.processed_path

    col_rows = db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == uuid.UUID(dataset_id))
    ).scalars().all()
    col_names = {c.name for c in col_rows}
    assert "order_id" in col_names
    assert "customer_id" in col_names
    assert "product_category" in col_names
    assert "unit_price" in col_names


def test_xlsx_input_converts_to_csv_processed_output(client: TestClient, db: Session):
    """Test 22: XLSX input is intentionally converted to standardized CSV in processed storage."""
    _, token = _create_user_and_login(client, "clean_xlsx22@example.com")
    org_id = _create_org(client, token, "XLSX Org 22")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["Product ID", "Product Name", "Price", "Stock"])
    ws.append(["PROD-1", "Laptop Pro", 85000.0, 15])
    ws.append(["PROD-2", "Wireless Mouse", 1200.0, 150])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    up_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Products XLSX"},
        files={
            "file": (
                "products.xlsx",
                io.BytesIO(xlsx_bytes),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert up_resp.status_code == 201
    dataset_id = up_resp.json()["id"]
    assert up_resp.json()["file_type"] == "xlsx"

    raw_upload_path = os.path.join(get_settings().upload_dir, org_id, f"{dataset_id}.xlsx")
    assert os.path.exists(raw_upload_path)

    apply_resp = client.post(
        f"/datasets/{dataset_id}/clean/apply",
        headers=_auth_header(token),
        json={},
    )
    assert apply_resp.status_code == 200
    report = apply_resp.json()
    assert report["output_location"] == f"data/processed/{org_id}/{dataset_id}.csv"

    proc_path = os.path.join(get_settings().processed_dir, org_id, f"{dataset_id}.csv")
    assert os.path.exists(proc_path)
    df_proc = pd.read_csv(proc_path)
    assert len(df_proc) == 2
    assert list(df_proc.columns) == ["product_id", "product_name", "price", "stock"]

    with open(raw_upload_path, "rb") as f:
        stored_bytes = f.read()
    assert hashlib.sha256(stored_bytes).hexdigest() == hashlib.sha256(xlsx_bytes).hexdigest()

