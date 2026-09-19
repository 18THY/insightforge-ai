"""
tests/test_rbac.py
==================
Tests for Phase 5 Multi-Tenant Organization Management and RBAC.

Tests run against an in-memory SQLite database using FastAPI's dependency
overrides. Only the 4 canonical roles (ADMIN, ANALYST, MANAGER, VIEWER)
are tested and permitted.

Test Matrix:
 1  test_create_organization_assigns_admin
 2  test_list_organizations_isolation
 3  test_cross_tenant_access_forbidden
 4  test_admin_can_add_all_canonical_roles
 5  test_analyst_cannot_add_members
 6  test_manager_cannot_add_members
 7  test_viewer_cannot_add_members
 8  test_add_member_unregistered_email
 9  test_add_member_duplicate_conflict
10  test_add_member_invalid_role_rejected
11  test_admin_can_update_member_role
12  test_non_admin_cannot_update_member_role
13  test_cannot_demote_sole_admin
14  test_can_demote_admin_when_another_admin_exists
15  test_admin_can_remove_member
16  test_non_admin_cannot_remove_other_members
17  test_member_can_leave_organization
18  test_sole_admin_cannot_leave_organization
19  test_all_roles_can_view_org_and_members
20  test_unauthenticated_access_fails
"""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models.auth import AuthSession
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

RBAC_TABLES = [
    User.__table__,
    AuthSession.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
]


def _create_tables() -> None:
    Base.metadata.create_all(bind=_engine, tables=RBAC_TABLES)


def _drop_tables() -> None:
    Base.metadata.drop_all(bind=_engine, tables=RBAC_TABLES)


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
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


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


# ---------------------------------------------------------------------------
# 1. Organization creation assigns ADMIN
# ---------------------------------------------------------------------------

def test_create_organization_assigns_admin(client: TestClient):
    _, token = _create_user_and_login(client, "admin_user@example.com")
    resp = client.post(
        "/organizations",
        json={"name": "Acme Corp"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert data["role"] == "admin"
    assert "slug" in data
    assert "id" in data


# ---------------------------------------------------------------------------
# 2. List organizations isolation
# ---------------------------------------------------------------------------

def test_list_organizations_isolation(client: TestClient):
    _, token1 = _create_user_and_login(client, "user1_iso@example.com")
    _, token2 = _create_user_and_login(client, "user2_iso@example.com")

    # User 1 creates Org 1
    resp1 = client.post("/organizations", json={"name": "Org One"}, headers=_auth_header(token1))
    org1_id = resp1.json()["id"]

    # User 2 creates Org 2
    resp2 = client.post("/organizations", json={"name": "Org Two"}, headers=_auth_header(token2))
    org2_id = resp2.json()["id"]

    # User 1 lists orgs -> only Org 1
    list1 = client.get("/organizations", headers=_auth_header(token1)).json()
    assert len(list1) == 1
    assert list1[0]["id"] == org1_id

    # User 2 lists orgs -> only Org 2
    list2 = client.get("/organizations", headers=_auth_header(token2)).json()
    assert len(list2) == 1
    assert list2[0]["id"] == org2_id


# ---------------------------------------------------------------------------
# 3. Cross-tenant access forbidden
# ---------------------------------------------------------------------------

def test_cross_tenant_access_forbidden(client: TestClient):
    _, token1 = _create_user_and_login(client, "tenant1@example.com")
    _, token2 = _create_user_and_login(client, "tenant2@example.com")

    resp1 = client.post("/organizations", json={"name": "Tenant 1 Org"}, headers=_auth_header(token1))
    org1_id = resp1.json()["id"]

    # User 2 attempts to get Org 1 details
    get_resp = client.get(f"/organizations/{org1_id}", headers=_auth_header(token2))
    assert get_resp.status_code == 403

    # User 2 attempts to list Org 1 members
    members_resp = client.get(f"/organizations/{org1_id}/members", headers=_auth_header(token2))
    assert members_resp.status_code == 403

    # User 2 attempts to add member to Org 1
    add_resp = client.post(
        f"/organizations/{org1_id}/members",
        json={"email": "someone@example.com", "role": "viewer"},
        headers=_auth_header(token2),
    )
    assert add_resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Admin can add all four canonical roles
# ---------------------------------------------------------------------------

def test_admin_can_add_all_canonical_roles(client: TestClient):
    _, admin_token = _create_user_and_login(client, "big_admin@example.com")
    org_resp = client.post("/organizations", json={"name": "Enterprise Inc"}, headers=_auth_header(admin_token))
    org_id = org_resp.json()["id"]

    roles_to_test = ["analyst", "manager", "viewer", "admin"]
    for role in roles_to_test:
        user_email = f"member_{role}@example.com"
        _create_user_and_login(client, user_email)

        add_resp = client.post(
            f"/organizations/{org_id}/members",
            json={"email": user_email, "role": role},
            headers=_auth_header(admin_token),
        )
        assert add_resp.status_code == 201
        data = add_resp.json()
        assert data["role"] == role
        assert data["email"] == user_email


# ---------------------------------------------------------------------------
# 5, 6, 7. Non-admin roles cannot add members
# ---------------------------------------------------------------------------

def test_analyst_cannot_add_members(client: TestClient):
    _, admin_token = _create_user_and_login(client, "adm_for_analyst@example.com")
    org = client.post("/organizations", json={"name": "Analyst Org"}, headers=_auth_header(admin_token)).json()

    _, analyst_token = _create_user_and_login(client, "the_analyst@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "the_analyst@example.com", "role": "analyst"},
        headers=_auth_header(admin_token),
    )

    _create_user_and_login(client, "target1@example.com")
    resp = client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "target1@example.com", "role": "viewer"},
        headers=_auth_header(analyst_token),
    )
    assert resp.status_code == 403


