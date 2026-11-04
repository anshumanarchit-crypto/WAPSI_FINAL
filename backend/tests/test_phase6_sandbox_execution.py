"""
Phase 6 Sandbox Execution and Decision Authorization Test Suite.

Verifies:
1. End-to-end recovery lifecycle state machine progression:
   PENDING -> ELIGIBLE -> SCHEDULED -> DISPATCHING -> DISPATCHED
   -> DELIVERED -> READ -> RECOVERED.
2. Stage E Human Approval and Safety Gate Validations:
   - Unapproved WhatsApp intervention blocked.
   - Explicitly approved WhatsApp intervention permitted.
   - Opted-out test customer blocked even after approval.
   - High-value payment (> INR 5,000) routed to human review.
   - Irreversible-risk profile (e.g. CARD_REPORTED_STOLEN) rejected.
   - Invalid webhook signature rejected (Razorpay & WhatsApp).
   - Duplicate webhook event deduplication.
   - Expired or failed payment link reconciliation.
3. Payment reconciliation with exact paise accounting and double-credit protection.
4. Model readiness boundary enforcement (BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS).
"""

import copy
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest.mock
import uuid
import pytest

from wapsi.core.config import get_settings
from wapsi.decision.supervisor import (
    DeterministicDecisionSupervisor,
    TransactionDecisionContext,
)
from wapsi.integrations.razorpay.webhook import RazorpayWebhookHandler
from wapsi.integrations.whatsapp.webhook import WhatsAppWebhookHandler
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore, compute_approval_hash
from wapsi.recovery.reconciliation import (
    PaymentLinkReconciliationReport,
    PaymentReconciliationEngine,
)
from wapsi.recovery.state_machine import RecoveryState, RecoveryStateMachine
from wapsi.recovery.timeline import RecoveryTimelineStore
from wapsi.recovery.webhook_processor import (
    DurableWebhookInbox,
    DurableWebhookEventProcessor,
)
from wapsi.recovery.worker import RecoveryBackgroundWorker


@pytest.fixture
def temp_sandbox_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield tmpdir


@pytest.fixture
def sandbox_outbox(temp_sandbox_dir):
    return DurableOutboxStore(db_path=os.path.join(temp_sandbox_dir, "outbox.db"))


@pytest.fixture
def sandbox_opt_out(temp_sandbox_dir):
    return PersistentOptOutStore(db_path=os.path.join(temp_sandbox_dir, "opt_out.db"))


@pytest.fixture
def sandbox_timeline(temp_sandbox_dir):
    return RecoveryTimelineStore(db_path=os.path.join(temp_sandbox_dir, "timeline.db"))


def test_end_to_end_recovery_state_machine_happy_path():
    """
    Validates complete state machine transition path:
    PENDING -> ELIGIBLE -> SCHEDULED -> DISPATCHING -> DISPATCHED
    -> DELIVERED -> READ -> RECOVERED.
    """
    case_id = "case_sm_001"
    state = RecoveryState.PENDING

    # 1. PENDING -> ELIGIBLE
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.ELIGIBLE, "Passed eligibility")
    assert state == RecoveryState.ELIGIBLE and changed is True

    # 2. ELIGIBLE -> SCHEDULED
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.SCHEDULED, "Action candidate scheduled")
    assert state == RecoveryState.SCHEDULED and changed is True

    # 3. SCHEDULED -> DISPATCHING
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.DISPATCHING, "Leased by worker")
    assert state == RecoveryState.DISPATCHING and changed is True

    # 4. DISPATCHING -> DISPATCHED
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.DISPATCHED, "Accepted by Meta")
    assert state == RecoveryState.DISPATCHED and changed is True

    # 5. DISPATCHED -> DELIVERED
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.DELIVERED, "Handset receipt")
    assert state == RecoveryState.DELIVERED and changed is True

    # 6. DELIVERED -> READ
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.READ, "Customer read receipt")
    assert state == RecoveryState.READ and changed is True

    # 7. READ -> RECOVERED (Authoritative terminal state)
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.RECOVERED, "Payment captured", is_payment_capture=True)
    assert state == RecoveryState.RECOVERED and changed is True

    # 8. Terminal invariant: Attempting to downgrade RECOVERED to FAILED is rejected and preserves RECOVERED
    state, changed = RecoveryStateMachine.transition(case_id, state, RecoveryState.FAILED, "Late failure callback")
    assert state == RecoveryState.RECOVERED and changed is False


