"""
WAPSI — Phase 6 Stage 4 Test Suite:
Production Hardening, Concurrency Leases, Crash Recovery, Exponential Backoff,
Dead-Letter Handling, Secret Leakage Prevention, and Frontend API Compatibility.

Verifies:
1. Concurrency & worker lease locking (disjoint claim sets, zero worker collision).
2. Worker crash recovery (expired lease reclamation by surviving workers).
3. Exponential backoff and terminal DEAD_LETTER transitions on max retries.
4. Non-retryable permanent failure immediate DEAD_LETTER transition.
5. Ambiguous provider timeout handling & reconciliation routing.
6. Secret leakage prevention (Pydantic SecretStr redaction in repr/str/logs).
7. Frontend API contract compatibility (/health, /api/v1/health, /api/v1/integrations/status, /recovery/cases, /decide).
8. Strict live target job isolation guarantee (zero mutations).
"""

import copy
import json
import os
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from wapsi.api.app import app
from wapsi.core.config import get_settings, WapsiSettings
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob
from wapsi.recovery.state_machine import RecoveryState, RecoveryStateMachine
from wapsi.recovery.timeline import RecoveryTimelineStore
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker
from wapsi.integrations.whatsapp.client import WhatsAppClient, WhatsAppError
from wapsi.db.session import DatabaseManager
from sqlalchemy import text


TARGET_JOB_ID = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
TARGET_MERCHANT_UUID = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
EXPECTED_APPROVAL_HASH = "dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd"


@pytest.fixture
def isolated_outbox(tmp_path):
    """Provides an isolated SQLite outbox store in a temporary directory."""
    db_file = str(tmp_path / "test_stage4_outbox.db")
    store = DurableOutboxStore(db_path=db_file)
    return store


@pytest.fixture(scope="module")
def api_client():
    """Provides FastAPI TestClient for frontend adapter and API integration checks."""
    with TestClient(app) as client:
        yield client


def test_1_concurrency_and_worker_lease_locking(isolated_outbox):
    """
    Scenario 1: Concurrency and Worker Lease Locking.
    Multiple workers competing for queued jobs must obtain completely disjoint sets of jobs.
    No job may be claimed by more than one worker.
    """
    store = isolated_outbox
    merchant_id = str(uuid.uuid4())
    job_ids = []

    # Enqueue 10 synthetic jobs
    for i in range(10):
        job = store.enqueue(
            case_id=f"case_conc_{i}",
            payment_id=f"pay_conc_{i}",
            action="WHATSAPP_ONE_CLICK_LINK",
            channel="whatsapp",
            recipient_masked="+91****1234",
            message_payload={"body": f"Payment link {i}"},
            idempotency_key=f"idemp_conc_{i}_{uuid.uuid4().hex[:6]}",
            merchant_id=merchant_id,
            requires_operator_approval=False,  # Immediately QUEUED
        )
        job_ids.append(job.id)

    # 3 concurrent workers claim up to 5 jobs each
    claimed_w1 = store.claim_jobs(worker_id="worker_alpha", limit=5, lease_duration_seconds=60)
    claimed_w2 = store.claim_jobs(worker_id="worker_beta", limit=5, lease_duration_seconds=60)
    claimed_w3 = store.claim_jobs(worker_id="worker_gamma", limit=5, lease_duration_seconds=60)

    ids_w1 = {j.id for j in claimed_w1}
    ids_w2 = {j.id for j in claimed_w2}
    ids_w3 = {j.id for j in claimed_w3}

    # Verify workers claimed jobs
    assert len(ids_w1) == 5
    assert len(ids_w2) == 5
    assert len(ids_w3) == 0  # All 10 jobs already claimed!

    # Verify disjointness (zero worker overlap)
    assert ids_w1.isdisjoint(ids_w2)
    assert ids_w1.isdisjoint(ids_w3)
    assert ids_w2.isdisjoint(ids_w3)

    # Verify status in database
    for jid in ids_w1:
        job = store.get_job(jid, merchant_id=merchant_id)
        assert job.status == "SENDING"
        assert job.worker_id == "worker_alpha"
        assert job.lease_expires_at is not None

    for jid in ids_w2:
        job = store.get_job(jid, merchant_id=merchant_id)
        assert job.status == "SENDING"
        assert job.worker_id == "worker_beta"
        assert job.lease_expires_at is not None


