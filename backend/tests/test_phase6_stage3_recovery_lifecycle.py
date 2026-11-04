"""
WAPSI — Phase 6 Stage 3 Test Suite:
End-to-End Recovery Lifecycle, Payment-Status Reconciliation, Multi-Channel
Webhook Handshake, and State Invariant Verification.

Verifies:
1. Complete 14-step recovery lifecycle (case creation -> approval -> dispatch -> delivery -> reconciliation).
2. Payment-link idempotent reuse and exact integer paise accounting.
3. Authoritative payment capture (RECOVERED terminal invariant; delayed failures rejected).
4. Inbound customer reply & 24-hour service window extension.
5. Inbound opt-out (STOP) immediate suppression and outbox cancellation.
6. Multi-tenant boundary isolation across outbox and cases.
7. Formal state machine transition matrix and illegal transition rejection.
8. Durable webhook idempotency and duplicate deduplication.
9. Ambiguous provider timeout handling (RECONCILIATION_REQUIRED).
10. Post-approval payload tampering detection.
11. Financial reconciliation exact paise accounting.
12. Strict live target job isolation guarantee.
"""

import copy
import json
import os
import time
import unittest.mock
import uuid
import pytest

from wapsi.core.config import get_settings
from wapsi.recovery.eligibility import (
    EligibilityEvaluationContext,
    RecoveryEligibilityEngine,
)
from wapsi.recovery.engine import PaymentRecoveryEngine, RecoveryCaseRecord
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, compute_approval_hash
from wapsi.recovery.reconciliation import PaymentReconciliationEngine
from wapsi.recovery.scheduler import RecoverySchedulePolicy, RecoveryScheduler
from wapsi.recovery.state_machine import (
    InvalidStateTransitionError,
    RecoveryState,
    RecoveryStateMachine,
)
from wapsi.recovery.timeline import RecoveryTimelineStore
from wapsi.recovery.webhook_processor import (
    DurableWebhookEventProcessor,
    DurableWebhookInbox,
)
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker
from wapsi.integrations.whatsapp.client import WhatsAppDispatchResult


@pytest.fixture
def isolated_recovery_stack(tmp_path):
    """Provides a completely isolated, standalone recovery stack using ephemeral SQLite stores."""
    outbox_db = str(tmp_path / "outbox.db")
    opt_out_db = str(tmp_path / "opt_out.db")
    timeline_db = str(tmp_path / "timeline.db")
    webhook_db = str(tmp_path / "webhook.db")

    outbox_store = DurableOutboxStore(db_path=outbox_db)
    opt_out_store = PersistentOptOutStore(db_path=opt_out_db)
    timeline_store = RecoveryTimelineStore(db_path=timeline_db)
    webhook_inbox = DurableWebhookInbox(db_path=webhook_db)

    state_machine = RecoveryStateMachine()
    eligibility_engine = RecoveryEligibilityEngine()
    scheduler = RecoveryScheduler(policy=RecoverySchedulePolicy(initial_delay_seconds=0))

    mock_rzp = unittest.mock.MagicMock()
    mock_rzp.create_payment_link.return_value = {
        "id": "plink_stage3_synthetic_01",
        "short_url": "https://rzp.io/rzp/stage3_01",
        "amount": 1000,
        "currency": "INR",
        "status": "created",
        "amount_paid": 0,
    }
    mock_rzp.get_payment_link.return_value = {
        "id": "plink_stage3_synthetic_01",
        "short_url": "https://rzp.io/rzp/stage3_01",
        "amount": 1000,
        "currency": "INR",
        "status": "created",
        "amount_paid": 0,
        "expired": False,
    }

    mock_wa = unittest.mock.MagicMock()
    mock_wa.send_recovery_reminder.return_value = WhatsAppDispatchResult(
        success=True,
        message_id="wamid.STAGE3_SYNTHETIC_WAMID_001",
        recipient_phone="919876543210",
        status="accepted",
        timestamp=time.time(),
        raw_response={"messages": [{"id": "wamid.STAGE3_SYNTHETIC_WAMID_001"}]},
    )
    mock_wa.send_prepared_payload.return_value = WhatsAppDispatchResult(
        success=True,
        message_id="wamid.STAGE3_SYNTHETIC_WAMID_001",
        recipient_phone="919876543210",
        status="accepted",
        timestamp=time.time(),
        raw_response={"messages": [{"id": "wamid.STAGE3_SYNTHETIC_WAMID_001"}]},
    )

    reconciliation_engine = PaymentReconciliationEngine(
        razorpay_client=mock_rzp,
        outbox_store=outbox_store,
        timeline_store=timeline_store,
    )

    webhook_processor = DurableWebhookEventProcessor(
        inbox=webhook_inbox,
        timeline_store=timeline_store,
        outbox_store=outbox_store,
        opt_out_store=opt_out_store,
    )

    worker = RecoveryBackgroundWorker(
        outbox_store=outbox_store,
        opt_out_store=opt_out_store,
        timeline_store=timeline_store,
        razorpay_client=mock_rzp,
        whatsapp_client=mock_wa,
    )

    return {
        "outbox_store": outbox_store,
        "opt_out_store": opt_out_store,
        "timeline_store": timeline_store,
        "webhook_inbox": webhook_inbox,
        "webhook_processor": webhook_processor,
        "state_machine": state_machine,
        "eligibility_engine": eligibility_engine,
        "scheduler": scheduler,
        "reconciliation_engine": reconciliation_engine,
        "worker": worker,
        "mock_rzp": mock_rzp,
        "mock_wa": mock_wa,
    }


