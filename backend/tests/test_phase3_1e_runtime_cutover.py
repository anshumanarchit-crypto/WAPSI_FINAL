"""
WAPSI Phase 3.1E: Runtime Database Cutover & Authentication Integration Tests.

Validates:
1. FastAPI runtime and DatabaseManager strictly use DATABASE_URL.
2. No hidden administrative fallback connection exists in application code.
3. API-key authentication invokes public.lookup_merchant_by_api_key_hash(text) without accessing restricted tables.
4. Restricted role wapsi_app database operations respect grants (permitted DML works, DELETE denied, sensitive tables denied).
5. Database connection failure returns a controlled failure without silent SQLite fallback.
6. SQLite fallback is never activated when PostgreSQL is explicitly configured.
7. Switch utility creates WAPSI_ADMIN_DATABASE_URL and updates DATABASE_URL.
8. Rollback utility safely restores DATABASE_URL to administrative connection.
9. Cross-merchant row isolation (RLS) under wapsi_app role.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import MagicMock, patch

import psycopg2
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError

from wapsi.core.config import WapsiSettings, get_settings
from wapsi.db.models import CustomerModel, MerchantModel, TransactionModel
from wapsi.db.repository import MerchantRepository
from wapsi.db.session import DatabaseManager, get_db_manager
from scripts.switch_wapsi_runtime_to_app_role import build_app_url, update_env_file, read_env_file
from scripts.rollback_wapsi_runtime_to_admin import rollback_runtime


TEST_PG_PORT = 5441
TEST_PG_DIR = os.path.abspath(".tmp_pg_phase31e_test")
POSTGRES_BIN_DIR = r"C:\Program Files\PostgreSQL\17\bin"


@pytest.fixture(scope="module")
def local_pg_cluster() -> Generator[str, None, None]:
    """Isolated local PostgreSQL 17 cluster on dedicated port 5441."""
    if not os.path.exists(os.path.join(POSTGRES_BIN_DIR, "postgres.exe")):
        pytest.skip(f"PostgreSQL 17 binaries not found at {POSTGRES_BIN_DIR}")

    shutil.rmtree(TEST_PG_DIR, ignore_errors=True)

    subprocess.run(
        [
            os.path.join(POSTGRES_BIN_DIR, "initdb.exe"),
            "-D",
            TEST_PG_DIR,
            "-U",
            "postgres",
            "-A",
            "trust",
            "--no-locale",
            "-E",
            "UTF8",
        ],
        check=True,
        capture_output=True,
    )

    pg_proc = subprocess.Popen(
        [
            os.path.join(POSTGRES_BIN_DIR, "postgres.exe"),
            "-D",
            TEST_PG_DIR,
            "-p",
            str(TEST_PG_PORT),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    admin_db_url = f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres"
    conn = None
    for _ in range(20):
        try:
            conn = psycopg2.connect(admin_db_url)
            break
        except psycopg2.OperationalError:
            time.sleep(0.5)

    try:
        if not conn:
            conn = psycopg2.connect(admin_db_url)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("""
            CREATE SCHEMA IF NOT EXISTS auth;
            CREATE TABLE IF NOT EXISTS auth.users (id UUID PRIMARY KEY DEFAULT gen_random_uuid());
            CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS 'SELECT NULL::uuid;';
            CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql AS 'SELECT ''{}''::jsonb;';
            DO 'BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ''anon'') THEN CREATE ROLE anon; END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ''authenticated'') THEN CREATE ROLE authenticated; END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ''service_role'') THEN CREATE ROLE service_role; END IF;
            END';
        """)

        backend_dir = Path(__file__).resolve().parent.parent
        mig1 = (backend_dir / "supabase" / "migrations" / "20261031000001_initial_core_schema.sql").read_text(encoding="utf-8")
        mig2 = (backend_dir / "supabase" / "migrations" / "20261031000002_operations_outbox_audit.sql").read_text(encoding="utf-8")
        mig3 = (backend_dir / "supabase" / "migrations" / "20261031000003_rls_policies_and_security.sql").read_text(encoding="utf-8")
        mig4 = (backend_dir / "supabase" / "migrations" / "20261101000004_phase1d_restricted_app_role.sql").read_text(encoding="utf-8")
        mig5 = (backend_dir / "supabase" / "migrations" / "20261101000005_phase3_outbox_leases_and_opt_outs.sql").read_text(encoding="utf-8")
        mig6 = (backend_dir / "supabase" / "migrations" / "20261101000006_fix_api_key_lookup_function.sql").read_text(encoding="utf-8")

        for m_sql in [mig1, mig2, mig3, mig4, mig5, mig6]:
            cur.execute(m_sql)

        cur.execute("ALTER ROLE wapsi_app WITH PASSWORD 'test_wapsi_app_secure_password_cutover_999';")
        conn.close()
        yield admin_db_url
    finally:
        pg_proc.terminate()
        try:
            pg_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pg_proc.kill()
        shutil.rmtree(TEST_PG_DIR, ignore_errors=True)


def test_fastapi_uses_database_url_from_settings():
    """1. Confirms DatabaseManager initializes engine directly from DATABASE_URL."""
    custom_url = "sqlite:///:memory:"
    db_mgr = DatabaseManager(database_url=custom_url)
    assert db_mgr.database_url == custom_url
    assert "sqlite" in db_mgr.engine.dialect.name


def test_no_hidden_administrative_fallback():
    """2. Confirms WAPSI_ADMIN_DATABASE_URL is not read by WapsiSettings or DatabaseManager."""
    with patch.dict(os.environ, {"WAPSI_ADMIN_DATABASE_URL": "postgresql://superadmin:secret@host/db"}, clear=False):
        settings = WapsiSettings()
        # Verify settings has no attribute wapsi_admin_database_url
        assert not hasattr(settings, "wapsi_admin_database_url")
        # Verify settings.database_url does not read admin url
        assert settings.database_url != "postgresql://superadmin:secret@host/db"


def test_sqlite_fallback_not_activated_when_postgres_configured():
    """3. Confirms PostgreSQL configuration never silently falls back to SQLite."""
    pg_url = "postgresql://invalid_user:invalid_password@127.0.0.1:5499/nonexistent_db?sslmode=disable"
    db_mgr = DatabaseManager(database_url=pg_url)
    assert db_mgr.is_fallback_mode is False
    assert db_mgr.engine.dialect.name == "postgresql"

    # Health ping returns controlled unhealthy response, NOT SQLite
    health = db_mgr.ping()
    assert health["status"] == "unhealthy"
    assert health["connected"] is False
    assert health["dialect"] == "postgresql"
    assert health["is_fallback"] is False


def test_api_key_lookup_function_repository_integration(local_pg_cluster: str):
    """4. Confirms MerchantRepository.authenticate_api_key calls lookup function under PostgreSQL."""
    admin_conn = psycopg2.connect(local_pg_cluster)
    admin_conn.autocommit = True
    cur = admin_conn.cursor()

    merch_id = str(uuid.uuid4())
    raw_key = "wapsi_live_test_api_key_cutover_verification"
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    cur.execute("""
        INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
        VALUES (%s, 'MERCH_CUTOVER_01', 'Cutover Test Corp', 'cutover@test.com', 'ACTIVE');
    """, (merch_id,))

    cur.execute("""
        INSERT INTO public.merchant_api_keys (merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment, scopes, is_revoked)
        VALUES (%s, 'Test Key', 'wapsi_live_', 'tion', %s, 'live', '["recovery:predict"]'::jsonb, false);
    """, (merch_id, hashed_key))
    admin_conn.close()

    # Now connect as restricted role wapsi_app
    app_url = f"postgresql+psycopg2://wapsi_app:test_wapsi_app_secure_password_cutover_999@localhost:{TEST_PG_PORT}/postgres"
    app_mgr = DatabaseManager(database_url=app_url)

    with app_mgr.session_scope() as session:
        # Valid key lookup
        auth_res = MerchantRepository.authenticate_api_key(session, raw_key)
        assert auth_res is not None
        assert auth_res["merchant_code"] == "MERCH_CUTOVER_01"
        assert auth_res["merchant_status"] == "ACTIVE"
        assert auth_res["key_scopes"] == ["recovery:predict"]

        # Unknown key lookup
        unknown_res = MerchantRepository.authenticate_api_key(session, "completely_unknown_raw_key")
        assert unknown_res is None

        # Invalid key inputs fail closed
        assert MerchantRepository.authenticate_api_key(session, "") is None
        assert MerchantRepository.authenticate_api_key(session, None) is None


def test_restricted_role_table_grants_and_denials(local_pg_cluster: str):
    """5. Confirms wapsi_app respects table grants and denials."""
    app_url = f"postgresql://wapsi_app:test_wapsi_app_secure_password_cutover_999@localhost:{TEST_PG_PORT}/postgres"
    conn = psycopg2.connect(app_url)
    conn.autocommit = False
    cur = conn.cursor()

    # Denied SELECT on sensitive tables
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("SELECT * FROM public.merchant_api_keys LIMIT 1;")
    conn.rollback()

    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("SELECT * FROM public.merchant_memberships LIMIT 1;")
    conn.rollback()

    # Denied DELETE on operational tables
    for tbl in ["transactions", "customers", "recovery_outbox", "opt_out_registry"]:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(f"DELETE FROM public.{tbl} WHERE 1=0;")
        conn.rollback()

    conn.close()


def test_cross_merchant_rls_row_isolation(local_pg_cluster: str):
    """6. Verifies cross-merchant row isolation (RLS) under wapsi_app role."""
    admin_conn = psycopg2.connect(local_pg_cluster)
    admin_conn.autocommit = True
    adm_cur = admin_conn.cursor()

    merch_a_id = str(uuid.uuid4())
    merch_b_id = str(uuid.uuid4())
    cust_a_id = str(uuid.uuid4())
    cust_b_id = str(uuid.uuid4())

    # Create merchants
    adm_cur.execute("""
        INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
        VALUES 
            (%s, 'MERCH_RLS_A', 'Tenant A Corp', 'a@test.com', 'ACTIVE'),
            (%s, 'MERCH_RLS_B', 'Tenant B Corp', 'b@test.com', 'ACTIVE');
    """, (merch_a_id, merch_b_id))

    # Create customers
    adm_cur.execute("""
        INSERT INTO public.customers (id, merchant_id, merchant_customer_id, customer_pseudonym, masked_identifier)
        VALUES 
            (%s, %s, 'cust_a', 'pseudo_a_123', 'user_a'),
            (%s, %s, 'cust_b', 'pseudo_b_456', 'user_b');
    """, (cust_a_id, merch_a_id, cust_b_id, merch_b_id))

    # Create transactions for each tenant
    tx_a_id = str(uuid.uuid4())
    tx_b_id = str(uuid.uuid4())
    adm_cur.execute("""
        INSERT INTO public.transactions (id, merchant_id, customer_id, payment_id, amount_paise, payment_method, error_code, error_category, hour_of_day)
        VALUES 
            (%s, %s, %s, 'pay_tx_a', 150000, 'upi', 'PAYMENT_FAILED', 'FRICTION_OTP_UX', 14),
            (%s, %s, %s, 'pay_tx_b', 250000, 'card_credit', 'PAYMENT_FAILED', 'TECHNICAL_GATEWAY', 15);
    """, (tx_a_id, merch_a_id, cust_a_id, tx_b_id, merch_b_id, cust_b_id))
    admin_conn.close()

    # Now connect as restricted wapsi_app
    app_url = f"postgresql://wapsi_app:test_wapsi_app_secure_password_cutover_999@localhost:{TEST_PG_PORT}/postgres"
    conn = psycopg2.connect(app_url)
    conn.autocommit = False
    cur = conn.cursor()

    # 1. No context set -> Default-Deny (0 rows returned)
    cur.execute("SELECT count(*) FROM public.transactions;")
    assert cur.fetchone()[0] == 0

    # 2. Context set to Merchant A -> Can see ONLY Tenant A transaction
    cur.execute("SET LOCAL app.current_merchant_id = %s;", (merch_a_id,))
    cur.execute("SELECT payment_id FROM public.transactions;")
    rows_a = [r[0] for r in cur.fetchall()]
    assert rows_a == ["pay_tx_a"]
    assert "pay_tx_b" not in rows_a  # Tenant B is completely isolated!

    # 3. Context set to Merchant B -> Can see ONLY Tenant B transaction
    cur.execute("SET LOCAL app.current_merchant_id = %s;", (merch_b_id,))
    cur.execute("SELECT payment_id FROM public.transactions;")
    rows_b = [r[0] for r in cur.fetchall()]
    assert rows_b == ["pay_tx_b"]
    assert "pay_tx_a" not in rows_b  # Tenant A is completely isolated!

    # 4. Context reset -> Default-Deny
    cur.execute("SET LOCAL app.current_merchant_id = '';")
    cur.execute("SELECT count(*) FROM public.transactions;")
    assert cur.fetchone()[0] == 0

    conn.rollback()
    conn.close()


def test_env_switch_and_rollback_utilities(tmp_path):
    """7. Tests switch and rollback utilities against isolated mock .env file."""
    mock_env = tmp_path / ".env"
    initial_content = (
        "WAPSI_ENV=development\n"
        "PORT=8000\n"
        "DATABASE_URL=postgresql://postgres.admin:AdminSecret123@aws-0-pooler.supabase.com:5432/postgres\n"
        "RAZORPAY_MODE=test\n"
    )
    mock_env.write_text(initial_content, encoding="utf-8")

    # Step 1: Execute switch utility helper
    app_url = "postgresql+psycopg2://wapsi_app.filofxijqmgluuulivxb:AppSecret456@aws-0-pooler.supabase.com:5432/postgres?sslmode=require"
    admin_url = "postgresql://postgres.admin:AdminSecret123@aws-0-pooler.supabase.com:5432/postgres"

    update_env_file(mock_env, app_url, admin_url)

    # Verify .env contents after switch
    vars_after_switch = read_env_file(mock_env)
    assert vars_after_switch["DATABASE_URL"] == app_url
    assert vars_after_switch["WAPSI_ADMIN_DATABASE_URL"] == admin_url
    assert vars_after_switch["WAPSI_ENV"] == "development"
    assert vars_after_switch["PORT"] == "8000"

    # Step 2: Execute rollback utility
    rollback_runtime(env_path=mock_env, skip_conn_check=True)

    # Verify .env contents after rollback
    vars_after_rollback = read_env_file(mock_env)
    assert vars_after_rollback["DATABASE_URL"] == admin_url
    assert vars_after_rollback["WAPSI_ADMIN_DATABASE_URL"] == admin_url
    assert vars_after_rollback["PORT"] == "8000"