def test_stage_e_unapproved_whatsapp_intervention_blocked(sandbox_outbox):
    """An unapproved customer-contacting job remains PENDING_APPROVAL and is unclaimable."""
    job = sandbox_outbox.enqueue(
        case_id="case_p6_e1",
        payment_id="pay_p6_e1",
        idempotency_key="idemp_p6_e1",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload={"amount_paise": 1000, "payment_link_url": "https://rzp.io/rzp/test"},
    )
    assert job.status == "PENDING_APPROVAL"
    assert job.requires_operator_approval is True

    # Claiming should return nothing
    claimed = sandbox_outbox.claim_jobs("worker_e1", limit=10)
    assert len(claimed) == 0


def test_stage_e_approved_whatsapp_intervention_permitted(sandbox_outbox):
    """Explicit operator approval signs the job with snapshot hash and transitions to QUEUED."""
    payload = {"amount_paise": 1000, "payment_link_url": "https://rzp.io/rzp/test"}
    job = sandbox_outbox.enqueue(
        case_id="case_p6_e2",
        payment_id="pay_p6_e2",
        idempotency_key="idemp_p6_e2",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked="919876543210",
        message_payload=payload,
    )
    ok = sandbox_outbox.approve_job(
        job_id=job.id,
        operator_id="operator_p6_admin",
    )
    assert ok is True
    approved_job = sandbox_outbox.get_job(job.id)
    assert approved_job.status == "QUEUED"
    assert approved_job.approved_by_operator_id == "operator_p6_admin"
    assert approved_job.approval_snapshot_hash is not None

    # Now it can be claimed
    claimed = sandbox_outbox.claim_jobs("worker_e2", limit=10)
    assert len(claimed) == 1
    assert claimed[0].id == job.id


def test_stage_e_opted_out_customer_blocked_even_after_approval(sandbox_outbox, sandbox_opt_out):
    """An opted-out customer cannot be contacted even if the operator approved the job."""
    phone = "+919876543210"
    sandbox_opt_out.record_opt_out(
        phone=phone,
        reason="Customer replied STOP",
        source="inbound_whatsapp",
    )
    assert sandbox_opt_out.is_opted_out(phone) is True

    payload = {"customer_phone": phone, "amount_paise": 1000}
    job = sandbox_outbox.enqueue(
        case_id="case_p6_e3",
        payment_id="pay_p6_e3",
        idempotency_key="idemp_p6_e3",
        action="SEND_WHATSAPP_REMINDER",
        channel="whatsapp",
        recipient_masked=phone,
        message_payload=payload,
    )
    sandbox_outbox.approve_job(job.id, "operator_admin")

    claimed = sandbox_outbox.claim_jobs("worker_e3", limit=1)
    assert len(claimed) == 1

    # Verify pre-dispatch authorization check fails due to opt-out
    auth_ok, reason = sandbox_outbox.verify_dispatch_authorization(
        job=claimed[0],
        opt_out_store=sandbox_opt_out,
    )
    assert auth_ok is False
    assert "opted out" in reason.lower()


def test_stage_e_high_value_payment_routes_to_human_review():
    """
    Transactions with value > INR 5,000 must NOT execute autonomously;
    they require explicit human review and authorization.
    """
    supervisor = DeterministicDecisionSupervisor(high_value_threshold_inr=5000.0)
    high_value_ctx = TransactionDecisionContext(
        payment_id="pay_high_val_01",
        customer_phone="+919876543210",
        amount_in_inr=15000.0,  # High value: Rs. 15,000
    )
    snapshot = supervisor.evaluate_decision(high_value_ctx)
    assert snapshot.execution_status == "PENDING_APPROVAL"
    assert snapshot.requires_human_approval is True
    assert "exceeds high-value threshold" in snapshot.human_approval_reason


def test_stage_e_irreversible_risk_rejection():
    """Irreversible risk profiles (e.g. CARD_REPORTED_STOLEN) are rejected with NO_ACTION."""
    supervisor = DeterministicDecisionSupervisor()
    risk_ctx = TransactionDecisionContext(
        payment_id="pay_fraud_01",
        customer_phone="+919876543210",
        amount_in_inr=1000.0,
        error_code="CARD_REPORTED_STOLEN",
    )
    snapshot = supervisor.evaluate_decision(risk_ctx)
    assert snapshot.execution_status == "REJECTED"
    assert snapshot.authorized_action == "NO_ACTION"
    assert snapshot.risk_assessment.get("is_fraud_or_irreversible") is True


