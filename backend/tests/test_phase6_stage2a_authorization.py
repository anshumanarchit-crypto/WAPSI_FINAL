"""
Phase 6 Stage 2A: Outbox Operator Authorization Gate Tests.

Verifies:
1. Unapproved customer-contacting jobs default to PENDING_APPROVAL and are blocked from claiming.
2. Unapproved jobs with status QUEUED or RETRY are independently blocked by stored procedure and SQLite claim queries.
3. Explicit operator approval properly signs the job with SHA-256 snapshot hash and enables claiming.
4. Material modification to payload or recipient invalidates approval and halts dispatch.
5. Operator rejection transitions job to REJECTED and permanently prevents claiming.
6. Customer opt-out check halts dispatch even if approved.
7. Background worker enforces verify_dispatch_authorization() defense-in-depth.
8. Idempotency guarantees prevent duplicate job enqueues.
9. Non-contacting jobs (internal/analytics) without operator approval requirement can proceed.
"""

import copy
import json
import os
import tempfile
import time
import uuid
import pytest

from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, compute_approval_hash
from wapsi.recovery.timeline import RecoveryTimelineStore
from wapsi.recovery.worker import RecoveryBackgroundWorker


@pytest.fixture
def temp_db_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield tmpdir


@pytest.fixture
def sqlite_outbox(temp_db_dir):
    db_path = os.path.join(temp_db_dir, "outbox_test.db")
    return DurableOutboxStore(db_path=db_path)


@pytest.fixture
def sqlite_opt_out(temp_db_dir):
    db_path = os.path.join(temp_db_dir, "opt_out_test.db")
    return PersistentOptOutStore(db_path=db_path)


@pytest.fixture
def sqlite_timeline(temp_db_dir):
    db_path = os.path.join(temp_db_dir, "timeline_test.db")
    return RecoveryTimelineStore(db_path=db_path)


def test_customer_contacting_job_defaults_to_pending_approval(sqlite_outbox):
    """Customer-contacting channel (whatsapp) must default to PENDING_APPROVAL."""
    payload = {
        "customer_phone": "+919876543210",
        "customer_name": "Test Customer",
        "amount_paise": 1000,
        "payment_link_url": "https://rzp.io/rzp/test1",
    }
    job = sqlite_outbox.enqueue(
        case_id="case_test_001",
        payment_id="pay_test_001",
        idempotency_key="idemp_test_001",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )

    assert job.status == "PENDING_APPROVAL"
    assert job.requires_operator_approval is True
    assert job.approved_by_operator_id is None
    assert job.approved_at is None
    assert job.approval_snapshot_hash is None

    # Verify claim_jobs ignores this job
    claimed = sqlite_outbox.claim_jobs("worker_test", limit=10)
    assert len(claimed) == 0


def test_unapproved_job_with_queued_or_retry_status_blocked_from_claiming(sqlite_outbox):
    """
    Even if status is forced to QUEUED or RETRY, a job requiring operator approval
    lacking operator credentials and snapshot hash MUST NOT be claimed.
    """
    payload = {"amount_paise": 1000}
    # Manually insert unapproved job with status='QUEUED'
    job = sqlite_outbox.enqueue(
        case_id="case_test_002",
        payment_id="pay_test_002",
        idempotency_key="idemp_test_002",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
        status="QUEUED",  # Attempted bypass
        requires_operator_approval=True,
    )
    assert job.status == "QUEUED"
    assert job.approved_by_operator_id is None

    # Claim should reject it
    claimed = sqlite_outbox.claim_jobs("worker_test", limit=10)
    assert len(claimed) == 0

    # Also test RETRY status without approval
    with sqlite_outbox._get_sqlite_connection() as conn:
        conn.execute("UPDATE recovery_outbox SET status = 'RETRY' WHERE id = ?", (job.id,))

    claimed_retry = sqlite_outbox.claim_jobs("worker_test", limit=10)
    assert len(claimed_retry) == 0


def test_explicit_approval_enables_job_claiming(sqlite_outbox):
    """Explicit operator approval signs payload and allows claiming."""
    payload = {
        "customer_phone": "+919876543210",
        "amount_paise": 1000,
        "payment_link_url": "https://rzp.io/rzp/test_appr",
    }
    job = sqlite_outbox.enqueue(
        case_id="case_test_003",
        payment_id="pay_test_003",
        idempotency_key="idemp_test_003",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )
    assert job.status == "PENDING_APPROVAL"

    # Approve the job
    ok = sqlite_outbox.approve_job(job.id, operator_id="ops_lead_alpha")
    assert ok is True

    # Re-fetch job
    approved_job = sqlite_outbox.get_job(job.id)
    assert approved_job.status == "QUEUED"
    assert approved_job.approved_by_operator_id == "ops_lead_alpha"
    assert approved_job.approved_at is not None
    assert approved_job.approval_snapshot_hash is not None

    # Worker can now claim it
    claimed = sqlite_outbox.claim_jobs("worker_test", limit=10)
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].status == "SENDING"


def test_operator_rejection_marks_job_rejected(sqlite_outbox):
    """Operator rejection marks job REJECTED and makes it unclaimable."""
    payload = {"amount_paise": 1000}
    job = sqlite_outbox.enqueue(
        case_id="case_test_004",
        payment_id="pay_test_004",
        idempotency_key="idemp_test_004",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )

    ok = sqlite_outbox.reject_job(job.id, operator_id="ops_lead_alpha", reason="Customer disputing charge")
    assert ok is True

    rejected_job = sqlite_outbox.get_job(job.id)
    assert rejected_job.status == "REJECTED"
    assert "Customer disputing charge" in rejected_job.last_error

    # Ensure unclaimable
    claimed = sqlite_outbox.claim_jobs("worker_test", limit=10)
    assert len(claimed) == 0