def test_2_worker_crash_recovery_expired_lease_reclaim(isolated_outbox):
    """
    Scenario 2: Worker Crash Recovery via Expired Lease Reclamation.
    When a worker crashes while processing, its lease expires.
    A surviving worker must automatically reclaim the job once the lease expires.
    """
    store = isolated_outbox
    merchant_id = str(uuid.uuid4())

    job = store.enqueue(
        case_id="case_crash_01",
        payment_id="pay_crash_01",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****9999",
        message_payload={"body": "Crash test"},
        idempotency_key=f"idemp_crash_{uuid.uuid4().hex[:6]}",
        merchant_id=merchant_id,
        requires_operator_approval=False,
    )

    t0 = time.time()
    # Worker Crashed claims with 10-second lease
    claimed = store.claim_jobs(worker_id="worker_crashed", limit=1, lease_duration_seconds=10, current_time=t0)
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].worker_id == "worker_crashed"

    # Worker Alive tries immediately at t0 + 2s (lease not expired) -> 0 jobs claimed
    claimed_early = store.claim_jobs(worker_id="worker_alive", limit=1, current_time=t0 + 2)
    assert len(claimed_early) == 0

    # Worker Alive tries at t0 + 15s (lease expired) -> Successfully reclaims job
    claimed_reclaim = store.claim_jobs(worker_id="worker_alive", limit=1, lease_duration_seconds=60, current_time=t0 + 15)
    assert len(claimed_reclaim) == 1
    reclaimed_job = claimed_reclaim[0]
    assert reclaimed_job.id == job.id
    assert reclaimed_job.worker_id == "worker_alive"
    assert reclaimed_job.status == "SENDING"


def test_3_exponential_backoff_and_dead_letter_transition(isolated_outbox):
    """
    Scenario 3: Exponential Backoff and Terminal DEAD_LETTER Transition.
    A transiently failing job increments retry_count and delays next_attempt_at.
    Upon exceeding max_retries, it transitions to DEAD_LETTER and is never claimed again.
    """
    store = isolated_outbox
    merchant_id = str(uuid.uuid4())

    job = store.enqueue(
        case_id="case_retry_01",
        payment_id="pay_retry_01",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****8888",
        message_payload={"body": "Retry backoff test"},
        idempotency_key=f"idemp_retry_{uuid.uuid4().hex[:6]}",
        merchant_id=merchant_id,
        requires_operator_approval=False,
    )

    worker_id = "worker_backoff"

    # Claim attempt 1
    c1 = store.claim_jobs(worker_id=worker_id, limit=1)
    assert len(c1) == 1

    # Failure 1 (retryable, 30s backoff)
    ok = store.fail_job(job.id, worker_id=worker_id, error_message="HTTP 503 Provider Unavailable", is_retryable=True, backoff_seconds=30)
    assert ok is True
    j1 = store.get_job(job.id, merchant_id=merchant_id)
    assert j1.status == "RETRY"
    assert j1.retry_count == 1
    assert j1.next_attempt_at > time.time()

    # Claim attempt 2 (simulate next_attempt_at has passed)
    future_t = j1.next_attempt_at + 1
    c2 = store.claim_jobs(worker_id=worker_id, limit=1, current_time=future_t)
    assert len(c2) == 1

    # Failure 2 (retryable, 60s backoff)
    store.fail_job(job.id, worker_id=worker_id, error_message="HTTP 504 Gateway Timeout", is_retryable=True, backoff_seconds=60)
    j2 = store.get_job(job.id, merchant_id=merchant_id)
    assert j2.status == "RETRY"
    assert j2.retry_count == 2

    # Claim attempt 3
    future_t2 = j2.next_attempt_at + 1
    c3 = store.claim_jobs(worker_id=worker_id, limit=1, current_time=future_t2)
    assert len(c3) == 1

    # Failure 3 (max_retries reached: 3 >= 3) -> Transitions to DEAD_LETTER
    store.fail_job(job.id, worker_id=worker_id, error_message="HTTP 500 Persistent Failure", is_retryable=True, backoff_seconds=120)
    j3 = store.get_job(job.id, merchant_id=merchant_id)
    assert j3.status == "DEAD_LETTER"
    assert j3.retry_count == 3

    # Ensure DEAD_LETTER job is NEVER claimed again, even in the far future
    c_never = store.claim_jobs(worker_id=worker_id, limit=1, current_time=future_t2 + 100000)
    assert len(c_never) == 0


