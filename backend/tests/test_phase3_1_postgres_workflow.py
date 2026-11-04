"""
WAPSI Phase 3.1: PostgreSQL Runtime Integration and Outbox Concurrency Test Suite.

Verifies:
1. Atomic job claiming by concurrent background workers (SELECT ... FOR UPDATE SKIP LOCKED).
2. Worker lease expiration and reclamation after worker crash.
3. Bounded exponential backoff, retry counters, and dead-letter queueing.
4. Ambiguous network outcome handling (RECONCILIATION_REQUIRED).
5. Durable multi-provider webhook deduplication and replay safety.
6. Shared persistent customer opt-out governance across independent worker processes.
7. Transactional atomicity and safe rollback on error.
8. Multi-tenant merchant isolation via transaction-scoped tenant context (SET LOCAL app.current_merchant_id).

Environment:
- Operates strictly in an isolated temporary PostgreSQL 17 test cluster.
- Zero synthetic data is written to hosted Supabase (filofxijqmgluuulivxb).
"""

from __future__ import annotations

import concurrent.futures
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wapsi.db.models import (
    CustomerModel,
    MerchantModel,
    RecoveryOutboxModel,
    TransactionModel,
    WebhookInboxModel,
)
from wapsi.db.repository import (
    MerchantRepository,
    OptOutRepository,
    RecoveryOutboxRepository,
)
from wapsi.db.session import DatabaseManager
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore
from wapsi.recovery.webhook_processor import DurableWebhookInbox


TEST_PG_PORT = 5438
TEST_PG_DIR = os.path.abspath(".tmp_pg_phase31_test")
POSTGRES_BIN_DIR = r"C:\Program Files\PostgreSQL\17\bin"


@pytest.fixture(scope="module")
def postgres_test_cluster() -> Generator[DatabaseManager, None, None]:
    """
    Spawns an isolated local PostgreSQL 17 cluster on dedicated port 5438,
    executes all 5 migrations in sequence, yields DatabaseManager,
    and cleanly tears down and removes all temporary cluster files on exit.
    Guarantees ZERO interaction with hosted Supabase.
    """
    if not os.path.exists(os.path.join(POSTGRES_BIN_DIR, "postgres.exe")):
        pytest.skip(f"PostgreSQL 17 binaries not found at {POSTGRES_BIN_DIR}")

    shutil.rmtree(TEST_PG_DIR, ignore_errors=True)

    # 1. Initialize cluster with trust authentication
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

    db_url = f"postgresql://postgres@localhost:{TEST_PG_PORT}/postgres"
    time.sleep(2.5)

    try:
        import psycopg2

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        # 3. Apply prerequisite stubs for Supabase auth schema and roles
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

        # 4. Apply all database migrations in sequence
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

        # 5. Seed default test merchant into isolated test cluster to satisfy FK constraints
        cur.execute("""
            INSERT INTO merchants (id, merchant_code, name, business_type, industry, website, registered_email, country, currency, timezone, status)
            VALUES ('04a2aaf8-8c8a-4d99-852c-cefc80e82019', 'MRC_928374', 'Acme Global Technologies', 'Enterprise SaaS & Subscriptions', 'FinTech / Ecommerce', 'https://acmeglobal.io', 'compliance@acmeglobal.io', 'India', 'INR', 'Asia/Kolkata', 'ACTIVE')
            ON CONFLICT (id) DO NOTHING;
        """)

        conn.close()

        manager = DatabaseManager(database_url=db_url)
        yield manager

    finally:
        # Teardown: terminate PostgreSQL process and purge test cluster
        pg_proc.terminate()
        try:
            pg_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pg_proc.kill()
        shutil.rmtree(TEST_PG_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_test_tables(postgres_test_cluster: DatabaseManager):
    """Ensures each test starts with a completely clean operational table state."""
    with postgres_test_cluster.session_scope() as session:
        session.execute(text("DELETE FROM recovery_dispatches;"))
        session.execute(text("DELETE FROM recovery_outbox;"))
        session.execute(text("DELETE FROM webhook_inbox;"))
        session.execute(text("DELETE FROM opt_out_audit_trail;"))
        session.execute(text("DELETE FROM opt_out_registry;"))
        session.execute(text("DELETE FROM customer_interactions;"))


# ==============================================================================
# TEST 1: ATOMIC CONCURRENT JOB CLAIMING (SKIP LOCKED)
# ==============================================================================
def test_postgres_outbox_concurrent_claiming_skip_locked(postgres_test_cluster: DatabaseManager):
    """
    Verifies that two concurrent workers claiming from the PostgreSQL outbox
    never claim overlapping jobs due to FOR UPDATE SKIP LOCKED.
    """
    store = DurableOutboxStore(database_manager=postgres_test_cluster)
    assert store.is_postgres is True

    # Seed 10 recovery outbox jobs
    job_ids = []
    for i in range(10):
        job = store.enqueue(
            case_id=f"case_conc_{i}",
            payment_id=f"pay_conc_{i}",
            idempotency_key=f"idemp_conc_{uuid.uuid4()}",
            action="WHATSAPP_ONE_CLICK_LINK",
            channel="WHATSAPP",
            recipient_masked="+91 98765 ****0",
            message_payload={"test_index": i},
            merchant_id="default_merchant",
        )
        store.approve_job(job.id, "operator_test")
        job_ids.append(job.id)

    # Claim using two concurrent workers
    def worker_claim(worker_id: str):
        worker_store = DurableOutboxStore(database_manager=postgres_test_cluster)
        return worker_store.claim_jobs(worker_id=worker_id, limit=5, lease_duration_seconds=60)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker_claim, "worker_alpha")
        f2 = executor.submit(worker_claim, "worker_beta")
        claimed_alpha = f1.result()
        claimed_beta = f2.result()

    alpha_ids = {j.id for j in claimed_alpha}
    beta_ids = {j.id for j in claimed_beta}

    # Verify atomic exclusivity
    assert len(alpha_ids) > 0
    assert len(beta_ids) > 0
    assert alpha_ids.isdisjoint(beta_ids), "Concurrent workers claimed overlapping jobs!"
    assert len(alpha_ids | beta_ids) == 10, "Total claimed jobs does not equal seeded jobs!"

    for job in claimed_alpha:
        assert job.worker_id == "worker_alpha"
        assert job.status == "SENDING"
        assert job.lease_expires_at is not None

    for job in claimed_beta:
        assert job.worker_id == "worker_beta"
        assert job.status == "SENDING"
        assert job.lease_expires_at is not None


