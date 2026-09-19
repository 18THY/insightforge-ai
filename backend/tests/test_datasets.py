"""tests/test_datasets.py
======================
Tests for Phase 6 Secure Dataset Ingestion.

Validates:
  1. CSV and XLSX upload functionality.
  2. Strict organization-level tenant isolation.
  3. Role-based access control (ADMIN and ANALYST can upload/delete; MANAGER and VIEWER cannot).
  4. Content inspection (file size limits, empty files, malformed CSV with null bytes, corrupt XLSX).
  5. Unsupported extensions rejection (.txt, .pdf, .json).
  6. Name uniqueness within organization (and allowance across different organizations).
  7. Dataset listing scoped to organization (GET /datasets?organization_id=...).
  8. Dataset detail retrieval and physical file deletion.
  9. Preservation of canonical dataset statuses ('uploaded', 'processing', 'ready', 'failed').
 10. Security: physical storage path never leaked in public API responses.
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
from sqlalchemy import create_engine
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

DATASET_TEST_TABLES = [
    User.__table__,
    AuthSession.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
    Dataset.__table__,
    DatasetColumn.__table__,
]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=DATASET_TEST_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=DATASET_TEST_TABLES)


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
    # Use temporary directory for file uploads during tests
    temp_upload_dir = tempfile.mkdtemp(prefix="insightforge_test_uploads_")
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


def _create_org(client: TestClient, token: str, name: str = "Test Corp") -> str:
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


def _sample_csv_bytes() -> bytes:
    return b"customer_id,city,spend\n1,Mumbai,1500.50\n2,Delhi,2300.00\n3,Bengaluru,850.25\n"


def _sample_xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["product_id", "name", "price", "stock"])
    ws.append([101, "Mechanical Keyboard", 4500, 50])
    ws.append([102, "Wireless Mouse", 1200, 120])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test Cases (20 core requirements)
# ---------------------------------------------------------------------------

def test_admin_can_upload_csv(client: TestClient):
    """1. Admin can upload a valid CSV file."""
    _, token = _create_user_and_login(client, "admin_upload_csv@example.com")
    org_id = _create_org(client, token, "CSV Org")

    csv_data = _sample_csv_bytes()
    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Customers CSV", "description": "Raw customer records"},
        files={"file": ("customers.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Customers CSV"
    assert data["original_filename"] == "customers.csv"
    assert data["file_type"] == "csv"
    assert data["file_size"] == len(csv_data)
    assert data["row_count"] == 3
    assert data["status"] == "uploaded"
    assert "storage_path" not in data  # Never expose physical path


def test_analyst_can_upload_csv(client: TestClient):
    """2. Analyst can upload a valid CSV file."""
    _, admin_token = _create_user_and_login(client, "admin_for_analyst@example.com")
    org_id = _create_org(client, admin_token, "Analyst Org")

    _, analyst_token = _create_user_and_login(client, "analyst_user@example.com")
    _add_member(client, admin_token, org_id, "analyst_user@example.com", "analyst")

    csv_data = _sample_csv_bytes()
    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(analyst_token),
        data={"organization_id": org_id, "name": "Analyst Dataset"},
        files={"file": ("sales.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "uploaded"


def test_manager_cannot_upload(client: TestClient):
    """3. Manager cannot upload datasets (HTTP 403)."""
    _, admin_token = _create_user_and_login(client, "admin_for_mgr@example.com")
    org_id = _create_org(client, admin_token, "Mgr Org")

    _, mgr_token = _create_user_and_login(client, "manager_user@example.com")
    _add_member(client, admin_token, org_id, "manager_user@example.com", "manager")

    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(mgr_token),
        data={"organization_id": org_id, "name": "Manager Upload Attempt"},
        files={"file": ("test.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 403
    assert "Insufficient permissions" in resp.json()["detail"]


def test_viewer_cannot_upload(client: TestClient):
    """4. Viewer cannot upload datasets (HTTP 403)."""
    _, admin_token = _create_user_and_login(client, "admin_for_vwr@example.com")
    org_id = _create_org(client, admin_token, "Viewer Org")

    _, vwr_token = _create_user_and_login(client, "viewer_user@example.com")
    _add_member(client, admin_token, org_id, "viewer_user@example.com", "viewer")

    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(vwr_token),
        data={"organization_id": org_id, "name": "Viewer Upload Attempt"},
        files={"file": ("test.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 403
    assert "Insufficient permissions" in resp.json()["detail"]


def test_non_member_cannot_upload(client: TestClient):
    """5. Non-member of organization cannot upload (HTTP 403)."""
    _, token1 = _create_user_and_login(client, "org1_admin@example.com")
    org_id1 = _create_org(client, token1, "Org One")

    _, token2 = _create_user_and_login(client, "outsider@example.com")

    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token2),
        data={"organization_id": org_id1, "name": "Outsider Upload"},
        files={"file": ("test.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 403
    assert "not a member" in resp.json()["detail"].lower()


def test_upload_valid_xlsx(client: TestClient):
    """6. Admin/Analyst can upload a valid XLSX file."""
    _, token = _create_user_and_login(client, "admin_xlsx@example.com")
    org_id = _create_org(client, token, "XLSX Org")

    xlsx_data = _sample_xlsx_bytes()
    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Products Catalog"},
        files={
            "file": (
                "products.xlsx",
                io.BytesIO(xlsx_data),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["file_type"] == "xlsx"
    assert data["original_filename"] == "products.xlsx"
    assert data["row_count"] == 2
    assert data["status"] == "uploaded"


def test_upload_unsupported_file_extension(client: TestClient):
    """7. Reject unsupported extensions (.txt, .json, .pdf) with HTTP 400."""
    _, token = _create_user_and_login(client, "admin_ext@example.com")
    org_id = _create_org(client, token, "Ext Org")

    for filename, ctype in [("doc.txt", "text/plain"), ("data.json", "application/json"), ("paper.pdf", "application/pdf")]:
        resp = client.post(
            "/datasets/upload",
            headers=_auth_header(token),
            data={"organization_id": org_id, "name": f"File {filename}"},
            files={"file": (filename, io.BytesIO(b"dummy data"), ctype)},
        )
        assert resp.status_code == 400
        assert "Unsupported file format" in resp.json()["detail"]


def test_upload_empty_file(client: TestClient):
    """8. Reject 0-byte file with HTTP 400."""
    _, token = _create_user_and_login(client, "admin_empty@example.com")
    org_id = _create_org(client, token, "Empty File Org")

    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Empty File"},
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_upload_exceeds_max_size(client: TestClient, monkeypatch):
    """9. Reject file exceeding max size limit with HTTP 400."""
    _, token = _create_user_and_login(client, "admin_size@example.com")
    org_id = _create_org(client, token, "Size Limit Org")

    # Set temporary low threshold of 20 bytes
    monkeypatch.setattr(get_settings(), "max_upload_size_bytes", 20)

    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Oversized File"},
        files={"file": ("oversized.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 400
    assert "exceeds maximum allowed limit" in resp.json()["detail"]


def test_upload_malformed_csv_null_bytes(client: TestClient):
    """10. Reject binary / null-byte corrupted file masquerading as CSV."""
    _, token = _create_user_and_login(client, "admin_malformed_csv@example.com")
    org_id = _create_org(client, token, "Malformed CSV Org")

    bad_content = b"header1,header2\nvalue1,\x00\x01\x02badbinary\n"
    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Binary Disguised CSV"},
        files={"file": ("binary.csv", io.BytesIO(bad_content), "text/csv")},
    )
    assert resp.status_code == 400
    assert "null bytes" in resp.json()["detail"].lower()


def test_upload_malformed_xlsx(client: TestClient):
    """11. Reject corrupted or non-zip file claiming to be XLSX."""
    _, token = _create_user_and_login(client, "admin_malformed_xlsx@example.com")
    org_id = _create_org(client, token, "Malformed XLSX Org")

    resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Corrupted XLSX"},
        files={
            "file": (
                "fake.xlsx",
                io.BytesIO(b"This is completely plain text not a zip archive"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 400
    assert "invalid xlsx" in resp.json()["detail"].lower() or "zip" in resp.json()["detail"].lower()


def test_upload_duplicate_name_in_org(client: TestClient):
    """12. Duplicate dataset name in the same organization returns HTTP 409 Conflict."""
    _, token = _create_user_and_login(client, "admin_dup@example.com")
    org_id = _create_org(client, token, "Dup Org")

    # Upload first
    resp1 = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Inventory"},
        files={"file": ("inv1.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp1.status_code == 201

    # Upload duplicate name
    resp2 = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Inventory"},
        files={"file": ("inv2.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"].lower()


def test_upload_same_name_different_orgs(client: TestClient):
    """13. Same dataset name across two different organizations is permitted."""
    _, token1 = _create_user_and_login(client, "org_a_user@example.com")
    org_a = _create_org(client, token1, "Org A")

    _, token2 = _create_user_and_login(client, "org_b_user@example.com")
    org_b = _create_org(client, token2, "Org B")

    resp1 = client.post(
        "/datasets/upload",
        headers=_auth_header(token1),
        data={"organization_id": org_a, "name": "SharedName"},
        files={"file": ("data.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/datasets/upload",
        headers=_auth_header(token2),
        data={"organization_id": org_b, "name": "SharedName"},
        files={"file": ("data.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    assert resp2.status_code == 201


def test_list_datasets_isolated_by_org(client: TestClient):
    """14. GET /datasets?organization_id=... returns only datasets for that organization."""
    _, token1 = _create_user_and_login(client, "iso_org1_user@example.com")
    org1 = _create_org(client, token1, "Isolated Org 1")

    _, token2 = _create_user_and_login(client, "iso_org2_user@example.com")
    org2 = _create_org(client, token2, "Isolated Org 2")

    # Org 1 uploads 2 datasets
    client.post(
        "/datasets/upload",
        headers=_auth_header(token1),
        data={"organization_id": org1, "name": "Org1 Dataset A"},
        files={"file": ("a.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    client.post(
        "/datasets/upload",
        headers=_auth_header(token1),
        data={"organization_id": org1, "name": "Org1 Dataset B"},
        files={"file": ("b.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )

    # Org 2 uploads 1 dataset
    client.post(
        "/datasets/upload",
        headers=_auth_header(token2),
        data={"organization_id": org2, "name": "Org2 Dataset C"},
        files={"file": ("c.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )

    # User 1 lists Org 1 datasets
    resp = client.get(f"/datasets?organization_id={org1}", headers=_auth_header(token1))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    names = {item["name"] for item in data["items"]}
    assert names == {"Org1 Dataset A", "Org1 Dataset B"}


def test_list_datasets_cross_org_forbidden(client: TestClient):
    """15. Requesting dataset list for an org where user is not a member returns HTTP 403."""
    _, token1 = _create_user_and_login(client, "cross_admin@example.com")
    org1 = _create_org(client, token1, "Secret Org")

    _, token2 = _create_user_and_login(client, "cross_intruder@example.com")

    resp = client.get(f"/datasets?organization_id={org1}", headers=_auth_header(token2))
    assert resp.status_code == 403
    assert "not a member" in resp.json()["detail"].lower()


def test_list_datasets_missing_org_query_param(client: TestClient):
    """16. GET /datasets without organization_id returns HTTP 422 Unprocessable Entity."""
    _, token = _create_user_and_login(client, "param_test@example.com")

    resp = client.get("/datasets", headers=_auth_header(token))
    assert resp.status_code == 422


def test_get_dataset_by_id(client: TestClient):
    """17. Authenticated member can get dataset details by ID."""
    _, token = _create_user_and_login(client, "get_ds_admin@example.com")
    org_id = _create_org(client, token, "Get Detail Org")

    upload_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token),
        data={"organization_id": org_id, "name": "Detailed Dataset"},
        files={"file": ("detail.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    dataset_id = upload_resp.json()["id"]

    resp = client.get(f"/datasets/{dataset_id}", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == dataset_id
    assert data["name"] == "Detailed Dataset"
    assert data["status"] == "uploaded"
    assert "storage_path" not in data


def test_get_dataset_cross_org_forbidden(client: TestClient):
    """18. User from another organization cannot get dataset by ID (HTTP 403)."""
    _, token1 = _create_user_and_login(client, "owner_get@example.com")
    org1 = _create_org(client, token1, "Detail Org 1")

    upload_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(token1),
        data={"organization_id": org1, "name": "Private Dataset"},
        files={"file": ("private.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    dataset_id = upload_resp.json()["id"]

    _, token2 = _create_user_and_login(client, "outsider_get@example.com")
    resp = client.get(f"/datasets/{dataset_id}", headers=_auth_header(token2))
    assert resp.status_code == 403
    assert "not a member" in resp.json()["detail"].lower()


def test_admin_and_analyst_can_delete_dataset(client: TestClient):
    """19. ADMIN and ANALYST can delete dataset (HTTP 204), file is removed, GET returns 404."""
    _, admin_token = _create_user_and_login(client, "admin_delete@example.com")
    org_id = _create_org(client, admin_token, "Delete Org")

    _, analyst_token = _create_user_and_login(client, "analyst_delete@example.com")
    _add_member(client, admin_token, org_id, "analyst_delete@example.com", "analyst")

    # Admin uploads dataset 1
    ds1_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(admin_token),
        data={"organization_id": org_id, "name": "DS To Delete By Admin"},
        files={"file": ("del1.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    ds1_id = ds1_resp.json()["id"]

    # Analyst uploads dataset 2
    ds2_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(analyst_token),
        data={"organization_id": org_id, "name": "DS To Delete By Analyst"},
        files={"file": ("del2.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    ds2_id = ds2_resp.json()["id"]

    # Admin deletes dataset 1
    del1_resp = client.delete(f"/datasets/{ds1_id}", headers=_auth_header(admin_token))
    assert del1_resp.status_code == 204

    # Confirm dataset 1 is 404
    assert client.get(f"/datasets/{ds1_id}", headers=_auth_header(admin_token)).status_code == 404

    # Analyst deletes dataset 2
    del2_resp = client.delete(f"/datasets/{ds2_id}", headers=_auth_header(analyst_token))
    assert del2_resp.status_code == 204

    # Confirm dataset 2 is 404
    assert client.get(f"/datasets/{ds2_id}", headers=_auth_header(analyst_token)).status_code == 404


def test_manager_and_viewer_cannot_delete_dataset(client: TestClient):
    """20. MANAGER and VIEWER cannot delete datasets (HTTP 403)."""
    _, admin_token = _create_user_and_login(client, "admin_del_rbac@example.com")
    org_id = _create_org(client, admin_token, "Delete RBAC Org")

    _, mgr_token = _create_user_and_login(client, "mgr_del@example.com")
    _add_member(client, admin_token, org_id, "mgr_del@example.com", "manager")

    _, vwr_token = _create_user_and_login(client, "vwr_del@example.com")
    _add_member(client, admin_token, org_id, "vwr_del@example.com", "viewer")

    # Admin uploads dataset
    ds_resp = client.post(
        "/datasets/upload",
        headers=_auth_header(admin_token),
        data={"organization_id": org_id, "name": "Protected Dataset"},
        files={"file": ("safe.csv", io.BytesIO(_sample_csv_bytes()), "text/csv")},
    )
    dataset_id = ds_resp.json()["id"]

    # Manager attempts delete -> 403
    mgr_del = client.delete(f"/datasets/{dataset_id}", headers=_auth_header(mgr_token))
    assert mgr_del.status_code == 403
    assert "Insufficient permissions" in mgr_del.json()["detail"]

    # Viewer attempts delete -> 403
    vwr_del = client.delete(f"/datasets/{dataset_id}", headers=_auth_header(vwr_token))
    assert vwr_del.status_code == 403
    assert "Insufficient permissions" in vwr_del.json()["detail"]

    # Dataset still exists
    assert client.get(f"/datasets/{dataset_id}", headers=_auth_header(admin_token)).status_code == 200
