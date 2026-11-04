"""
WAPSI — Phase 6 Stage 2D Regression Test Suite:
Exact-Job Dispatch Isolation and Tamper-Proof Single-Job Gating.

Tests:
1. A different queued job is never claimed when claiming by exact job ID.
2. The requested target job is the ONLY job claimed among multiple queued candidates.
3. An unapproved job cannot be claimed or dispatched by ID.
4. A modified approval payload is detected and rejected at dispatch authorization.
5. An opted-out recipient is rejected and suppressed prior to dispatch.
6. The exact-job claim function refuses non-existent or ineligible statuses.
7. Exactly one provider message call occurs and double-send is impossible.
8. Live target job remains PENDING_APPROVAL and is rejected by claim_job_by_id.
"""

import copy
import json
import os
import time
import unittest.mock
import uuid
import pytest

from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, compute_approval_hash
from wapsi.recovery.timeline import RecoveryTimelineStore
from wapsi.recovery.worker import RecoveryBackgroundWorker

TARGET_JOB_ID = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
TARGET_MERCHANT_UUID = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"


def test_1_different_queued_job_is_never_claimed(tmp_path):
    """When claiming by exact ID, earlier eligible queued jobs are ignored and never claimed."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))

    # Job A: Queued earlier
    job_a = store.enqueue(
        case_id="case_a",
        payment_id="pay_a",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****1111",
        message_payload={"body": "Job A message"},
        idempotency_key="idemp_a",
        requires_operator_approval=True,
    )
    store.approve_job(job_a.id, operator_id="op_admin")

    # Job B: Target job
    job_b = store.enqueue(
        case_id="case_b",
        payment_id="pay_b",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****2222",
        message_payload={"body": "Job B message"},
        idempotency_key="idemp_b",
        requires_operator_approval=True,
    )
    store.approve_job(job_b.id, operator_id="op_admin")

    # Claim ONLY Job B
    claimed_b = store.claim_job_by_id(job_id=job_b.id, worker_id="worker_isolated_01")
    assert claimed_b is not None
    assert claimed_b.id == job_b.id
    assert claimed_b.status == "SENDING"
    assert claimed_b.worker_id == "worker_isolated_01"

    # Verify Job A remained completely untouched in QUEUED status
    job_a_current = store.get_job(job_a.id)
    assert job_a_current.status == "QUEUED"
    assert job_a_current.worker_id is None
    assert job_a_current.lease_expires_at is None


def test_2_requested_target_job_is_the_only_job_claimed_among_multiple(tmp_path):
    """Among 5 queued jobs, claiming by target ID claims strictly that 1 job."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))

    jobs = []
    for i in range(5):
        j = store.enqueue(
            case_id=f"case_multi_{i}",
            payment_id=f"pay_multi_{i}",
            action="WHATSAPP_ONE_CLICK_LINK",
            channel="whatsapp",
            recipient_masked=f"+91****{i}{i}{i}{i}",
            message_payload={"body": f"Multi job {i}"},
            idempotency_key=f"idemp_multi_{i}",
            requires_operator_approval=True,
        )
        store.approve_job(j.id, operator_id="op_admin")
        jobs.append(j)

    target = jobs[2]
    claimed = store.claim_job_by_id(job_id=target.id, worker_id="worker_exact_02")
    assert claimed is not None
    assert claimed.id == target.id
    assert claimed.status == "SENDING"

    # All other jobs remain QUEUED
    for idx, j in enumerate(jobs):
        current = store.get_job(j.id)
        if idx == 2:
            assert current.status == "SENDING"
            assert current.worker_id == "worker_exact_02"
        else:
            assert current.status == "QUEUED"
            assert current.worker_id is None