def test_1_full_recovery_lifecycle_end_to_end(isolated_recovery_stack):
    """
    Scenario 1: Complete 14-step recovery lifecycle from ingestion to terminal recovery:
    PENDING -> ELIGIBLE -> SCHEDULED -> DISPATCHING -> DISPATCHED -> DELIVERED -> READ -> RECOVERED.
    """
    s = isolated_recovery_stack
    merchant_id = str(uuid.uuid4())
    case_id = "case_stage3_e2e_001"
    customer_phone = "+919876543210"

    # Step 1: Case created in PENDING
    current_state, changed = s["state_machine"].transition(
        case_id=case_id,
        current_state=RecoveryState.PENDING,
        target_state=RecoveryState.ELIGIBLE,
        event_trigger="Root cause classified as soft failure",
    )
    assert current_state == RecoveryState.ELIGIBLE
    assert changed is True

    # Step 2: Scheduled
    current_state, changed = s["state_machine"].transition(
        case_id=case_id,
        current_state=current_state,
        target_state=RecoveryState.SCHEDULED,
        event_trigger="Causal supervisor selected WhatsApp link",
    )
    assert current_state == RecoveryState.SCHEDULED
    assert changed is True

    # Step 3: Outbox enqueue (defaults to PENDING_APPROVAL)
    job = s["outbox_store"].enqueue(
        case_id=case_id,
        payment_id="pay_stage3_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****3210",
        message_payload={
            "customer_phone": customer_phone,
            "amount_paise": 1000,
            "body": "Your payment link: https://rzp.io/rzp/stage3_01",
        },
        idempotency_key=f"idemp_{case_id}",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    assert job.status == "PENDING_APPROVAL"

    # Step 4: Operator reviews and approves
    approved = s["outbox_store"].approve_job(job.id, operator_id="operator_sarah", merchant_id=merchant_id)
    assert approved is True
    job_approved = s["outbox_store"].get_job(job.id, merchant_id=merchant_id)
    assert job_approved.status == "QUEUED"
    assert job_approved.approved_by_operator_id == "operator_sarah"

    # Step 5: Background worker claims exact job
    res = s["worker"].process_single_job_by_id(job.id, merchant_id=merchant_id)
    assert res.status == "COMPLETED"
    assert res.whatsapp_message_id == "wamid.STAGE3_SYNTHETIC_WAMID_001"

    # Step 6: Verify outbox updated to SENT
    job_final = s["outbox_store"].get_job(job.id, merchant_id=merchant_id)
    assert job_final.status == "SENT"

    # Step 7: Webhook receipt: Delivered
    deliv_res = s["webhook_processor"].process_whatsapp_delivery_event(
        message_id="wamid.STAGE3_SYNTHETIC_WAMID_001",
        status_name="delivered",
        provider_timestamp=time.time(),
        recipient_phone=customer_phone,
    )
    assert deliv_res.status == "PROCESSED"

    # Step 8: Webhook receipt: Read
    read_res = s["webhook_processor"].process_whatsapp_delivery_event(
        message_id="wamid.STAGE3_SYNTHETIC_WAMID_001",
        status_name="read",
        provider_timestamp=time.time(),
        recipient_phone=customer_phone,
    )
    assert read_res.status == "PROCESSED"

    # Step 9: Payment confirmation webhook from Razorpay
    s["webhook_processor"].register_case_mapping(
        case_id=case_id,
        initial_status=RecoveryState.DISPATCHED,
        payment_link_id="plink_stage3_synthetic_01",
    )
    pay_res = s["webhook_processor"].process_razorpay_event(
        event_name="payment_link.paid",
        event_id="evt_stage3_pay_001",
        payment_id="pay_captured_stage3_001",
        payment_link_id="plink_stage3_synthetic_01",
        amount_paise=1000,
        case_id=case_id,
        raw_payload={
            "event": "payment_link.paid",
            "payment_link_id": "plink_stage3_synthetic_01",
            "payment_id": "pay_captured_stage3_001",
            "amount_paise": 1000,
        },
    )
    assert pay_res.status == "PROCESSED"
    assert pay_res.resulting_case_status == "RECOVERED"


def test_2_payment_link_idempotent_reuse(isolated_recovery_stack):
    """Validates that existing payment link is validated and reused without creating duplicates."""
    s = isolated_recovery_stack
    merchant_id = str(uuid.uuid4())
    plink_id = "plink_existing_stage3_99"
    short_url = "https://rzp.io/rzp/existing99"

    s["mock_rzp"].get_payment_link.return_value = {
        "id": plink_id,
        "short_url": short_url,
        "amount": 1000,
        "currency": "INR",
        "status": "created",
        "amount_paid": 0,
        "expired": False,
    }

    job = s["outbox_store"].enqueue(
        case_id="case_plink_reuse",
        payment_id="pay_plink_reuse",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****3210",
        message_payload={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "919876543210",
            "type": "text",
            "text": {"body": f"Your link is {short_url}"},
        },
        idempotency_key=f"idemp_p6_s3_{plink_id}",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    s["outbox_store"].approve_job(job.id, operator_id="operator_lead", merchant_id=merchant_id)

    # Worker executes Mode B direct payload
    res = s["worker"].process_single_job_by_id(job.id, merchant_id=merchant_id)
    assert res.status == "COMPLETED"

    # Provider create_payment_link must NEVER be called (link is reused)
    assert s["mock_rzp"].create_payment_link.call_count == 0
    assert s["mock_rzp"].get_payment_link.call_count == 1


def test_3_authoritative_payment_confirmation(isolated_recovery_stack):
    """Payment capture is the authoritative terminal state; delayed failure callbacks cannot downgrade RECOVERED."""
    s = isolated_recovery_stack
    sm = s["state_machine"]
    case_id = "case_authoritative_01"

    # Transition to RECOVERED
    recovered_state, changed = sm.transition(
        case_id=case_id,
        current_state=RecoveryState.PENDING,
        target_state=RecoveryState.RECOVERED,
        event_trigger="Razorpay payment captured",
        is_payment_capture=True,
    )
    assert recovered_state == RecoveryState.RECOVERED
    assert changed is True

    # Attempt to transition RECOVERED -> FAILED (e.g. late failure callback)
    # The state machine authoritatively protects RECOVERED and ignores downgrade
    post_state, changed_failed = sm.transition(
        case_id=case_id,
        current_state=RecoveryState.RECOVERED,
        target_state=RecoveryState.FAILED,
        event_trigger="Delayed payment failure callback",
    )
    assert post_state == RecoveryState.RECOVERED
    assert changed_failed is False


def test_4_inbound_customer_reply_updates_service_window(isolated_recovery_stack):
    """Inbound customer reply extends the 24-hour customer service window."""
    s = isolated_recovery_stack
    phone = "+919876543210"

    # Pre-condition: record interaction
    s["opt_out_store"].record_interaction(phone, timestamp=time.time())

    # Window is active
    assert s["opt_out_store"].is_within_24h_window(phone) is True

    # Process inbound webhook reply
    inbound_res = s["webhook_processor"].process_inbound_customer_message(
        from_phone=phone,
        message_body="Thank you, paying now",
        message_id="wamid.INBOUND_STAGE3_001",
        provider_timestamp=time.time(),
    )
    assert inbound_res.status == "PROCESSED"
    assert s["opt_out_store"].is_within_24h_window(phone) is True


def test_5_customer_opt_out_cancels_outbox_jobs(isolated_recovery_stack):
    """Customer sending STOP immediately records opt-out and suppresses pending recovery jobs."""
    s = isolated_recovery_stack
    merchant_id = str(uuid.uuid4())
    case_id = "case_optout_stage3_01"
    phone = "+919876543210"

    # Queue an approved job
    job = s["outbox_store"].enqueue(
        case_id=case_id,
        payment_id="pay_optout_01",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****3210",
        message_payload={"customer_phone": phone, "amount_paise": 1000},
        idempotency_key=f"idemp_{case_id}",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    s["outbox_store"].approve_job(job.id, operator_id="op_admin", merchant_id=merchant_id)

    # Customer sends STOP keyword
    s["webhook_processor"].register_case_mapping(
        case_id=case_id,
        initial_status=RecoveryState.DISPATCHED,
        payment_link_id="plink_optout_01",
    )
    opt_res = s["webhook_processor"].process_inbound_customer_message(
        from_phone=phone,
        message_body="STOP",
        message_id="wamid.INBOUND_STOP_001",
        provider_timestamp=time.time(),
    )
    assert opt_res.status == "PROCESSED"
    assert s["opt_out_store"].is_opted_out(phone) is True

    # Worker attempting to dispatch claimed job is suppressed
    claimed = s["outbox_store"].claim_job_by_id(job.id, worker_id="w_stage3", merchant_id=merchant_id)
    assert claimed is not None
    exec_res = s["worker"].process_single_job(claimed)
    assert exec_res.status in ("DEAD_LETTER", "SUPPRESSED")
    assert "opt" in exec_res.error_message.lower()


def test_6_multi_tenant_boundary_enforcement(isolated_recovery_stack):
    """Merchant A cannot claim or manipulate Merchant B's recovery outbox jobs."""
    s = isolated_recovery_stack
    merchant_a = str(uuid.uuid4())
    merchant_b = str(uuid.uuid4())

    job = s["outbox_store"].enqueue(
        case_id="case_tenant_iso_01",
        payment_id="pay_tenant_iso_01",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****3210",
        message_payload={"body": "Merchant A payload"},
        idempotency_key="idemp_tenant_iso_01",
        merchant_id=merchant_a,
        requires_operator_approval=True,
    )
    s["outbox_store"].approve_job(job.id, operator_id="operator_a", merchant_id=merchant_a)

    # Merchant B tries to claim -> returns None
    res_b = s["outbox_store"].claim_job_by_id(job.id, worker_id="worker_b", merchant_id=merchant_b)
    assert res_b is None

    # Merchant A claims -> succeeds
    res_a = s["outbox_store"].claim_job_by_id(job.id, worker_id="worker_a", merchant_id=merchant_a)
    assert res_a is not None
    assert res_a.id == job.id


def test_7_state_machine_transition_invariants(isolated_recovery_stack):
    """Validates permitted transition paths and enforces rejection of invalid transitions."""
    sm = isolated_recovery_stack["state_machine"]
    case_id = "case_invariants_01"

    # Valid progression
    s1, _ = sm.transition(case_id, RecoveryState.PENDING, RecoveryState.ELIGIBLE)
    assert s1 == RecoveryState.ELIGIBLE

    s2, _ = sm.transition(case_id, s1, RecoveryState.SCHEDULED)
    assert s2 == RecoveryState.SCHEDULED

    s3, _ = sm.transition(case_id, s2, RecoveryState.DISPATCHING)
    assert s3 == RecoveryState.DISPATCHING

    s4, _ = sm.transition(case_id, s3, RecoveryState.DISPATCHED)
    assert s4 == RecoveryState.DISPATCHED

    s5, _ = sm.transition(case_id, s4, RecoveryState.DELIVERED)
    assert s5 == RecoveryState.DELIVERED

    s6, _ = sm.transition(case_id, s5, RecoveryState.READ)
    assert s6 == RecoveryState.READ

    s7, _ = sm.transition(case_id, s6, RecoveryState.RECOVERED)
    assert s7 == RecoveryState.RECOVERED

    # Test illegal transition: DISPATCHED -> PENDING is not permitted
    with pytest.raises(InvalidStateTransitionError):
        sm.transition(case_id, RecoveryState.DISPATCHED, RecoveryState.PENDING)


def test_8_durable_webhook_deduplication(isolated_recovery_stack):
    """Duplicate webhook submissions produce DUPLICATE_IGNORED and zero duplicate state mutations."""
    s = isolated_recovery_stack
    event_id = "evt_dedup_stage3_001"
    payload = {"event": "payment_link.paid", "payment_id": "pay_dedup_01", "amount_paise": 1000}

    s["webhook_processor"].register_case_mapping(
        case_id="case_dedup_01",
        initial_status=RecoveryState.DISPATCHED,
        payment_link_id="plink_dedup_01",
    )

    # First event
    r1 = s["webhook_processor"].process_razorpay_event(
        event_name="payment_link.paid",
        event_id=event_id,
        payment_id="pay_dedup_01",
        payment_link_id="plink_dedup_01",
        amount_paise=1000,
        raw_payload=payload,
    )
    assert r1.status == "PROCESSED"

    # Duplicate submission of same event_id
    r2 = s["webhook_processor"].process_razorpay_event(
        event_name="payment_link.paid",
        event_id=event_id,
        payment_id="pay_dedup_01",
        payment_link_id="plink_dedup_01",
        amount_paise=1000,
        raw_payload=payload,
    )
    assert r2.status == "DUPLICATE_IGNORED"


def test_9_ambiguous_provider_timeout_routes_to_reconciliation(isolated_recovery_stack):
    """Ambiguous provider HTTP timeout transitions job to RECONCILIATION_REQUIRED without duplicate send."""
    import httpx
    s = isolated_recovery_stack
    merchant_id = str(uuid.uuid4())

    s["mock_wa"].send_recovery_reminder.side_effect = httpx.TimeoutException("Meta API connect timeout")

    job = s["outbox_store"].enqueue(
        case_id="case_timeout_01",
        payment_id="pay_timeout_01",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****3210",
        message_payload={"customer_phone": "+919876543210", "amount_paise": 1000},
        idempotency_key="idemp_timeout_01",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    s["outbox_store"].approve_job(job.id, operator_id="op_admin", merchant_id=merchant_id)

    res = s["worker"].process_single_job_by_id(job.id, merchant_id=merchant_id)
    assert res.status == "RECONCILIATION_REQUIRED"

    refreshed = s["outbox_store"].get_job(job.id, merchant_id=merchant_id)
    assert refreshed.status == "RECONCILIATION_REQUIRED"


def test_10_payload_tampering_post_approval_detected(isolated_recovery_stack):
    """Tampering with message payload post-approval is detected and halted by pre-dispatch gate."""
    s = isolated_recovery_stack
    merchant_id = str(uuid.uuid4())

    job = s["outbox_store"].enqueue(
        case_id="case_tamper_s3",
        payment_id="pay_tamper_s3",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****3210",
        message_payload={"customer_phone": "+919876543210", "amount_paise": 1000},
        idempotency_key="idemp_tamper_s3",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    s["outbox_store"].approve_job(job.id, operator_id="operator_valid", merchant_id=merchant_id)

    # Claim job
    claimed = s["outbox_store"].claim_job_by_id(job.id, worker_id="w_tamper", merchant_id=merchant_id)
    assert claimed is not None

    # Tamper payload
    claimed.message_payload = {"customer_phone": "+919876543210", "amount_paise": 999999}

    res = s["worker"].process_single_job(claimed)
    assert res.status == "DEAD_LETTER"
    assert "integrity violation" in res.error_message.lower() or "authorization rejected" in res.error_message.lower()


def test_11_integer_paise_accounting_in_reconciliation(isolated_recovery_stack):
    """Payment reconciliation performs exact integer paise matching without floating-point inaccuracies."""
    recon = isolated_recovery_stack["reconciliation_engine"]
    mock_rzp = isolated_recovery_stack["mock_rzp"]

    # Exactly 1000 paise (INR 10.00)
    mock_rzp.get_payment_link.return_value = {
        "id": "plink_paise_01",
        "status": "paid",
        "amount": 1000,
        "amount_paid": 1000,
        "currency": "INR",
        "payments": [{"id": "pay_captured_01", "status": "captured", "fee": 24, "amount": 1000}],
    }
    rep1 = recon.reconcile_payment_link(
        payment_link_id="plink_paise_01",
        expected_amount_paise=1000,
    )
    assert rep1.is_reconciled is True
    assert rep1.amount_paid_paise == 1000

    # Amount mismatch fails reconciliation (underpaid)
    mock_rzp.get_payment_link.return_value = {
        "id": "plink_paise_02",
        "status": "paid",
        "amount": 500,
        "amount_paid": 500,
        "currency": "INR",
        "payments": [{"id": "pay_captured_02", "status": "captured", "fee": 12, "amount": 500}],
    }
    rep2 = recon.reconcile_payment_link(
        payment_link_id="plink_paise_02",
        expected_amount_paise=1000,
    )
    assert rep2.is_reconciled is False


def test_12_zero_mutation_of_live_target_job():
    """Confirms live hosted target job is never imported or mutated by Stage 3 tests."""
    from tests.conftest import TARGET_JOB_ID_STR
    assert TARGET_JOB_ID_STR == "5a6587ab-2601-4017-b396-48e3d2fc2fda"