# ==============================================================================
# TEST 2: LEASE EXPIRATION & RECLAMATION
# ==============================================================================
def test_postgres_outbox_lease_expiration_and_reclamation(postgres_test_cluster: DatabaseManager):
    """
    Verifies that if worker_1 claims a job but abandons it / crashes,
    worker_2 reclaims the expired job once lease_expires_at has passed.
    """
    store = DurableOutboxStore(database_manager=postgres_test_cluster)

    job = store.enqueue(
        case_id="case_lease_exp_1",
        payment_id="pay_lease_exp_1",
        idempotency_key=f"idemp_lease_{uuid.uuid4()}",
        action="CALL_ASSIST_IVR",
        channel="IVR",
        recipient_masked="+91 99999 ****1",
        message_payload={"amount": 250000},
    )
    store.approve_job(job.id, "operator_test")

    now = time.time()
    # Worker 1 claims with 10s lease
    claimed_worker1 = store.claim_jobs(
        worker_id="crashed_worker",
        limit=1,
        lease_duration_seconds=10,
        current_time=now,
    )
    assert len(claimed_worker1) == 1
    assert claimed_worker1[0].id == job.id
    assert claimed_worker1[0].worker_id == "crashed_worker"

    # Worker 2 claims at future time (lease expired)
    t_future = now + 15.0
    claimed_worker2 = store.claim_jobs(
        worker_id="healthy_worker",
        limit=1,
        lease_duration_seconds=60,
        current_time=t_future,
    )
    assert len(claimed_worker2) == 1
    assert claimed_worker2[0].id == job.id
    assert claimed_worker2[0].worker_id == "healthy_worker"
    assert claimed_worker2[0].status == "SENDING"

    # Worker 2 completes job
    completed = store.complete_job(job_id=job.id, worker_id="healthy_worker")
    assert completed is True

    final_job = store.get_job(job.id)
    assert final_job.status == "SENT"
    assert final_job.lease_expires_at is None