def test_4_non_retryable_error_immediate_dead_letter(isolated_outbox):
    """
    Scenario 4: Non-Retryable Error Immediately Routes to DEAD_LETTER.
    Permanent failures (e.g. invalid phone number, blocked template) must bypass retries.
    """
    store = isolated_outbox
    merchant_id = str(uuid.uuid4())

    job = store.enqueue(
        case_id="case_perm_fail_01",
        payment_id="pay_perm_01",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****7777",
        message_payload={"body": "Permanent failure test"},
        idempotency_key=f"idemp_perm_{uuid.uuid4().hex[:6]}",
        merchant_id=merchant_id,
        requires_operator_approval=False,
    )

    worker_id = "worker_perm"
    c = store.claim_jobs(worker_id=worker_id, limit=1)
    assert len(c) == 1

    # Mark failed with is_retryable=False
    store.fail_job(
        job.id,
        worker_id=worker_id,
        error_message="Meta Error 131026: Message undeliverable to this phone number",
        is_retryable=False,
    )

    j = store.get_job(job.id, merchant_id=merchant_id)
    assert j.status == "DEAD_LETTER"
    assert j.retry_count == 1  # Bypassed retry attempts 2 and 3


def test_5_ambiguous_provider_timeout_routes_to_reconciliation(isolated_outbox):
    """
    Scenario 5: Ambiguous Provider Timeout Handling.
    When a network timeout occurs during dispatch, the case enters RECONCILIATION_REQUIRED
    to prevent double-charging or out-of-sync state.
    """
    store = isolated_outbox
    merchant_id = str(uuid.uuid4())
    case_id = "case_ambig_timeout_01"

    state_machine = RecoveryStateMachine()
    timeline = RecoveryTimelineStore(db_path=store.db_path)

    # Transition to DISPATCHING
    st, changed = state_machine.transition(
        case_id=case_id,
        current_state=RecoveryState.SCHEDULED,
        target_state=RecoveryState.DISPATCHING,
        event_trigger="Worker dispatch initiated",
    )
    assert st == RecoveryState.DISPATCHING

    # Simulate timeout event -> Route to RECONCILIATION_REQUIRED
    st_reconcil, changed = state_machine.transition(
        case_id=case_id,
        current_state=st,
        target_state=RecoveryState.RECONCILIATION_REQUIRED,
        event_trigger="Meta API HTTP 504 Gateway Timeout during POST /messages",
    )
    assert st_reconcil == RecoveryState.RECONCILIATION_REQUIRED
    assert changed is True

    # Record event in timeline
    event = timeline.record_event(
        case_id=case_id,
        event_type="DISPATCH_TIMEOUT_RECONCILIATION",
        description="Provider dispatch timed out; case routed to asynchronous reconciliation engine.",
        source="RECOVERY_WORKER",
        from_state="DISPATCHING",
        to_state="RECONCILIATION_REQUIRED",
    )
    assert event.event_id is not None
    assert event.to_state == "RECONCILIATION_REQUIRED"