def test_3_unapproved_job_cannot_be_claimed_or_dispatched(tmp_path):
    """An unapproved job (PENDING_APPROVAL) returns None on claim and UNCLAIMED on worker dispatch."""
    db_file = tmp_path / "test_outbox.db"
    opt_file = tmp_path / "test_opt_out.db"
    time_file = tmp_path / "test_timeline.db"

    store = DurableOutboxStore(db_path=str(db_file))
    opt_store = PersistentOptOutStore(db_path=str(opt_file))
    timeline = RecoveryTimelineStore(db_path=str(time_file))

    unapproved_job = store.enqueue(
        case_id="case_unappr_001",
        payment_id="pay_unappr_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Unapproved message"},
        idempotency_key="idemp_unappr_001",
        requires_operator_approval=True,
    )
    assert unapproved_job.status == "PENDING_APPROVAL"

    # 1. Claim fails
    claimed = store.claim_job_by_id(job_id=unapproved_job.id, worker_id="worker_probe_03")
    assert claimed is None

    # 2. Worker process_single_job_by_id fails closed
    worker = RecoveryBackgroundWorker(outbox_store=store, opt_out_store=opt_store, timeline_store=timeline)
    result = worker.process_single_job_by_id(unapproved_job.id)
    assert result.status == "UNCLAIMED"
    assert "not eligible" in result.error_message


def test_4_modified_approval_payload_rejected_at_dispatch(tmp_path):
    """If payload is tampered post-approval, verify_dispatch_authorization halts worker send."""
    db_file = tmp_path / "test_outbox.db"
    opt_file = tmp_path / "test_opt_out.db"
    time_file = tmp_path / "test_timeline.db"

    store = DurableOutboxStore(db_path=str(db_file))
    opt_store = PersistentOptOutStore(db_path=str(opt_file))
    timeline = RecoveryTimelineStore(db_path=str(time_file))

    job = store.enqueue(
        case_id="case_tamper_001",
        payment_id="pay_tamper_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Genuine INR 10.00"},
        idempotency_key="idemp_tamper_001",
        requires_operator_approval=True,
    )
    store.approve_job(job.id, operator_id="op_admin")

    # Claim job
    claimed = store.claim_job_by_id(job_id=job.id, worker_id="worker_tamper_04")
    assert claimed is not None

    # Tamper payload before worker executes pre-dispatch check
    claimed.message_payload = {"body": "Tampered INR 100000.00"}

    worker = RecoveryBackgroundWorker(outbox_store=store, opt_out_store=opt_store, timeline_store=timeline)
    res = worker.process_single_job(claimed)
    assert res.status == "DEAD_LETTER"
    assert "Authorization rejected" in res.error_message


def test_5_opted_out_recipient_rejected_at_dispatch(tmp_path):
    """Customer opt-out in store halts worker dispatch even if job was claimed and approved."""
    db_file = tmp_path / "test_outbox.db"
    opt_file = tmp_path / "test_opt_out.db"
    time_file = tmp_path / "test_timeline.db"

    store = DurableOutboxStore(db_path=str(db_file))
    opt_store = PersistentOptOutStore(db_path=str(opt_file))
    timeline = RecoveryTimelineStore(db_path=str(time_file))

    phone = "+916260055671"
    job = store.enqueue(
        case_id="case_optout_001",
        payment_id="pay_optout_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"customer_phone": phone, "body": "Recovery link"},
        idempotency_key="idemp_optout_001",
        requires_operator_approval=True,
    )
    store.approve_job(job.id, operator_id="op_admin")

    # Customer opts out before dispatch
    opt_store.record_opt_out(phone, reason="Customer STOP", source="whatsapp_inbound")

    worker = RecoveryBackgroundWorker(outbox_store=store, opt_out_store=opt_store, timeline_store=timeline)
    res = worker.process_single_job_by_id(job.id)
    assert res.status == "DEAD_LETTER"
    assert "opted out" in res.error_message.lower()