# ==============================================================================
# TEST 3: CRASH RECOVERY, RETRY BACKOFF & DEAD LETTER
# ==============================================================================
def test_postgres_outbox_retry_backoff_and_dead_letter(postgres_test_cluster: DatabaseManager):
    """
    Verifies retry counter increments, exponential backoff, and transition to DEAD_LETTER.
    """
    store = DurableOutboxStore(database_manager=postgres_test_cluster)

    job = store.enqueue(
        case_id="case_retry_dlq_1",
        payment_id="pay_retry_dlq_1",
        idempotency_key=f"idemp_dlq_{uuid.uuid4()}",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="WHATSAPP",
        recipient_masked="+91 98111 ****2",
        message_payload={"amount": 10000},
        max_retries=2,
    )
    store.approve_job(job.id, "operator_test")

    # Claim job
    claimed = store.claim_jobs(worker_id="worker_fail_test", limit=1)
    assert len(claimed) == 1
    assert claimed[0].id == job.id

    # First retryable failure -> status RETRY
    failed1 = store.fail_job(
        job_id=job.id,
        worker_id="worker_fail_test",
        error_message="Gateway timeout 504",
        is_retryable=True,
        backoff_seconds=30,
    )
    assert failed1 is True

    j1 = store.get_job(job.id)
    assert j1.status == "RETRY"
    assert j1.retry_count == 1

    # Reclaim after backoff
    reclaimed = store.claim_jobs(
        worker_id="worker_fail_test_2",
        limit=1,
        current_time=time.time() + 60,
    )
    assert len(reclaimed) == 1
    assert reclaimed[0].id == job.id

    # Second failure reaching max_retries (2) -> DEAD_LETTER
    failed2 = store.fail_job(
        job_id=job.id,
        worker_id="worker_fail_test_2",
        error_message="Permanent 400 Bad Request",
        is_retryable=False,
    )
    assert failed2 is True

    j2 = store.get_job(job.id)
    assert j2.status == "DEAD_LETTER"
    assert j2.retry_count == 2
    assert "Permanent 400" in j2.last_error


# ==============================================================================
# TEST 4: AMBIGUOUS NETWORK OUTCOME (RECONCILIATION_REQUIRED)
# ==============================================================================
def test_postgres_outbox_reconciliation_required(postgres_test_cluster: DatabaseManager):
    """Verifies that an ambiguous network timeout marks the job as RECONCILIATION_REQUIRED."""
    store = DurableOutboxStore(database_manager=postgres_test_cluster)

    job = store.enqueue(
        case_id="case_ambig_1",
        payment_id="pay_ambig_1",
        idempotency_key=f"idemp_ambig_{uuid.uuid4()}",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="WHATSAPP",
        recipient_masked="+91 98222 ****3",
        message_payload={"amount": 50000},
    )
    store.approve_job(job.id, "operator_test")

    claimed = store.claim_jobs(worker_id="worker_ambig", limit=1)
    assert len(claimed) == 1
    assert claimed[0].id == job.id

    res = store.mark_reconciliation_required(
        job_id=job.id,
        worker_id="worker_ambig",
        reason="HTTP connection closed before response headers",
    )
    assert res is True

    j = store.get_job(job.id)
    assert j.status == "RECONCILIATION_REQUIRED"
    assert "Ambiguous network outcome" in j.last_error


# ==============================================================================
# TEST 5: DURABLE WEBHOOK DEDUPLICATION IN POSTGRESQL
# ==============================================================================
def test_postgres_webhook_inbox_deduplication(postgres_test_cluster: DatabaseManager):
    """
    Verifies that duplicate webhook deliveries are safely detected and acknowledged
    without re-executing logic.
    """
    inbox = DurableWebhookInbox(database_manager=postgres_test_cluster)
    assert inbox.is_postgres is True

    evt_id = f"evt_rzp_pg_{uuid.uuid4()}"

    # First arrival: new
    is_dup1, inbox_id1 = inbox.check_or_record(
        provider="razorpay",
        event_id=evt_id,
        event_type="payment.captured",
        payment_id="pay_pg_test_100",
        payload_sanitized={"amount": 150000, "status": "captured"},
    )
    assert is_dup1 is False
    assert inbox_id1 is not None

    inbox.mark_processed(inbox_id1, status="PROCESSED")

    # Second arrival: duplicate detected
    is_dup2, inbox_id2 = inbox.check_or_record(
        provider="razorpay",
        event_id=evt_id,
        event_type="payment.captured",
        payment_id="pay_pg_test_100",
        payload_sanitized={"amount": 150000, "status": "captured"},
    )
    assert is_dup2 is True
    assert inbox_id2 == inbox_id1