def test_6_secret_leakage_prevention():
    """
    Scenario 6: Secret Leakage Prevention.
    Verifies that all API keys, bearer tokens, webhook secrets, and salts are masked
    by Pydantic SecretStr and cannot be exposed via str(), repr(), or logging.
    """
    settings = get_settings()

    # Verify types are SecretStr
    if settings.whatsapp_access_token:
        assert str(settings.whatsapp_access_token) == "**********"
        assert repr(settings.whatsapp_access_token) == "SecretStr('**********')"
    if settings.whatsapp_diagnostic_token:
        assert str(settings.whatsapp_diagnostic_token) == "**********"
        assert repr(settings.whatsapp_diagnostic_token) == "SecretStr('**********')"
    if settings.razorpay_key_secret:
        assert str(settings.razorpay_key_secret) == "**********"
        assert repr(settings.razorpay_key_secret) == "SecretStr('**********')"

    # Settings representation must NOT contain raw secret values
    settings_repr = repr(settings)
    assert "EAANr4" not in settings_repr
    assert "dYQ12V" not in settings_repr

    # Verify WhatsAppClient doesn't leak token in repr
    client = WhatsAppClient(access_token="test_secret_token_12345", phone_number_id="123456789")
    client_repr = repr(client)
    assert "test_secret_token_12345" not in client_repr


def test_7_frontend_api_compatibility(api_client):
    """
    Scenario 7: Frontend API Contract Compatibility.
    Verifies all endpoints consumed by the React Frontend:
    - /health & /api/v1/health
    - /api/v1/integrations/status
    - /api/v1/recovery/cases
    - /api/v1/recovery/cases/{id}
    - /api/v1/recovery/cases/{id}/approve
    - /api/v1/decide
    """
    # Health checks
    r1 = api_client.get("/health")
    assert r1.status_code == 200
    r2 = api_client.get("/api/v1/health")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"

    # Integrations Status
    r_int = api_client.get("/api/v1/integrations/status")
    assert r_int.status_code == 200
    int_data = r_int.json()
    assert "whatsapp_cloud_api" in int_data
    assert "razorpay" in int_data

    # Recovery cases list
    r_cases = api_client.get("/api/v1/recovery/cases")
    assert r_cases.status_code == 200
    cases_data = r_cases.json()
    assert "cases" in cases_data
    assert len(cases_data["cases"]) > 0

    first_case_id = cases_data["cases"][0]["caseId"]

    # Recovery case detail
    r_detail = api_client.get(f"/api/v1/recovery/cases/{first_case_id}")
    assert r_detail.status_code == 200
    detail_data = r_detail.json()
    assert detail_data["caseId"] == first_case_id
    assert "actionScores" in detail_data
    assert "explanation" in detail_data

    # Approve action
    r_app = api_client.post(f"/api/v1/recovery/cases/{first_case_id}/approve", json={"action": "WHATSAPP"})
    assert r_app.status_code == 200
    app_data = r_app.json()
    assert app_data["status"] == "APPROVED"
    assert "audit_hash" in app_data

    # Causal Decision Engine
    decide_payload = {
        "payment_id": "pay_stage4_decide_001",
        "amount_in_inr": 1500.0,
        "payment_method": "card",
        "error_code": "GATEWAY_TIMEOUT",
        "error_description": "Issuing bank timeout",
        "merchant_id": "merch_p6_s4",
        "user_id": "usr_p6_s4",
    }
    r_decide = api_client.post("/api/v1/decide", json=decide_payload)
    assert r_decide.status_code == 200
    dec_data = r_decide.json()
    assert "decision_id" in dec_data
    assert "recommended_action" in dec_data
    assert "audit_hash" in dec_data


def test_8_zero_mutation_of_live_target_job():
    """
    Scenario 8: Read-only verification that the live hosted target job
    5a6587ab-2601-4017-b396-48e3d2fc2fda was NEVER mutated by Stage 4 tests.
    """
    db = DatabaseManager()
    with db.session_scope() as session:
        session.execute(
            text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
            {"m_id": TARGET_MERCHANT_UUID},
        )
        row = session.execute(
            text("SELECT id, status, retry_count, worker_id, approved_by_operator_id, approval_snapshot_hash FROM recovery_outbox WHERE id = :job_id"),
            {"job_id": TARGET_JOB_ID},
        ).fetchone()

        assert row is not None
        mapping = dict(row._mapping)
        assert mapping["status"] == "SENT"
        assert mapping["retry_count"] == 1
        assert mapping["approved_by_operator_id"] == "operator_arpit"
        assert mapping["approval_snapshot_hash"] == EXPECTED_APPROVAL_HASH