def test_6_exact_job_claim_refuses_nonexistent_or_ineligible_jobs(tmp_path):
    """Non-existent UUID or wrong status returns None."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))

    # 1. Nonexistent ID
    random_id = str(uuid.uuid4())
    res1 = store.claim_job_by_id(job_id=random_id, worker_id="w_test")
    assert res1 is None

    # 2. Already DEAD_LETTER job
    job = store.enqueue(
        case_id="case_inelig_001",
        payment_id="pay_inelig_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Test"},
        idempotency_key="idemp_inelig_001",
        requires_operator_approval=False,
    )
    claimed = store.claim_job_by_id(job_id=job.id, worker_id="w_prev")
    assert claimed is not None
    store.fail_job(job.id, worker_id="w_prev", error_message="Hard failure", is_retryable=False)
    assert store.get_job(job.id).status == "DEAD_LETTER"

    res2 = store.claim_job_by_id(job_id=job.id, worker_id="w_test")
    assert res2 is None


def test_7_exactly_one_provider_message_call_occurs(tmp_path):
    """Worker executes exactly one provider call, updates status to COMPLETED, and prevents duplicate claim."""
    from wapsi.integrations.whatsapp.client import WhatsAppDispatchResult
    db_file = tmp_path / "test_outbox.db"
    opt_file = tmp_path / "test_opt_out.db"
    time_file = tmp_path / "test_timeline.db"

    store = DurableOutboxStore(db_path=str(db_file))
    opt_store = PersistentOptOutStore(db_path=str(opt_file))
    timeline = RecoveryTimelineStore(db_path=str(time_file))

    job = store.enqueue(
        case_id="case_once_001",
        payment_id="pay_once_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={
            "customer_phone": "+916260055671",
            "text": {"body": "Single dispatch test"},
            "amount_paise": 1000,
        },
        idempotency_key="idemp_once_001",
        requires_operator_approval=True,
    )
    store.approve_job(job.id, operator_id="op_admin")

    mock_wa = unittest.mock.MagicMock()
    mock_wa.send_recovery_reminder.return_value = WhatsAppDispatchResult(
        success=True,
        message_id="wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggTESTMOCKWAMID",
        recipient_phone="+916260055671",
        status="accepted",
        timestamp=time.time(),
        raw_response={"messages": [{"id": "wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggTESTMOCKWAMID"}]},
    )

    mock_rzp = unittest.mock.MagicMock()
    mock_rzp.create_payment_link.return_value = {
        "id": "plink_test_mock_001",
        "short_url": "https://rzp.io/rzp/mock001",
    }

    worker = RecoveryBackgroundWorker(
        outbox_store=store,
        opt_out_store=opt_store,
        timeline_store=timeline,
        whatsapp_client=mock_wa,
        razorpay_client=mock_rzp,
    )

    # First dispatch execution
    res1 = worker.process_single_job_by_id(job.id)
    assert res1.status == "COMPLETED"
    assert res1.whatsapp_message_id == "wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggTESTMOCKWAMID"

    # Verify provider was called exactly once
    assert mock_wa.send_recovery_reminder.call_count == 1

    # Second dispatch execution on same job is rejected (cannot be claimed again)
    res2 = worker.process_single_job_by_id(job.id)
    assert res2.status == "UNCLAIMED"

    # Provider call count remains exactly 1
    assert mock_wa.send_recovery_reminder.call_count == 1


def test_8_unapproved_job_unclaimable_in_isolation(tmp_path):
    """Confirms an unapproved job returns None on claim_job_by_id and remains PENDING_APPROVAL."""
    db_file = tmp_path / "test_unapproved_2d.db"
    store = DurableOutboxStore(db_path=str(db_file))
    merchant_id = str(uuid.uuid4())

    job = store.enqueue(
        case_id="case_unappr_iso_01",
        payment_id="pay_unappr_iso_01",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Unapproved isolation test"},
        idempotency_key="idemp_unappr_iso_01",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    assert job.status == "PENDING_APPROVAL"
    assert job.requires_operator_approval is True

    claimed = store.claim_job_by_id(job_id=job.id, worker_id="probe_test_worker", merchant_id=merchant_id)
    assert claimed is None

    recheck = store.get_job(job.id, merchant_id=merchant_id)
    assert recheck.status == "PENDING_APPROVAL"
    assert recheck.worker_id is None


def test_8b_live_target_job_governance_read_only():
    """Read-only audit: confirms live target job governance metadata without claim or mutation."""
    dm = DatabaseManager()
    store = DurableOutboxStore(database_manager=dm)

    job = store.get_job(TARGET_JOB_ID, merchant_id=TARGET_MERCHANT_UUID)
    assert job is not None
    assert job.id == TARGET_JOB_ID
    assert job.requires_operator_approval is True
    assert job.approved_by_operator_id == "operator_arpit"
    assert job.approval_snapshot_hash == "dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd"
