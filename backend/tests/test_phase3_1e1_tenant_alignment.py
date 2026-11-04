"""
WAPSI Phase 3.1E.1: Tenant Context Wiring and Runtime Schema Alignment Test Suite.

Verifies:
1. Two merchants with separate records (cross-tenant row isolation).
2. Merchant A can read its records; cannot read or modify Merchant B's records.
3. Missing tenant context produces default-deny (0 rows returned).
4. Context is reset after transaction completion (commit and rollback).
5. Reused pooled connections do not leak tenant context across requests.
6. Authentication derives merchant identity exclusively from API-key lookup (never trusts header/body).
7. Background worker claims jobs across tenants using authorized SECURITY DEFINER mechanism.
8. Background worker processes each job under its associated merchant context.
9. Outbox lease and state transitions match deployed schema (worker_id, lease_expires_at, case_id, payment_id).
10. Zero synthetic data written to hosted Supabase (operates in isolated PostgreSQL test cluster).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

import psycopg2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from wapsi.api.app import app
from wapsi.db.models import (
    CustomerModel,
    MerchantApiKeyModel,
    MerchantModel,
    RecoveryOutboxModel,
    TransactionModel,
)
from wapsi.db.repository import (
    MerchantRepository,
    RecoveryOutboxRepository,
    TransactionRepository,
)
from wapsi.db.session import DatabaseManager
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob
from wapsi.recovery.worker import RecoveryBackgroundWorker

TEST_PG_PORT = 5440
TEST_PG_DIR = os.path.abspath(".tmp_pg_phase31e1_test")
POSTGRES_BIN_DIR = r"C:\Program Files\PostgreSQL\17\bin"
TEST_APP_PASSWORD = "test_wapsi_app_secure_password_phase31e1_999"


@pytest.fixture(scope="module")
def pg_cluster() -> Generator[DatabaseManager, None, None]:
    """Spawns an isolated local PostgreSQL 17 cluster with migrations 1–7 applied."""
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

    admin_url = f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres"
    conn = None
    for _ in range(20):
        try:
            conn = psycopg2.connect(admin_url)
            break
        except psycopg2.OperationalError:
            time.sleep(0.5)

    try:
        if not conn:
            conn = psycopg2.connect(admin_url)
        conn.autocommit = True
        cur = conn.cursor()

        # 3. Setup Supabase auth schema and mock roles
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

        # 4. Apply all migrations in sequence
        backend_dir = Path(__file__).resolve().parent.parent
        mig1 = (backend_dir / "supabase" / "migrations" / "20261031000001_initial_core_schema.sql").read_text(encoding="utf-8")
        mig2 = (backend_dir / "supabase" / "migrations" / "20261031000002_operations_outbox_audit.sql").read_text(encoding="utf-8")
        mig3 = (backend_dir / "supabase" / "migrations" / "20261031000003_rls_policies_and_security.sql").read_text(encoding="utf-8")
        mig4 = (backend_dir / "docs" / "migrations" / "20261101000004_phase1d_restricted_app_role.sql").read_text(encoding="utf-8")
        mig5 = (backend_dir / "docs" / "migrations" / "20261101000005_phase3_outbox_leases_and_opt_outs.sql").read_text(encoding="utf-8")
        mig6 = (backend_dir / "supabase" / "migrations" / "20261101000006_fix_api_key_lookup_function.sql").read_text(encoding="utf-8")
        mig7 = (backend_dir / "docs" / "migrations" / "20261101000007_outbox_worker_claim_function.sql").read_text(encoding="utf-8")
        mig8 = (backend_dir / "supabase" / "migrations" / "20261102000008_outbox_operator_authorization_gate.sql").read_text(encoding="utf-8")

        cur.execute(mig1)
        cur.execute(mig2)
        cur.execute(mig3)
        cur.execute(mig4)
        cur.execute(mig5)
        cur.execute(mig6)
        cur.execute(mig7)
        cur.execute(mig8)

        # 5. Provision password for restricted wapsi_app
        cur.execute(f"ALTER ROLE wapsi_app WITH PASSWORD '{TEST_APP_PASSWORD}';")
        conn.close()

        manager = DatabaseManager(database_url=admin_url)
        yield manager

    finally:
        pg_proc.terminate()
        try:
            pg_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pg_proc.kill()
        shutil.rmtree(TEST_PG_DIR, ignore_errors=True)


@pytest.fixture
def app_db_url() -> str:
    return f"postgresql://wapsi_app:{TEST_APP_PASSWORD}@localhost:{TEST_PG_PORT}/postgres"


def test_cross_merchant_rls_isolation(pg_cluster: DatabaseManager, app_db_url: str):
    """
    Verifies:
    - Two merchants with separate records.
    - Merchant A can read its records.
    - Merchant A cannot read or modify Merchant B's records.
    - Zero DELETE privileges.
    """
    merch_a_id = str(uuid.uuid4())
    merch_b_id = str(uuid.uuid4())
    cust_a_id = str(uuid.uuid4())
    cust_b_id = str(uuid.uuid4())
    tx_a_id = str(uuid.uuid4())
    tx_b_id = str(uuid.uuid4())

    # Admin seed
    admin_conn = psycopg2.connect(f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres")
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute("""
        INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
        VALUES 
            (%s, 'MERCH_A', 'Merchant A Store', 'a@store.com', 'ACTIVE'),
            (%s, 'MERCH_B', 'Merchant B Store', 'b@store.com', 'ACTIVE');
        INSERT INTO public.customers (id, merchant_id, merchant_customer_id, customer_pseudonym, masked_identifier)
        VALUES 
            (%s, %s, 'cust_a', 'pseudo_a_123', 'user_a'),
            (%s, %s, 'cust_b', 'pseudo_b_456', 'user_b');
        INSERT INTO public.transactions (id, merchant_id, customer_id, payment_id, amount_paise, payment_method, error_code, error_category, hour_of_day)
        VALUES 
            (%s, %s, %s, 'pay_tx_a_1', 150000, 'upi', 'PAYMENT_FAILED', 'FRICTION_OTP_UX', 14),
            (%s, %s, %s, 'pay_tx_b_1', 250000, 'card_credit', 'PAYMENT_FAILED', 'TECHNICAL_GATEWAY', 15);
    """, (merch_a_id, merch_b_id, cust_a_id, merch_a_id, cust_b_id, merch_b_id, tx_a_id, merch_a_id, cust_a_id, tx_b_id, merch_b_id, cust_b_id))
    admin_conn.close()

    # Restricted app connection
    conn = psycopg2.connect(app_db_url)
    conn.autocommit = False
    app_cur = conn.cursor()

    try:
        # Context set to Merchant A
        app_cur.execute("SELECT set_config('app.current_merchant_id', %s, true);", (merch_a_id,))

        # SELECT: can see ONLY Merchant A transaction
        app_cur.execute("SELECT payment_id FROM public.transactions;")
        visible = [r[0] for r in app_cur.fetchall()]
        assert visible == ["pay_tx_a_1"]
        assert "pay_tx_b_1" not in visible

        # UPDATE: attempting to update Merchant B transaction affects 0 rows
        app_cur.execute("UPDATE public.transactions SET error_code = 'HACKED' WHERE payment_id = 'pay_tx_b_1';")
        assert app_cur.rowcount == 0

        # DELETE: denied by role permissions (42501)
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            app_cur.execute("DELETE FROM public.transactions WHERE payment_id = 'pay_tx_a_1';")
        conn.rollback()

    finally:
        conn.close()


def test_missing_tenant_context_produces_default_deny(pg_cluster: DatabaseManager, app_db_url: str):
    """Verifies that missing tenant context produces default-deny (0 rows accessible)."""
    conn = psycopg2.connect(app_db_url)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        # No context set: current_setting('app.current_merchant_id', true) is empty -> NULL
        cur.execute("SELECT count(*) FROM public.transactions;")
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT count(*) FROM public.customers;")
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT count(*) FROM public.recovery_outbox;")
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT count(*) FROM public.causal_decisions;")
        assert cur.fetchone()[0] == 0

        # Attempting insert without context fails check constraint on RLS
        with pytest.raises((psycopg2.errors.CheckViolation, psycopg2.errors.InsufficientPrivilege)):
            cur.execute("""
                INSERT INTO public.customers (merchant_id, merchant_customer_id, customer_pseudonym, masked_identifier)
                VALUES (%s, 'anon', 'pseudo_anon', 'user_anon');
            """, (str(uuid.uuid4()),))
        conn.rollback()
    finally:
        conn.close()


def test_tenant_context_reset_and_no_connection_leakage(pg_cluster: DatabaseManager, app_db_url: str):
    """
    Verifies:
    - Context is reset after transaction completion (commit and rollback).
    - Reused connections do not leak tenant context across requests.
    """
    merch_id = str(uuid.uuid4())
    admin_conn = psycopg2.connect(f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres")
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute("INSERT INTO public.merchants (id, merchant_code, name, registered_email) VALUES (%s, 'LEAK_TEST', 'Leak Corp', 'leak@test.com');", (merch_id,))
    admin_conn.close()

    engine = create_engine(f"postgresql+psycopg2://wapsi_app:{TEST_APP_PASSWORD}@localhost:{TEST_PG_PORT}/postgres", pool_size=1, max_overflow=0)

    # 1. Transaction 1: Set context and commit
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SELECT set_config('app.current_merchant_id', :m_id, true)"), {"m_id": merch_id})
            val = conn.execute(text("SELECT current_setting('app.current_merchant_id', true);")).scalar()
            assert val == merch_id
        # Outside transaction: context must be reset immediately
        val_after_commit = conn.execute(text("SELECT current_setting('app.current_merchant_id', true);")).scalar()
        assert val_after_commit == ""

    # 2. Transaction 2: Reused connection from pool without setting context -> MUST be empty (zero leakage!)
    with engine.connect() as conn:
        with conn.begin():
            leak_check = conn.execute(text("SELECT current_setting('app.current_merchant_id', true);")).scalar()
            assert leak_check == ""

    # 3. Transaction 3: Set context and rollback
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(text("SELECT set_config('app.current_merchant_id', :m_id, true)"), {"m_id": merch_id})
                raise RuntimeError("Simulated transaction rollback")
        except RuntimeError:
            pass
        # Context must be reset immediately after rollback
        val_after_rollback = conn.execute(text("SELECT current_setting('app.current_merchant_id', true);")).scalar()
        assert val_after_rollback == ""


def test_api_key_lookup_and_tenant_derivation(pg_cluster: DatabaseManager, app_db_url: str, monkeypatch: pytest.MonkeyPatch):
    """
    Verifies:
    - Authentication derives merchant identity exclusively from API-key lookup.
    - Never trusts X-Merchant-ID or body-supplied merchant_id.
    - Contradicting headers or bodies are rejected with 403 Forbidden.
    """
    local_mgr = DatabaseManager(database_url=app_db_url)
    monkeypatch.setattr("wapsi.db.session.get_db_manager", lambda: local_mgr)
    merch_a_id = str(uuid.uuid4())
    merch_b_id = str(uuid.uuid4())
    raw_key_a = "wapsi_live_secret_key_tenant_a_12345"
    raw_key_b = "wapsi_live_secret_key_tenant_b_67890"
    hash_a = hashlib.sha256(raw_key_a.encode("utf-8")).hexdigest()
    hash_b = hashlib.sha256(raw_key_b.encode("utf-8")).hexdigest()

    admin_conn = psycopg2.connect(f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres")
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
            VALUES 
                (%s, 'MERCH_KEY_A', 'Tenant A', 'key_a@test.com', 'ACTIVE'),
                (%s, 'MERCH_KEY_B', 'Tenant B', 'key_b@test.com', 'ACTIVE');
            INSERT INTO public.merchant_api_keys (merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment)
            VALUES 
                (%s, 'Key A', 'wapsi_live', '12345', %s, 'live'),
                (%s, 'Key B', 'wapsi_live', '67890', %s, 'live');
        """, (merch_a_id, merch_b_id, merch_a_id, hash_a, merch_b_id, hash_b))
    admin_conn.close()

    # Connect as restricted wapsi_app to verify API key lookup
    app_engine = create_engine(f"postgresql+psycopg2://wapsi_app:{TEST_APP_PASSWORD}@localhost:{TEST_PG_PORT}/postgres")
    with Session(app_engine) as session:
        auth_a = MerchantRepository.authenticate_api_key(session, raw_key_a)
        assert auth_a is not None
        assert auth_a["merchant_id"] == merch_a_id
        assert auth_a["merchant_code"] == "MERCH_KEY_A"

        auth_b = MerchantRepository.authenticate_api_key(session, raw_key_b)
        assert auth_b is not None
        assert auth_b["merchant_id"] == merch_b_id
        assert auth_b["merchant_code"] == "MERCH_KEY_B"

        # Invalid key returns None
        auth_invalid = MerchantRepository.authenticate_api_key(session, "invalid_key_999")
        assert auth_invalid is None

    # Test FastAPI endpoint validation
    client = TestClient(app)

    # 1. Merchant A key + matching X-Merchant-ID -> Allowed
    valid_payload = {
        "case_id": f"RX_A_{uuid.uuid4().hex[:6]}",
        "merchant_id": "MERCH_KEY_A",
        "domain": "subscription",
        "amount": 1000.0,
        "decline_reason": "insufficient_funds",
        "attempts_used": 1,
        "account_age_days": 100,
        "previous_failures": 1,
        "previous_recoveries": 1,
        "prior_recovery_rate": 0.5,
        "day_of_week": 2,
        "hour": 14,
        "issuer": "HDFC",
        "bin_bucket": "classic",
        "fatigue_score": 0.1,
    }
    res_valid = client.post(
        "/api/v1/recovery/predict",
        json=valid_payload,
        headers={"X-API-Key": raw_key_a, "X-Merchant-ID": "MERCH_KEY_A"},
    )
    assert res_valid.status_code == 200

    # 2. Merchant A key + contradicting X-Merchant-ID -> 403 Forbidden!
    res_spoof_hdr = client.post(
        "/api/v1/recovery/predict",
        json=valid_payload,
        headers={"X-API-Key": raw_key_a, "X-Merchant-ID": "MERCH_KEY_B"},
    )
    assert res_spoof_hdr.status_code == 403
    assert "Tenant authorization failure" in res_spoof_hdr.json()["detail"]

    # 3. Merchant A key + contradicting body merchant_id -> 403 Forbidden!
    bad_body = dict(valid_payload, merchant_id="MERCH_KEY_B")
    res_spoof_body = client.post(
        "/api/v1/recovery/predict",
        json=bad_body,
        headers={"X-API-Key": raw_key_a},
    )
    assert res_spoof_body.status_code == 403
    assert "Tenant authorization failure" in res_spoof_body.json()["detail"]

    # 4. Invalid API key -> 401 Unauthorized!
    res_invalid_key = client.post(
        "/api/v1/recovery/predict",
        json=valid_payload,
        headers={"X-API-Key": "forged_secret_key"},
    )
    assert res_invalid_key.status_code == 401


