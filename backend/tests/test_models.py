"""Tests for the ORM model layer.

These tests only inspect `Base.metadata` -- they do not require a live
database connection, so they run in any environment (including CI, once
configured) without needing PostgreSQL available. Migration-level
verification against a real database was performed manually for Phase 2
(see docs/database.md, section 7) and is not repeated here.
"""

from app.db.models import Base

EXPECTED_TABLES = {
    "users",
    "organizations",
    "organization_members",
    "datasets",
    "dataset_columns",
    "customers",
    "products",
    "orders",
    "payments",
    "documents",
    "document_chunks",
    "analytics_queries",
    "ai_conversations",
    "ai_messages",
    "anomalies",
    "forecasts",
    "reports",
    "audit_logs",
    # Phase 4 -- authentication sessions
    "auth_sessions",
}


def test_all_required_tables_are_registered():
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_every_table_has_a_uuid_primary_key_named_id():
    for table in Base.metadata.tables.values():
        assert "id" in table.columns
        assert table.columns["id"].primary_key


def test_every_table_has_created_at():
    for table in Base.metadata.tables.values():
        assert "created_at" in table.columns


def test_audit_logs_has_no_updated_at_append_only():
    audit_logs = Base.metadata.tables["audit_logs"]
    assert "updated_at" not in audit_logs.columns


def test_auth_sessions_has_no_updated_at_append_only():
    """auth_sessions is append-only (like audit_logs) -- no updated_at."""
    auth_sessions = Base.metadata.tables["auth_sessions"]
    assert "updated_at" not in auth_sessions.columns


def test_auth_sessions_has_required_columns():
    t = Base.metadata.tables["auth_sessions"]
    for col in ("user_id", "token_hash", "expires_at", "revoked", "revoked_at"):
        assert col in t.columns, f"auth_sessions missing column: {col}"


def test_org_scoped_tables_have_organization_id_foreign_key():
    org_scoped = EXPECTED_TABLES - {
        "users",
        "organizations",
        "auth_sessions",        # platform-wide, not org-scoped
        # scoped indirectly through a parent, not a direct FK column
        "dataset_columns",
        "ai_messages",
        "payments",
    }
    for table_name in org_scoped:
        table = Base.metadata.tables[table_name]
        assert "organization_id" in table.columns, f"{table_name} missing organization_id"


def test_document_chunks_has_vector_embedding_column():
    document_chunks = Base.metadata.tables["document_chunks"]
    assert "embedding" in document_chunks.columns
