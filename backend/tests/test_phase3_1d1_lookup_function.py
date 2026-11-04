"""
WAPSI Phase 3.1D.1: Regression Test Suite for public.lookup_merchant_by_api_key_hash
Guarantees Verified:
1. Valid API-key hash returns the correct merchant identity (merchant_id, merchant_code, status, scopes).
2. Unknown hash returns no merchant (empty result set).
3. Revoked key (is_revoked = true) is rejected.
4. Expired key (expires_at < now()) is rejected.
5. Inactive merchant (status != 'ACTIVE') is rejected.
6. Invalid hash format (NULL, len != 64, non-hex, uppercase) fails closed safely without error.
7. Function returns exact expected field names and data types.
8. wapsi_app role can execute the function successfully.
9. wapsi_app role is strictly forbidden from directly SELECTing public.merchant_api_keys (42501).
10. PUBLIC, anon, and authenticated roles are strictly forbidden from executing the function (42501).

Environment:
- Operates strictly in an isolated local temporary PostgreSQL 17 test cluster (port 5439).
- Zero interaction or synthetic data pollution on hosted Supabase.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Generator, Dict, Any

import psycopg2
import pytest
from psycopg2 import sql


TEST_PG_PORT = 5439
TEST_PG_DIR = os.path.abspath(".tmp_pg_phase31d1_test")
POSTGRES_BIN_DIR = r"C:\Program Files\PostgreSQL\17\bin"


@pytest.fixture(scope="module")
def local_pg_cluster() -> Generator[str, None, None]:
    """
    Spawns an isolated local PostgreSQL 17 cluster on dedicated port 5439,
    executes migrations 1-6 in sequence, yields connection string,
    and cleanly tears down on exit.
    """
    if not os.path.exists(os.path.join(POSTGRES_BIN_DIR, "postgres.exe")):
        pytest.skip(f"PostgreSQL 17 binaries not found at {POSTGRES_BIN_DIR}")

    shutil.rmtree(TEST_PG_DIR, ignore_errors=True)

    # 1. Initialize cluster
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

    # 2. Start PostgreSQL server
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
    time.sleep(2.5)

    try:
        conn = psycopg2.connect(admin_db_url)
        conn.autocommit = True
        cur = conn.cursor()

        # 3. Create prerequisite Supabase auth stubs and standard roles
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

        # 4. Apply all 6 migrations in sequence
        backend_dir = Path(__file__).resolve().parent.parent
        mig1 = (backend_dir / "supabase" / "migrations" / "20261031000001_initial_core_schema.sql").read_text(encoding="utf-8")
        mig2 = (backend_dir / "supabase" / "migrations" / "20261031000002_operations_outbox_audit.sql").read_text(encoding="utf-8")
        mig3 = (backend_dir / "supabase" / "migrations" / "20261031000003_rls_policies_and_security.sql").read_text(encoding="utf-8")
        mig4 = (backend_dir / "supabase" / "migrations" / "20261101000004_phase1d_restricted_app_role.sql").read_text(encoding="utf-8")
        mig5 = (backend_dir / "supabase" / "migrations" / "20261101000005_phase3_outbox_leases_and_opt_outs.sql").read_text(encoding="utf-8")
        mig6 = (backend_dir / "supabase" / "migrations" / "20261101000006_fix_api_key_lookup_function.sql").read_text(encoding="utf-8")

        for m_idx, m_sql in enumerate([mig1, mig2, mig3, mig4, mig5, mig6], start=1):
            cur.execute(m_sql)

        # Grant wapsi_app a known password for local tests
        cur.execute("ALTER ROLE wapsi_app WITH PASSWORD 'test_wapsi_app_secure_password_12345';")

        conn.close()
        yield admin_db_url
    finally:
        pg_proc.terminate()
        try:
            pg_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pg_proc.kill()
        shutil.rmtree(TEST_PG_DIR, ignore_errors=True)


@pytest.fixture(scope="module")
def seed_test_data(local_pg_cluster: str) -> Dict[str, Any]:
    """Seeds test merchants and keys into isolated local cluster."""
    conn = psycopg2.connect(local_pg_cluster)
    conn.autocommit = True
    cur = conn.cursor()

    active_merchant_id = str(uuid.uuid4())
    suspended_merchant_id = str(uuid.uuid4())

    # Insert Active Merchant
    cur.execute("""
        INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
        VALUES (%s, 'MERCH_ACTIVE_001', 'Active Merchant Corp', 'active@test.com', 'ACTIVE');
    """, (active_merchant_id,))

    # Insert Suspended Merchant
    cur.execute("""
        INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
        VALUES (%s, 'MERCH_SUSPENDED_002', 'Suspended Merchant Ltd', 'suspended@test.com', 'SUSPENDED');
    """, (suspended_merchant_id,))

    # Helper to generate 64-char sha256 hex
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    valid_raw_key = "wapsi_live_valid_key_sample_123456789012"
    valid_hash = hash_key(valid_raw_key)

    valid_exp_raw_key = "wapsi_live_future_exp_key_sample_123456"
    valid_exp_hash = hash_key(valid_exp_raw_key)

    revoked_raw_key = "wapsi_live_revoked_key_sample_1234567890"
    revoked_hash = hash_key(revoked_raw_key)

    expired_raw_key = "wapsi_live_expired_key_sample_1234567890"
    expired_hash = hash_key(expired_raw_key)

    suspended_raw_key = "wapsi_live_suspended_merch_key_sample_12"
    suspended_hash = hash_key(suspended_raw_key)

    now = datetime.now(timezone.utc)
    future = now + timedelta(days=30)
    past = now - timedelta(days=5)

    # 1. Valid Key (Active Merchant, No Expiry, Not Revoked)
    cur.execute("""
        INSERT INTO public.merchant_api_keys (merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment, scopes, is_revoked, expires_at)
        VALUES (%s, 'Production Key', 'wapsi_live_', '789012', %s, 'live', '["recovery:predict", "recovery:read"]'::jsonb, false, NULL);
    """, (active_merchant_id, valid_hash))

    # 2. Valid Key with Future Expiry
    cur.execute("""
        INSERT INTO public.merchant_api_keys (merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment, scopes, is_revoked, expires_at)
        VALUES (%s, 'Expiring Key', 'wapsi_live_', '123456', %s, 'live', '["recovery:predict"]'::jsonb, false, %s);
    """, (active_merchant_id, valid_exp_hash, future))

    # 3. Revoked Key
    cur.execute("""
        INSERT INTO public.merchant_api_keys (merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment, scopes, is_revoked, expires_at)
        VALUES (%s, 'Revoked Key', 'wapsi_live_', '7890', %s, 'live', '["recovery:predict"]'::jsonb, true, NULL);
    """, (active_merchant_id, revoked_hash))

    # 4. Expired Key
    cur.execute("""
        INSERT INTO public.merchant_api_keys (merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment, scopes, is_revoked, expires_at)
        VALUES (%s, 'Expired Key', 'wapsi_live_', '7890', %s, 'live', '["recovery:predict"]'::jsonb, false, %s);
    """, (active_merchant_id, expired_hash, past))

    # 5. Key for Suspended Merchant
    cur.execute("""
        INSERT INTO public.merchant_api_keys (merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment, scopes, is_revoked, expires_at)
        VALUES (%s, 'Suspended Key', 'wapsi_live_', 'le_12', %s, 'live', '["recovery:predict"]'::jsonb, false, NULL);
    """, (suspended_merchant_id, suspended_hash))

    conn.close()

    return {
        "active_merchant_id": active_merchant_id,
        "suspended_merchant_id": suspended_merchant_id,
        "valid_hash": valid_hash,
        "valid_exp_hash": valid_exp_hash,
        "revoked_hash": revoked_hash,
        "expired_hash": expired_hash,
        "suspended_hash": suspended_hash,
    }


def test_valid_api_key_lookup(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """1. Valid API-key hash returns the correct merchant identity and fields."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["valid_hash"],))
    rows = cur.fetchall()
    assert len(rows) == 1
    row = rows[0]

    # Expected: (merchant_id uuid, merchant_code varchar, merchant_status varchar, key_scopes jsonb)
    m_id, m_code, m_status, scopes = row
    assert str(m_id) == seed_test_data["active_merchant_id"]
    assert m_code == "MERCH_ACTIVE_001"
    assert m_status == "ACTIVE"
    assert scopes == ["recovery:predict", "recovery:read"]
    conn.close()