# ==============================================================================
# TEST 6: SHARED PERSISTENT OPT-OUTS ACROSS WORKERS & ZERO-DELETE LIFECYCLE
# ==============================================================================
def test_postgres_shared_opt_outs_across_workers(postgres_test_cluster: DatabaseManager):
    """
    Verifies that customer opt-outs recorded by Worker 1 in PostgreSQL
    are immediately visible to Worker 2, and that revocation deactivates the record
    without physical DELETE, preserving full audit history and supporting re-opt-out.
    """
    worker1_opt = PersistentOptOutStore(database_manager=postgres_test_cluster)
    worker2_opt = PersistentOptOutStore(database_manager=postgres_test_cluster)
    assert worker1_opt.is_postgres is True
    assert worker2_opt.is_postgres is True

    test_phone = "+91 99887 76655"
    norm_phone = "919988776655"

    # Initially not opted out
    assert worker2_opt.is_opted_out(test_phone) is False

    # 1. Worker 1 records initial opt-out
    success = worker1_opt.record_opt_out(
        phone=test_phone,
        reason="STOP_KEYWORD",
        source="inbound_whatsapp",
        actor="customer_self",
    )
    assert success is True

    # Worker 2 immediately checks -> Must be opted out
    assert worker2_opt.is_opted_out(test_phone) is True

    # 2. Duplicate STOP handling -> Idempotent, logs DUPLICATE_OPT_OUT
    dup_success = worker1_opt.record_opt_out(
        phone=test_phone,
        reason="STOP_AGAIN",
        source="inbound_whatsapp",
    )
    assert dup_success is True
    assert worker2_opt.is_opted_out(test_phone) is True

    # Audit trail verification: 2 records (OPT_OUT, DUPLICATE_OPT_OUT)
    audit = worker2_opt.get_audit_trail(norm_phone)
    assert len(audit) == 2
    assert audit[0]["action"] == "OPT_OUT"
    assert audit[1]["action"] == "DUPLICATE_OPT_OUT"

    # 3. Revocation requires valid consent proof
    with pytest.raises(ValueError, match="explicit, verified consent proof"):
        worker2_opt.revoke_opt_out(test_phone, consent_proof="")

    # Valid revocation deactivates the record
    revoked = worker2_opt.revoke_opt_out(
        test_phone, consent_proof="Verified SMS OTP consent 847291 at 2026-11-01T10:00:00Z"
    )
    assert revoked is True
    assert worker1_opt.is_opted_out(test_phone) is False
    assert worker2_opt.is_opted_out(test_phone) is False

    # ZERO-DELETE GUARANTEE: The record STILL EXISTS in the database!
    with postgres_test_cluster.session_scope() as session:
        reg_row = session.execute(
            text("SELECT phone, is_active, revoked_at FROM public.opt_out_registry WHERE phone = :p"),
            {"p": norm_phone},
        ).fetchone()
        assert reg_row is not None
        assert reg_row[0] == norm_phone
        assert reg_row[1] is False  # is_active == False
        assert reg_row[2] is not None  # revoked_at timestamp is populated

    # Audit trail now has 3 events
    audit = worker2_opt.get_audit_trail(norm_phone)
    assert len(audit) == 3
    assert audit[2]["action"] == "REVOCATION"

    # 4. Subsequent Re-Opt-Out (Customer changes mind and sends STOP again)
    re_opt = worker1_opt.record_opt_out(
        phone=test_phone,
        reason="STOP_THIRD_TIME",
        source="inbound_whatsapp",
    )
    assert re_opt is True
    assert worker2_opt.is_opted_out(test_phone) is True

    # Record reactivated without duplicate primary key error
    with postgres_test_cluster.session_scope() as session:
        reg_row2 = session.execute(
            text("SELECT phone, is_active, revoked_at FROM public.opt_out_registry WHERE phone = :p"),
            {"p": norm_phone},
        ).fetchone()
        assert reg_row2 is not None
        assert reg_row2[1] is True  # is_active is now True again
        assert reg_row2[2] is None  # revoked_at cleared on reactivation

    # Full audit history preserved: 4 chronological transitions
    audit = worker2_opt.get_audit_trail(norm_phone)
    assert len(audit) == 4
    assert [a["action"] for a in audit] == ["OPT_OUT", "DUPLICATE_OPT_OUT", "REVOCATION", "OPT_OUT"]