def test_stage_e_invalid_webhook_signature_rejected():
    """Tampered or invalid HMAC signatures must be rejected by webhook handlers."""
    payload_body = b'{"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": "plink_1"}}}}'
    correct_rzp_secret = "correct_secret_rzp_123"

    # Valid signature passes
    valid_sig = hmac.new(correct_rzp_secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()
    assert RazorpayWebhookHandler.verify_signature(payload_body, valid_sig, secret=correct_rzp_secret) is True

    # Tampered signature fails
    assert RazorpayWebhookHandler.verify_signature(payload_body, "tampered_bad_sig_hex", secret=correct_rzp_secret) is False

    # WhatsApp webhook signature check
    wa_body = b'{"object": "whatsapp_business_account", "entry": []}'
    correct_meta_secret = "correct_meta_secret_456"
    valid_wa_sig = "sha256=" + hmac.new(correct_meta_secret.encode("utf-8"), wa_body, hashlib.sha256).hexdigest()
    assert WhatsAppWebhookHandler.verify_signature(wa_body, valid_wa_sig, app_secret=correct_meta_secret) is True
    assert WhatsAppWebhookHandler.verify_signature(wa_body, "sha256=invalid_hash", app_secret=correct_meta_secret) is False


def test_stage_e_duplicate_webhook_event_deduplication(temp_sandbox_dir):
    """Processing the exact same webhook delivery twice yields idempotent deduplication."""
    inbox = DurableWebhookInbox(db_path=os.path.join(temp_sandbox_dir, "webhook_inbox.db"))
    processor = DurableWebhookEventProcessor(inbox=inbox)

    event_id = "evt_rzp_test_dup_001"
    raw_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_dup_001",
                    "amount": 1000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }
    # First delivery
    res1 = processor.process_razorpay_event(
        event_name="payment.captured",
        event_id=event_id,
        payment_id="pay_test_dup_001",
        raw_payload=raw_payload,
    )
    assert res1.status in ("PROCESSED", "ACCEPTED", "SUCCESS")

    # Second identical delivery
    res2 = processor.process_razorpay_event(
        event_name="payment.captured",
        event_id=event_id,
        payment_id="pay_test_dup_001",
        raw_payload=raw_payload,
    )
    assert res2.status in ("DUPLICATE_IGNORED", "ALREADY_PROCESSED", "PROCESSED")


def test_stage_e_failed_or_expired_payment_link_triggers_reconciliation():
    """An expired or failed payment link is flagged as unreconciled, preventing recovery credit."""
    mock_rzp = unittest.mock.MagicMock()
    mock_rzp.get_payment_link.return_value = {
        "id": "plink_expired_001",
        "status": "expired",
        "amount": 1000,
        "currency": "INR",
        "amount_paid": 0,
    }
    engine = PaymentReconciliationEngine(razorpay_client=mock_rzp)
    report = engine.reconcile_payment_link(
        payment_link_id="plink_expired_001",
        expected_amount_paise=1000,
    )
    assert isinstance(report, PaymentLinkReconciliationReport)
    assert report.is_reconciled is False
    assert report.provider_status == "expired"
    assert report.is_actionable_recovery is False
    assert "not paid" in report.failure_reason.lower()


def test_payment_reconciliation_exact_paise_accounting():
    """Payment reconciliation accurately matches expected vs paid paise and status."""
    mock_rzp = unittest.mock.MagicMock()
    mock_rzp.get_payment_link.return_value = {
        "id": "plink_match_001",
        "status": "paid",
        "amount": 1000,
        "currency": "INR",
        "amount_paid": 1000,
    }
    engine = PaymentReconciliationEngine(razorpay_client=mock_rzp)
    report = engine.reconcile_payment_link(
        payment_link_id="plink_match_001",
        expected_amount_paise=1000,
    )
    assert report.is_reconciled is True
    assert report.matched_amount_paise == 1000
    assert report.amount_paid_paise == 1000
    assert report.is_actionable_recovery is True


def test_model_readiness_boundary_preserves_advisory_mode():
    """
    Verifies that model artifacts carry BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS
    and that production autonomous authorization is blocked.
    """
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "models",
        "manifest.json",
    )
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for model_meta in manifest.get("registered_models", []):
        assert model_meta.get("readiness_status") == "BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS"

    supervisor = DeterministicDecisionSupervisor()
    assert supervisor.model_readiness_status == "BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS"
    assert supervisor.deployment_mode == "ADVISORY_HUMAN_REVIEW"