def test_worker_claiming_and_processing_under_merchant_context(pg_cluster: DatabaseManager, app_db_url: str):
    """
    Verifies:
    - Background worker claims jobs across tenants using authorized claim_recovery_outbox_jobs procedure.
    - Worker gets each job's merchant_id.
    - Worker executes operations and transitions outbox state under that merchant's context.
    - Outbox lease and state transitions match deployed schema.
    """
    merch_a_id = str(uuid.uuid4())
    merch_b_id = str(uuid.uuid4())
    admin_conn = psycopg2.connect(f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres")
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
            VALUES 
                (%s, 'WRK_A', 'Worker Store A', 'wa@store.com', 'ACTIVE'),
                (%s, 'WRK_B', 'Worker Store B', 'wb@store.com', 'ACTIVE');
            INSERT INTO public.recovery_outbox (
                id, merchant_id, idempotency_key, action, channel, recipient_masked,
                message_payload, status, retry_count, max_retries, next_attempt_at, case_id, payment_id,
                requires_operator_approval, approved_by_operator_id, approved_at, approval_snapshot_hash
            ) VALUES 
                (%s, %s, 'idemp_wrk_a', 'whatsapp_nudge', 'whatsapp', '+91 98****1111', '{"phone": "+919811111111"}'::jsonb, 'QUEUED', 0, 3, now() - interval '1 minute', 'case_wrk_a', 'pay_wrk_a', true, 'ops_test_1', now(), 'dummy_hash_a'),
                (%s, %s, 'idemp_wrk_b', 'whatsapp_nudge', 'whatsapp', '+91 98****2222', '{"phone": "+919822222222"}'::jsonb, 'QUEUED', 0, 3, now() - interval '1 minute', 'case_wrk_b', 'pay_wrk_b', true, 'ops_test_2', now(), 'dummy_hash_b');
        """, (merch_a_id, merch_b_id, str(uuid.uuid4()), merch_a_id, str(uuid.uuid4()), merch_b_id))
    admin_conn.close()

    # Worker connects as restricted wapsi_app
    app_engine = create_engine(f"postgresql+psycopg2://wapsi_app:{TEST_APP_PASSWORD}@localhost:{TEST_PG_PORT}/postgres")
    with Session(app_engine) as session:
        worker_id = "test_worker_bg_1"
        claimed = RecoveryOutboxRepository.claim_jobs(
            session=session,
            worker_id=worker_id,
            limit=10,
            lease_duration_seconds=60,
        )
        assert len(claimed) == 2
        job_a = next(j for j in claimed if j.case_id == "case_wrk_a")
        job_b = next(j for j in claimed if j.case_id == "case_wrk_b")

        assert str(job_a.merchant_id) == merch_a_id
        assert str(job_b.merchant_id) == merch_b_id
        assert job_a.status == "SENDING"
        assert job_a.worker_id == worker_id
        assert job_a.lease_expires_at is not None

        # Process Job A under Merchant A's context -> Succeeds!
        res_a = RecoveryOutboxRepository.complete_job(
            session=session,
            job_id=job_a.id,
            worker_id=worker_id,
            merchant_id=merch_a_id,
        )
        assert res_a is True

        # Process Job B: attempting to complete using Merchant A's context -> Fails (0 rows updated due to RLS!)
        res_cross_tamper = RecoveryOutboxRepository.complete_job(
            session=session,
            job_id=job_b.id,
            worker_id=worker_id,
            merchant_id=merch_a_id,  # Wrong merchant context!
        )
        assert res_cross_tamper is False

        # Process Job B under correct Merchant B context -> Succeeds!
        res_b = RecoveryOutboxRepository.complete_job(
            session=session,
            job_id=job_b.id,
            worker_id=worker_id,
            merchant_id=merch_b_id,
        )
        assert res_b is True


def test_outbox_deployed_schema_and_allowed_state_transitions(pg_cluster: DatabaseManager, app_db_url: str):
    """
    Verifies:
    - Actual deployed outbox columns: worker_id, lease_expires_at, case_id, payment_id.
    - Check constraint ck_outbox_status enforces:
      'QUEUED', 'SENDING', 'SENT', 'FAILED', 'RETRY', 'DEAD_LETTER', 'RECONCILIATION_REQUIRED', 'CANCELLED'
    """
    admin_conn = psycopg2.connect(f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres")
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        # Check columns exist in pg_attribute
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'recovery_outbox'
            ORDER BY column_name;
        """)
        cols = {r[0]: r[1] for r in cur.fetchall()}
        assert "worker_id" in cols
        assert "lease_expires_at" in cols
        assert "case_id" in cols
        assert "payment_id" in cols
        assert "status" in cols

        # Check that invalid statuses like 'PENDING' or 'PROCESSED' are strictly rejected
        merch_id = str(uuid.uuid4())
        cur.execute("INSERT INTO public.merchants (id, merchant_code, name, registered_email) VALUES (%s, 'SCHEMA_TEST', 'Schema Corp', 's@test.com');", (merch_id,))

        for invalid_status in ["PENDING", "PROCESSED", "COMPLETED", "UNKNOWN"]:
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute("""
                    INSERT INTO public.recovery_outbox (
                        merchant_id, idempotency_key, action, channel, recipient_masked,
                        message_payload, status
                    ) VALUES (%s, %s, 'whatsapp_nudge', 'whatsapp', '+91 99****1234', '{}'::jsonb, %s);
                """, (merch_id, f"idemp_{invalid_status}", invalid_status))

        # Check all 8 valid statuses are accepted
        valid_statuses = [
            "QUEUED", "SENDING", "SENT", "FAILED", "RETRY",
            "DEAD_LETTER", "RECONCILIATION_REQUIRED", "CANCELLED"
        ]
        for valid_status in valid_statuses:
            cur.execute("""
                INSERT INTO public.recovery_outbox (
                    merchant_id, idempotency_key, action, channel, recipient_masked,
                    message_payload, status
                ) VALUES (%s, %s, 'whatsapp_nudge', 'whatsapp', '+91 99****1234', '{}'::jsonb, %s);
            """, (merch_id, f"idemp_{valid_status}", valid_status))

    admin_conn.close()