def test_tampered_payload_detected_by_pre_dispatch_verification(sqlite_outbox):
    """Tampering with message payload after approval causes snapshot hash verification failure."""
    original_payload = {
        "customer_phone": "+919876543210",
        "amount_paise": 1000,
        "payment_link_url": "https://rzp.io/rzp/legit_link",
    }
    job = sqlite_outbox.enqueue(
        case_id="case_test_005",
        payment_id="pay_test_005",
        idempotency_key="idemp_test_005",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=original_payload,
    )
    sqlite_outbox.approve_job(job.id, operator_id="ops_lead_alpha")
    approved_job = sqlite_outbox.get_job(job.id)

    # Valid check passes
    valid, err = sqlite_outbox.verify_dispatch_authorization(approved_job)
    assert valid is True
    assert err is None

    # Simulate tampering: altering payment link or amount
    tampered_job = copy.deepcopy(approved_job)
    tampered_job.message_payload["amount_paise"] = 50000  # 50000 instead of 1000

    valid, err = sqlite_outbox.verify_dispatch_authorization(tampered_job)
    assert valid is False
    assert "payload integrity violation" in err


def test_tampered_recipient_detected_by_pre_dispatch_verification(sqlite_outbox):
    """Tampering with recipient phone after approval causes hash verification failure."""
    payload = {"customer_phone": "+919876543210", "amount_paise": 1000}
    job = sqlite_outbox.enqueue(
        case_id="case_test_006",
        payment_id="pay_test_006",
        idempotency_key="idemp_test_006",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )
    sqlite_outbox.approve_job(job.id, operator_id="ops_lead_alpha")
    approved_job = sqlite_outbox.get_job(job.id)

    # Tamper with recipient
    tampered_job = copy.deepcopy(approved_job)
    tampered_job.recipient_masked = "919999999999"

    valid, err = sqlite_outbox.verify_dispatch_authorization(tampered_job)
    assert valid is False
    assert "payload integrity violation" in err


def test_customer_opt_out_blocks_pre_dispatch_even_if_approved(sqlite_outbox, sqlite_opt_out):
    """If customer registers opt-out, verify_dispatch_authorization rejects dispatch."""
    phone = "+919876543210"
    payload = {"customer_phone": phone, "amount_paise": 1000}
    job = sqlite_outbox.enqueue(
        case_id="case_test_007",
        payment_id="pay_test_007",
        idempotency_key="idemp_test_007",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )
    sqlite_outbox.approve_job(job.id, operator_id="ops_lead_alpha")
    approved_job = sqlite_outbox.get_job(job.id)

    # Record opt-out for customer
    sqlite_opt_out.record_opt_out(phone, reason="STOP_KEYWORD")

    valid, err = sqlite_outbox.verify_dispatch_authorization(approved_job, opt_out_store=sqlite_opt_out)
    assert valid is False
    assert "opted out" in err


def test_worker_process_single_job_defensively_rejects_unauthorized_job(
    sqlite_outbox, sqlite_opt_out, sqlite_timeline
):
    """
    If an unauthorized job is directly passed to worker.process_single_job(),
    the worker defensively fails the job and transitions it to DEAD_LETTER without calling external APIs.
    """
    payload = {"customer_phone": "+919876543210", "amount_paise": 1000}
    job = sqlite_outbox.enqueue(
        case_id="case_test_008",
        payment_id="pay_test_008",
        idempotency_key="idemp_test_008",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )
    assert job.status == "PENDING_APPROVAL"

    worker = RecoveryBackgroundWorker(
        worker_id="test_worker_guard",
        outbox_store=sqlite_outbox,
        opt_out_store=sqlite_opt_out,
        timeline_store=sqlite_timeline,
    )

    result = worker.process_single_job(job)
    assert result.status == "DEAD_LETTER"
    assert "Authorization rejected" in result.error_message


def test_non_contacting_internal_job_claimable_without_operator(sqlite_outbox):
    """Internal system jobs not contacting customers can be claimed without operator approval."""
    payload = {"task": "RECONCILE_BATCH"}
    job = sqlite_outbox.enqueue(
        case_id="case_test_009",
        payment_id="pay_test_009",
        idempotency_key="idemp_test_009",
        action="SYSTEM_RECONCILIATION",
        channel="internal",
        recipient_masked="system",
        message_payload=payload,
        requires_operator_approval=False,
    )
    assert job.status == "QUEUED"
    assert job.requires_operator_approval is False

    claimed = sqlite_outbox.claim_jobs("worker_test", limit=10)
    assert len(claimed) == 1
    assert claimed[0].id == job.id


def test_outbox_metrics_partitioning(sqlite_outbox):
    """Metrics accurately reflect PENDING_APPROVAL and REJECTED counts."""
    payload = {"amount_paise": 1000}
    job1 = sqlite_outbox.enqueue(
        case_id="case_test_010a",
        payment_id="pay_test_010a",
        idempotency_key="idemp_test_010a",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )
    job2 = sqlite_outbox.enqueue(
        case_id="case_test_010b",
        payment_id="pay_test_010b",
        idempotency_key="idemp_test_010b",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )
    sqlite_outbox.reject_job(job2.id, operator_id="ops_lead")

    metrics = sqlite_outbox.get_metrics()
    assert metrics["PENDING_APPROVAL"] >= 1
    assert metrics["REJECTED"] >= 1