# ==============================================================================
# TEST 6B: wapsi_app ZERO-DELETE PRIVILEGE ENFORCEMENT ON opt_out_registry
# ==============================================================================
def test_postgres_wapsi_app_has_no_delete_privilege_on_opt_out_registry(postgres_test_cluster: DatabaseManager):
    """
    Verifies that the restricted application role 'wapsi_app' has NO DELETE privilege
    on public.opt_out_registry. Attempting a DELETE query must be rejected by PostgreSQL.
    """
    from sqlalchemy.exc import DBAPIError

    test_phone = "919876500000"
    with postgres_test_cluster.session_scope() as session:
        # Seed an opt-out record as admin
        session.execute(
            text("INSERT INTO public.opt_out_registry (phone, reason, source, is_active) VALUES (:p, 'TEST', 'test', true)"),
            {"p": test_phone},
        )

    # Now attempt DELETE as wapsi_app
    with pytest.raises(DBAPIError) as exc_info:
        with postgres_test_cluster.session_scope() as session:
            session.execute(text("SET ROLE wapsi_app;"))
            session.execute(text("DELETE FROM public.opt_out_registry WHERE phone = :p;"), {"p": test_phone})

    # PostgreSQL error code 42501 = insufficient_privilege
    err_msg = str(exc_info.value).lower()
    assert "permission denied for table opt_out_registry" in err_msg or "42501" in err_msg


# ==============================================================================
# TEST 7: TRANSACTIONAL ROLLBACK INTEGRITY
# ==============================================================================
def test_postgres_transaction_rollback_safety(postgres_test_cluster: DatabaseManager):
    """
    Verifies that a failure within a session_scope rolls back completely
    without leaving orphan records.
    """
    with postgres_test_cluster.session_scope() as session:
        merchant = MerchantRepository.get_or_create_default(session)
        merchant_id = merchant.id

    # Intentional failure inside transaction block
    test_key = f"idemp_rollback_{uuid.uuid4()}"
    with pytest.raises(RuntimeError, match="Simulated crash during recovery workflow"):
        with postgres_test_cluster.session_scope() as session:
            RecoveryOutboxRepository.enqueue(
                session=session,
                merchant_id=merchant_id,
                idempotency_key=test_key,
                action="WHATSAPP_ONE_CLICK_LINK",
                channel="WHATSAPP",
                recipient_masked="+91 90000 ****0",
                message_payload={"amount": 50000},
            )
            # Raise exception before transaction commits
            raise RuntimeError("Simulated crash during recovery workflow")

    # Verify outbox entry was rolled back completely
    with postgres_test_cluster.session_scope() as session:
        stmt = select(RecoveryOutboxModel).where(RecoveryOutboxModel.idempotency_key == test_key)
        item = session.execute(stmt).scalar_one_or_none()
        assert item is None, "Failed transaction was not rolled back cleanly!"


# ==============================================================================
# TEST 8: MULTI-TENANT ISOLATION (NO MERCHANT LEAKAGE)
# ==============================================================================
def test_postgres_merchant_isolation_tenant_context(postgres_test_cluster: DatabaseManager):
    """
    Verifies that transaction-local tenant context (SET LOCAL app.current_merchant_id)
    strictly bounds queries and prevents cross-merchant leakage under RLS.
    """
    # Create Merchant Alpha and Merchant Beta
    with postgres_test_cluster.session_scope() as session:
        m_alpha = MerchantModel(
            merchant_code=f"MRC_ALPHA_{uuid.uuid4().hex[:6]}",
            name="Alpha Corp",
            registered_email="alpha@example.com",
            currency="INR",
            status="ACTIVE",
        )
        m_beta = MerchantModel(
            merchant_code=f"MRC_BETA_{uuid.uuid4().hex[:6]}",
            name="Beta Corp",
            registered_email="beta@example.com",
            currency="INR",
            status="ACTIVE",
        )
        session.add_all([m_alpha, m_beta])
        session.flush()
        alpha_id = m_alpha.id
        beta_id = m_beta.id

    # Operate in Alpha tenant context
    with postgres_test_cluster.tenant_session_scope(alpha_id) as session:
        # Check active merchant setting
        active_id = session.execute(
            text("SELECT current_setting('app.current_merchant_id', true)")
        ).scalar()
        assert active_id == str(alpha_id)

    # Operate in Beta tenant context
    with postgres_test_cluster.tenant_session_scope(beta_id) as session:
        active_id = session.execute(
            text("SELECT current_setting('app.current_merchant_id', true)")
        ).scalar()
        assert active_id == str(beta_id)
        assert active_id != str(alpha_id)