def test_manager_cannot_add_members(client: TestClient):
    _, admin_token = _create_user_and_login(client, "adm_for_mgr@example.com")
    org = client.post("/organizations", json={"name": "Manager Org"}, headers=_auth_header(admin_token)).json()

    _, mgr_token = _create_user_and_login(client, "the_manager@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "the_manager@example.com", "role": "manager"},
        headers=_auth_header(admin_token),
    )

    _create_user_and_login(client, "target2@example.com")
    resp = client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "target2@example.com", "role": "viewer"},
        headers=_auth_header(mgr_token),
    )
    assert resp.status_code == 403


def test_viewer_cannot_add_members(client: TestClient):
    _, admin_token = _create_user_and_login(client, "adm_for_vwr@example.com")
    org = client.post("/organizations", json={"name": "Viewer Org"}, headers=_auth_header(admin_token)).json()

    _, vwr_token = _create_user_and_login(client, "the_viewer@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "the_viewer@example.com", "role": "viewer"},
        headers=_auth_header(admin_token),
    )

    _create_user_and_login(client, "target3@example.com")
    resp = client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "target3@example.com", "role": "viewer"},
        headers=_auth_header(vwr_token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 8. Add member unregistered email -> 404
# ---------------------------------------------------------------------------

def test_add_member_unregistered_email(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_ghost@example.com")
    org = client.post("/organizations", json={"name": "Ghost Org"}, headers=_auth_header(admin_token)).json()

    resp = client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "does_not_exist@example.com", "role": "viewer"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. Add member duplicate conflict -> 409
# ---------------------------------------------------------------------------

def test_add_member_duplicate_conflict(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_dupe@example.com")
    org = client.post("/organizations", json={"name": "Dupe Org"}, headers=_auth_header(admin_token)).json()

    _create_user_and_login(client, "dupe_target@example.com")
    resp1 = client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "dupe_target@example.com", "role": "analyst"},
        headers=_auth_header(admin_token),
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "dupe_target@example.com", "role": "analyst"},
        headers=_auth_header(admin_token),
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# 10. Add member invalid role rejected -> 422
# ---------------------------------------------------------------------------

def test_add_member_invalid_role_rejected(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_badrole@example.com")
    org = client.post("/organizations", json={"name": "BadRole Org"}, headers=_auth_header(admin_token)).json()

    _create_user_and_login(client, "badrole_target@example.com")
    for bad_role in ["owner", "member", "superadmin", "guest"]:
        resp = client.post(
            f"/organizations/{org['id']}/members",
            json={"email": "badrole_target@example.com", "role": bad_role},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 11. Admin can update member role
# ---------------------------------------------------------------------------

def test_admin_can_update_member_role(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_upd@example.com")
    org = client.post("/organizations", json={"name": "Upd Org"}, headers=_auth_header(admin_token)).json()

    target_user, _ = _create_user_and_login(client, "target_upd@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "target_upd@example.com", "role": "viewer"},
        headers=_auth_header(admin_token),
    )

    # Promote viewer to analyst
    resp = client.patch(
        f"/organizations/{org['id']}/members/{target_user['id']}",
        json={"role": "analyst"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "analyst"


# ---------------------------------------------------------------------------
# 12. Non-admin cannot update member role
# ---------------------------------------------------------------------------

def test_non_admin_cannot_update_member_role(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_upd_na@example.com")
    org = client.post("/organizations", json={"name": "Upd NA Org"}, headers=_auth_header(admin_token)).json()

    target_user, _ = _create_user_and_login(client, "target_upd_na@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "target_upd_na@example.com", "role": "viewer"},
        headers=_auth_header(admin_token),
    )

    _, analyst_token = _create_user_and_login(client, "analyst_upd_na@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "analyst_upd_na@example.com", "role": "analyst"},
        headers=_auth_header(admin_token),
    )

    # Analyst attempts to promote target
    resp = client.patch(
        f"/organizations/{org['id']}/members/{target_user['id']}",
        json={"role": "admin"},
        headers=_auth_header(analyst_token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 13. Cannot demote sole admin
# ---------------------------------------------------------------------------

def test_cannot_demote_sole_admin(client: TestClient):
    admin_user, admin_token = _create_user_and_login(client, "sole_admin@example.com")
    org = client.post("/organizations", json={"name": "Sole Admin Org"}, headers=_auth_header(admin_token)).json()

    # Sole admin tries to demote themselves
    resp = client.patch(
        f"/organizations/{org['id']}/members/{admin_user['id']}",
        json={"role": "analyst"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 400
    assert "Cannot demote the only admin" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 14. Can demote admin when another admin exists
# ---------------------------------------------------------------------------

def test_can_demote_admin_when_another_admin_exists(client: TestClient):
    _, admin1_token = _create_user_and_login(client, "admin1_co@example.com")
    org = client.post("/organizations", json={"name": "Co Admin Org"}, headers=_auth_header(admin1_token)).json()

    admin2_user, _ = _create_user_and_login(client, "admin2_co@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "admin2_co@example.com", "role": "admin"},
        headers=_auth_header(admin1_token),
    )

    # Demote admin 2 to manager
    resp = client.patch(
        f"/organizations/{org['id']}/members/{admin2_user['id']}",
        json={"role": "manager"},
        headers=_auth_header(admin1_token),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


# ---------------------------------------------------------------------------
# 15. Admin can remove member
# ---------------------------------------------------------------------------

def test_admin_can_remove_member(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_rem@example.com")
    org = client.post("/organizations", json={"name": "Rem Org"}, headers=_auth_header(admin_token)).json()

    target_user, _ = _create_user_and_login(client, "target_rem@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "target_rem@example.com", "role": "viewer"},
        headers=_auth_header(admin_token),
    )

    # Admin removes viewer
    resp = client.delete(
        f"/organizations/{org['id']}/members/{target_user['id']}",
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 16. Non-admin cannot remove other members
# ---------------------------------------------------------------------------

def test_non_admin_cannot_remove_other_members(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_rem_na@example.com")
    org = client.post("/organizations", json={"name": "Rem NA Org"}, headers=_auth_header(admin_token)).json()

    target_user, _ = _create_user_and_login(client, "target_rem_na@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "target_rem_na@example.com", "role": "viewer"},
        headers=_auth_header(admin_token),
    )

    _, analyst_token = _create_user_and_login(client, "analyst_rem_na@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "analyst_rem_na@example.com", "role": "analyst"},
        headers=_auth_header(admin_token),
    )

    # Analyst tries to remove viewer
    resp = client.delete(
        f"/organizations/{org['id']}/members/{target_user['id']}",
        headers=_auth_header(analyst_token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 17. Member can leave organization
# ---------------------------------------------------------------------------

def test_member_can_leave_organization(client: TestClient):
    _, admin_token = _create_user_and_login(client, "admin_leave@example.com")
    org = client.post("/organizations", json={"name": "Leave Org"}, headers=_auth_header(admin_token)).json()

    analyst_user, analyst_token = _create_user_and_login(client, "analyst_leave@example.com")
    client.post(
        f"/organizations/{org['id']}/members",
        json={"email": "analyst_leave@example.com", "role": "analyst"},
        headers=_auth_header(admin_token),
    )

    # Analyst removes self
    resp = client.delete(
        f"/organizations/{org['id']}/members/{analyst_user['id']}",
        headers=_auth_header(analyst_token),
    )
    assert resp.status_code == 200

    # Analyst can no longer access org
    get_resp = client.get(f"/organizations/{org['id']}", headers=_auth_header(analyst_token))
    assert get_resp.status_code == 403


# ---------------------------------------------------------------------------
# 18. Sole admin cannot leave organization
# ---------------------------------------------------------------------------

def test_sole_admin_cannot_leave_organization(client: TestClient):
    admin_user, admin_token = _create_user_and_login(client, "sole_leave@example.com")
    org = client.post("/organizations", json={"name": "Sole Leave Org"}, headers=_auth_header(admin_token)).json()

    resp = client.delete(
        f"/organizations/{org['id']}/members/{admin_user['id']}",
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 400
    assert "Cannot remove the only admin" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 19. All four roles can view org and members
# ---------------------------------------------------------------------------

def test_all_roles_can_view_org_and_members(client: TestClient):
    _, admin_token = _create_user_and_login(client, "view_admin@example.com")
    org = client.post("/organizations", json={"name": "View Org"}, headers=_auth_header(admin_token)).json()

    tokens = [admin_token]
    for role in ["analyst", "manager", "viewer"]:
        _, t = _create_user_and_login(client, f"view_{role}@example.com")
        client.post(
            f"/organizations/{org['id']}/members",
            json={"email": f"view_{role}@example.com", "role": role},
            headers=_auth_header(admin_token),
        )
        tokens.append(t)

    # Each role should be able to view org and member list
    for t in tokens:
        org_get = client.get(f"/organizations/{org['id']}", headers=_auth_header(t))
        assert org_get.status_code == 200

        members_get = client.get(f"/organizations/{org['id']}/members", headers=_auth_header(t))
        assert members_get.status_code == 200
        assert len(members_get.json()) == 4


# ---------------------------------------------------------------------------
# 20. Unauthenticated access fails
# ---------------------------------------------------------------------------

def test_unauthenticated_access_fails(client: TestClient):
    fake_id = str(uuid.uuid4())
    assert client.get("/organizations").status_code in (401, 403)
    assert client.post("/organizations", json={"name": "Test"}).status_code in (401, 403)
    assert client.get(f"/organizations/{fake_id}").status_code in (401, 403)
    assert client.get(f"/organizations/{fake_id}/members").status_code in (401, 403)
    assert client.post(f"/organizations/{fake_id}/members", json={"email": "a@b.com", "role": "viewer"}).status_code in (401, 403)
    assert client.patch(f"/organizations/{fake_id}/members/{fake_id}", json={"role": "analyst"}).status_code in (401, 403)
    assert client.delete(f"/organizations/{fake_id}/members/{fake_id}").status_code in (401, 403)