def test_valid_key_with_future_expiry(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """1b. Valid key with future expiration date returns the correct merchant."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["valid_exp_hash"],))
    rows = cur.fetchall()
    assert len(rows) == 1
    m_id, m_code, m_status, scopes = rows[0]
    assert str(m_id) == seed_test_data["active_merchant_id"]
    assert m_code == "MERCH_ACTIVE_001"
    assert m_status == "ACTIVE"
    assert scopes == ["recovery:predict"]
    conn.close()


def test_unknown_hash_returns_empty(local_pg_cluster: str):
    """2. Unknown hash returns no merchant (empty result set)."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    dummy_unknown_hash = hashlib.sha256(b"unknown_nonexistent_key_123").hexdigest()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (dummy_unknown_hash,))
    rows = cur.fetchall()
    assert len(rows) == 0
    conn.close()


def test_revoked_key_rejected(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """3. Revoked key is rejected (returns empty result)."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["revoked_hash"],))
    rows = cur.fetchall()
    assert len(rows) == 0
    conn.close()


def test_expired_key_rejected(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """4. Expired key is rejected (returns empty result)."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["expired_hash"],))
    rows = cur.fetchall()
    assert len(rows) == 0
    conn.close()


def test_inactive_merchant_rejected(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """5. Inactive merchant (status != 'ACTIVE') is rejected."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["suspended_hash"],))
    rows = cur.fetchall()
    assert len(rows) == 0
    conn.close()


@pytest.mark.parametrize("invalid_input", [
    None,
    "",
    "short_string",
    "a" * 63,          # 63 chars (too short)
    "a" * 65,          # 65 chars (too long)
    "g" * 64,          # invalid hex character 'g'
    "A" * 64,          # uppercase hex (must be lowercase)
    " " * 64,          # whitespace
    "'" + "a" * 62 + "'", # SQL injection attempt
])
def test_invalid_hash_format_fails_closed(local_pg_cluster: str, invalid_input):
    """6. Invalid hash format fails closed safely without SQL error or exception."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (invalid_input,))
    rows = cur.fetchall()
    assert len(rows) == 0
    conn.close()


def test_return_field_names_and_types(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """7. Function returns exact expected field names and data types."""
    conn = psycopg2.connect(local_pg_cluster)
    cur = conn.cursor()
    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["valid_hash"],))
    col_names = [desc[0] for desc in cur.description]
    assert col_names == ["merchant_id", "merchant_code", "merchant_status", "key_scopes"]

    row = cur.fetchone()
    assert isinstance(row[0], str)  # UUID representation
    assert uuid.UUID(row[0])        # Valid UUID
    assert isinstance(row[1], str)  # merchant_code is string
    assert isinstance(row[2], str)  # merchant_status is string
    assert isinstance(row[3], list) # key_scopes deserialized JSONB list
    conn.close()


def test_wapsi_app_can_execute_function(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """8. wapsi_app role can execute the function."""
    wapsi_url = f"postgresql://wapsi_app:test_wapsi_app_secure_password_12345@localhost:{TEST_PG_PORT}/postgres"
    conn = psycopg2.connect(wapsi_url)
    cur = conn.cursor()
    cur.execute("SELECT current_user;")
    assert cur.fetchone()[0] == "wapsi_app"

    cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["valid_hash"],))
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "MERCH_ACTIVE_001"
    conn.close()


def test_wapsi_app_cannot_select_merchant_api_keys(local_pg_cluster: str):
    """9. wapsi_app role cannot directly SELECT public.merchant_api_keys (42501)."""
    wapsi_url = f"postgresql://wapsi_app:test_wapsi_app_secure_password_12345@localhost:{TEST_PG_PORT}/postgres"
    conn = psycopg2.connect(wapsi_url)
    cur = conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc_info:
        cur.execute("SELECT * FROM public.merchant_api_keys LIMIT 1;")
    assert "permission denied for table merchant_api_keys" in str(exc_info.value).lower()
    conn.close()


def test_public_anon_authenticated_cannot_execute(local_pg_cluster: str, seed_test_data: Dict[str, Any]):
    """10. PUBLIC, anon, and authenticated roles do not gain EXECUTE privileges."""
    admin_conn = psycopg2.connect(local_pg_cluster)
    admin_conn.autocommit = True
    cur = admin_conn.cursor()

    # Test as role 'anon'
    cur.execute("SET ROLE anon;")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc_info:
        cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["valid_hash"],))
    assert "permission denied for function lookup_merchant_by_api_key_hash" in str(exc_info.value).lower()

    # Test as role 'authenticated'
    cur.execute("RESET ROLE;")
    cur.execute("SET ROLE authenticated;")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc_info:
        cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (seed_test_data["valid_hash"],))
    assert "permission denied for function lookup_merchant_by_api_key_hash" in str(exc_info.value).lower()

    cur.execute("RESET ROLE;")
    admin_conn.close()

