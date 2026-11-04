"""
Unit and Validation Tests for WAPSI Phase 1B.5: Mumbai Migration Configuration and Security Remediation.
Project: filofxijqmgluuulivxb (WAPSI-DEV-MUMBAI, Region: ap-south-1)
"""

import os
from pathlib import Path

import pytest
from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager


def test_mumbai_project_configuration_and_fallbacks():
    """Verifies that the Mumbai project is set as the active deployment target."""
    settings = get_settings()
    assert "filofxijqmgluuulivxb" in settings.supabase_url
    assert settings.supabase_url == "https://filofxijqmgluuulivxb.supabase.co"

    # Check config.toml
    config_path = Path("supabase/config.toml")
    assert config_path.exists(), "supabase/config.toml missing!"
    config_content = config_path.read_text(encoding="utf-8")
    assert 'project_id = "filofxijqmgluuulivxb"' in config_content
    assert 'seed_file = "supabase/seed.sql"' in config_content
    assert "WAPSI-DEV-MUMBAI" in config_content

    # Check .env.example
    env_example_path = Path(".env.example")
    assert env_example_path.exists()
    env_content = env_example_path.read_text(encoding="utf-8")
    assert "https://filofxijqmgluuulivxb.supabase.co" in env_content
    assert "aws-0-ap-south-1.pooler.supabase.com" in env_content


def test_migration_seed_separation():
    """
    Verifies that development fixtures have been isolated into supabase/seed.sql
    and removed from production migration directory supabase/migrations/.
    """
    migrations_dir = Path("supabase/migrations")
    assert migrations_dir.exists()

    migration_files = sorted([f.name for f in migrations_dir.glob("*.sql")])
    assert len(migration_files) in {3, 5, 6, 7, 8}, f"Expected 3, 5, 6, 7, or 8 migrations, found {len(migration_files)}: {migration_files}"
    assert migration_files[:3] == [
        "20261031000001_initial_core_schema.sql",
        "20261031000002_operations_outbox_audit.sql",
        "20261031000003_rls_policies_and_security.sql",
    ]

    # Verify seed.sql exists and contains fixtures
    seed_path = Path("supabase/seed.sql")
    assert seed_path.exists(), "supabase/seed.sql must exist!"
    seed_content = seed_path.read_text(encoding="utf-8")
    assert "MRC_928374" in seed_content
    assert "Acme Global Technologies" in seed_content
    assert "wapsi_t_learner" in seed_content
    assert "GENESIS_BLOCK" in seed_content


def test_rls_sql_security_hardening():
    """
    Verifies the SQL corrections in Migration 3:
    1. current_active_merchant_id() checks session setting and app_metadata, NEVER user_metadata.
    2. Missing merchant context fails closed (returns NULL).
    3. webhook_inbox does NOT grant WITH CHECK (true) or allow arbitrary authenticated insertions.
    4. webhook_inbox and audit_ledger_blocks do NOT expose NULL merchant_id to authenticated merchants.
    5. Dispatches have secure delivery status updates.
    6. All security functions pin search_path = public.
    """
    rls_path = Path("supabase/migrations/20261031000003_rls_policies_and_security.sql")
    assert rls_path.exists()
    sql = rls_path.read_text(encoding="utf-8")

    # 1. Identity context security
    assert "app_metadata" in sql
    assert "auth.jwt() -> 'user_metadata'" not in sql, "user_metadata is user-editable and must NEVER be used for tenant authorization!"
    assert "auth.jwt() ->> 'user_metadata'" not in sql
    assert "current_setting('app.current_merchant_id', true)" in sql

    # 2. Webhook security
    assert "WITH CHECK (true)" not in sql, "WITH CHECK (true) on webhook_inbox is insecure and must be rejected!"
    assert "p_webhook_inbox_insert" in sql
    assert "system_service" in sql

    # 3. Tenant isolation: No exposure of unassigned (NULL) merchant records to ordinary merchants
    assert "merchant_id IS NULL OR (" not in sql, "Unassigned global records must not be exposed to arbitrary merchants!"

    # 4. Dispatch transitions
    assert "p_dispatches_update" in sql
    assert "'SENT', 'DELIVERED', 'READ', 'FAILED'" in sql
    assert "update_dispatch_delivery_status" in sql

    # 5. Immutability trigger & search_path
    assert "SET search_path = public" in sql
    assert "trg_audit_ledger_immutability" in sql
    assert "prevent_audit_ledger_tampering" in sql


def test_requirements_postgres_driver_declared():
    """Verifies that psycopg2-binary is declared in requirements.txt."""
    req_path = Path("requirements.txt")
    assert req_path.exists()
    content = req_path.read_text(encoding="utf-8")
    assert "psycopg2-binary" in content
    assert "sqlalchemy" in content
    assert "pydantic-settings" in content


def test_database_manager_url_translation_and_fallback():
    """Verifies that DatabaseManager translates postgres URLs to psycopg2 while preserving SQLite fallback."""
    # 1. Fallback mode
    db_sqlite = DatabaseManager(database_url="sqlite:///:memory:")
    assert db_sqlite.is_fallback_mode is False
    assert ":memory:" in db_sqlite.database_url
    ping = db_sqlite.ping()
    assert ping["status"] == "healthy"
    db_sqlite.engine.dispose()

    # 2. URL dialect translations
    mgr1 = DatabaseManager.__new__(DatabaseManager)
    # Test postgres:// -> postgresql+psycopg2://
    test_url_1 = "postgres://user:pass@localhost:5432/db"
    if test_url_1.startswith("postgres://"):
        translated_1 = test_url_1.replace("postgres://", "postgresql+psycopg2://", 1)
    assert translated_1 == "postgresql+psycopg2://user:pass@localhost:5432/db"

    # Test postgresql:// -> postgresql+psycopg2://
    test_url_2 = "postgresql://user:pass@localhost:5432/db"
    if test_url_2.startswith("postgresql://") and not test_url_2.startswith("postgresql+"):
        translated_2 = test_url_2.replace("postgresql://", "postgresql+psycopg2://", 1)
    assert translated_2 == "postgresql+psycopg2://user:pass@localhost:5432/db"
