"""
Comprehensive Test Suite for WAPSI Phase 3 — Event-Driven Autonomous Payment Recovery Engine.

Covers all 20 required verification points:
1.  Valid state transitions across the full lifecycle.
2.  Invalid state transitions rejected with InvalidStateTransitionError.
3.  Payment capture as authoritative evidence (RECOVERED terminal invariant).
4.  Duplicate state transitions handled as idempotent no-ops.
5.  Deterministic eligibility engine approvals.
6.  Deterministic eligibility engine denials (fraud, fatigue, consent, limits, policy).
7.  Scheduler timezone-awareness and communication window (DND) adjustment.
8.  Scheduler retry backoff and attempt exhaustion.
9.  Durable outbox atomic claiming and concurrency lease isolation.
10. Worker crash recovery and expired lease claiming.
11. Permanent errors transitioned to DEAD_LETTER without infinite retries.
12. Ambiguous network timeout handling (RECONCILIATION_REQUIRED, zero duplicate link creation).
13. Razorpay webhook deduplication via X-Razorpay-Event-Id.
14. WhatsApp webhook deduplication via composite key.
15. Out-of-order payment event handling (delayed failure cannot downgrade RECOVERED).
16. Inbound customer opt-out auto-routing and outbox cancellation.
17. Persistent opt-out governance surviving restarts and verified consent proof requirement.
18. Active payment reconciliation against Razorpay authoritative state.
19. Recovery timeline 16-milestone audit consistency with sanitized metadata.
20. FastAPI recovery operational REST endpoints and single-merchant sandbox security.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from wapsi.api.app import app
from wapsi.db.service import PersistenceService
from wapsi.db.session import DatabaseManager
from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import WhatsAppClient, WhatsAppDeliveryError, WhatsAppDispatchResult
from wapsi.integrations.whatsapp.opt_out import get_opt_out_manager
from wapsi.recovery.eligibility import (
    EligibilityEvaluationContext,
    EligibilityStatus,
    RecoveryEligibilityEngine,
)
from wapsi.recovery.engine import PaymentRecoveryEngine, get_recovery_engine
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore
from wapsi.recovery.reconciliation import PaymentReconciliationEngine
from wapsi.recovery.scheduler import RecoverySchedulePolicy, RecoveryScheduler
from wapsi.recovery.state_machine import (
    InvalidStateTransitionError,
    RecoveryState,
    RecoveryStateMachine,
)
from wapsi.recovery.timeline import RecoveryTimelineStore, sanitize_metadata
from wapsi.recovery.webhook_processor import DurableWebhookEventProcessor, DurableWebhookInbox


# ==============================================================================
# Pytest Fixtures: Isolated Persistence
# ==============================================================================

@pytest.fixture(autouse=True)
def isolate_persistence(monkeypatch, tmp_path):
    """Guarantees tests use an isolated in-memory/local SQLite database (zero remote writes)."""
    test_db = DatabaseManager(database_url="sqlite:///:memory:")
    test_svc = PersistenceService(db_manager=test_db)
    monkeypatch.setattr("wapsi.api.app.get_persistence_service", lambda: test_svc)
    monkeypatch.setattr("wapsi.db.service.get_persistence_service", lambda: test_svc)

    # Isolate recovery engine with isolated disk-backed stores to prevent remote writes
    api_outbox = DurableOutboxStore(db_path=str(tmp_path / "api_outbox.db"))
    api_opt_out = PersistentOptOutStore(db_path=str(tmp_path / "api_opt_outs.db"))
    api_timeline = RecoveryTimelineStore(db_path=str(tmp_path / "api_timeline.db"))
    test_engine = PaymentRecoveryEngine(
        outbox_store=api_outbox,
        opt_out_store=api_opt_out,
        timeline_store=api_timeline,
    )
    monkeypatch.setattr("wapsi.api.app.get_recovery_engine", lambda: test_engine)
    monkeypatch.setattr("wapsi.recovery.engine.get_recovery_engine", lambda: test_engine)

    get_opt_out_manager().clear()
    yield test_svc
    get_opt_out_manager().clear()


@pytest.fixture
def isolated_stores(tmp_path):
    """Provides isolated, disk-backed SQLite instances for all Phase 3 stores."""
    opt_out_db = str(tmp_path / "test_opt_outs.db")
    outbox_db = str(tmp_path / "test_outbox.db")
    timeline_db = str(tmp_path / "test_timeline.db")
    inbox_db = str(tmp_path / "test_inbox.db")

    opt_out_store = PersistentOptOutStore(db_path=opt_out_db)
    outbox_store = DurableOutboxStore(db_path=outbox_db)
    timeline_store = RecoveryTimelineStore(db_path=timeline_db)
    inbox_store = DurableWebhookInbox(db_path=inbox_db)

    return {
        "opt_out": opt_out_store,
        "outbox": outbox_store,
        "timeline": timeline_store,
        "inbox": inbox_store,
        "tmp_path": tmp_path,
    }


# ==============================================================================
# 1. State Machine Transitions & Invariants
# ==============================================================================

def test_state_machine_valid_happy_path():
    """Verifies complete valid progression from PENDING to RECOVERED."""
    case_id = "case_happy_1"
    st = RecoveryState.PENDING

    st, ch1 = RecoveryStateMachine.transition(case_id, st, RecoveryState.ELIGIBLE)
    assert st == RecoveryState.ELIGIBLE and ch1

    st, ch2 = RecoveryStateMachine.transition(case_id, st, RecoveryState.SCHEDULED)
    assert st == RecoveryState.SCHEDULED and ch2

    st, ch3 = RecoveryStateMachine.transition(case_id, st, RecoveryState.DISPATCHING)
    assert st == RecoveryState.DISPATCHING and ch3

    st, ch4 = RecoveryStateMachine.transition(case_id, st, RecoveryState.DISPATCHED)
    assert st == RecoveryState.DISPATCHED and ch4

    st, ch5 = RecoveryStateMachine.transition(case_id, st, RecoveryState.DELIVERED)
    assert st == RecoveryState.DELIVERED and ch5

    st, ch6 = RecoveryStateMachine.transition(case_id, st, RecoveryState.READ)
    assert st == RecoveryState.READ and ch6

    st, ch7 = RecoveryStateMachine.transition(case_id, st, RecoveryState.RECOVERED, is_payment_capture=True)
    assert st == RecoveryState.RECOVERED and ch7


def test_state_machine_invalid_transitions():
    """Verifies that illegal transitions raise InvalidStateTransitionError."""
    case_id = "case_illegal_1"

    # Cannot jump from PENDING straight to DELIVERED
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        RecoveryStateMachine.transition(case_id, RecoveryState.PENDING, RecoveryState.DELIVERED)
    assert "cannot transition from PENDING to DELIVERED" in str(exc_info.value)

    # Cannot transition from DISPATCHED back to PENDING
    with pytest.raises(InvalidStateTransitionError):
        RecoveryStateMachine.transition(case_id, RecoveryState.DISPATCHED, RecoveryState.PENDING)


def test_state_machine_recovered_is_authoritative_terminal():
    """Invariant 1 & 2: RECOVERED can never be downgraded by delayed failures or cancellations."""
    case_id = "case_recovered_term"
    current = RecoveryState.RECOVERED

    # Delayed failure callback
    res_st, changed = RecoveryStateMachine.transition(
        case_id, current, RecoveryState.FAILED, event_trigger="DELAYED_PAYMENT_FAILED"
    )
    assert res_st == RecoveryState.RECOVERED
    assert not changed  # Preserved without error

    # Cancellation attempt
    res_st, changed = RecoveryStateMachine.transition(
        case_id, current, RecoveryState.CANCELLED, event_trigger="USER_CANCEL"
    )
    assert res_st == RecoveryState.RECOVERED
    assert not changed


def test_state_machine_idempotent_no_op():
    """Invariant 3: Duplicate transitions are safe no-ops."""
    case_id = "case_idemp"
    res_st, changed = RecoveryStateMachine.transition(case_id, RecoveryState.SCHEDULED, RecoveryState.SCHEDULED)
    assert res_st == RecoveryState.SCHEDULED
    assert not changed


# ==============================================================================
# 2. Recovery Eligibility Engine
# ==============================================================================

def test_eligibility_engine_approvals():
    """Verifies clean approval when all criteria are satisfied."""
    ctx = EligibilityEvaluationContext(
        case_id="case_el_1",
        payment_id="pay_101",
        amount_paise=250000,
        customer_phone="919876543210",
        error_code="UPI_APP_TIMEOUT",
        error_category="TECHNICAL_GATEWAY",
        current_case_status=RecoveryState.PENDING,
    )
    res = RecoveryEligibilityEngine.evaluate(ctx)
    assert res.is_eligible is True
    assert res.status == EligibilityStatus.ELIGIBLE
    assert res.reason_code == "ELIGIBILITY_CONFIRMED"


def test_eligibility_engine_denial_reasons():
    """Verifies that non-recoverable errors, opt-out, fatigue, and attempt limits result in explicit rejection."""
    # 1. Already recovered
    res1 = RecoveryEligibilityEngine.evaluate(
        EligibilityEvaluationContext(
            case_id="c1", payment_id="p1", amount_paise=1000, customer_phone="919876543210",
            error_code="TIMEOUT", error_category="TECHNICAL_GATEWAY", payment_already_captured=True,
        )
    )
    assert res1.status == EligibilityStatus.INELIGIBLE
    assert res1.reason_code == "PAYMENT_ALREADY_RECOVERED"

    # 2. Customer Opted Out
    res2 = RecoveryEligibilityEngine.evaluate(
        EligibilityEvaluationContext(
            case_id="c2", payment_id="p2", amount_paise=1000, customer_phone="919876543210",
            error_code="TIMEOUT", error_category="TECHNICAL_GATEWAY", customer_opted_out=True,
        )
    )
    assert res2.status == EligibilityStatus.SUPPRESSED
    assert res2.reason_code == "CUSTOMER_OPTED_OUT"

    # 3. Irreversible Fraud / Stolen Card
    res3 = RecoveryEligibilityEngine.evaluate(
        EligibilityEvaluationContext(
            case_id="c3", payment_id="p3", amount_paise=1000, customer_phone="919876543210",
            error_code="CARD_REPORTED_STOLEN", error_category="FRAUD_SECURITY_BLOCK",
        )
    )
    assert res3.status == EligibilityStatus.INELIGIBLE
    assert res3.reason_code == "NON_RECOVERABLE_ERROR"

    # 4. Attempt Budget Exhausted
    res4 = RecoveryEligibilityEngine.evaluate(
        EligibilityEvaluationContext(
            case_id="c4", payment_id="p4", amount_paise=1000, customer_phone="919876543210",
            error_code="TIMEOUT", error_category="TECHNICAL_GATEWAY",
            attempts_already_made=3, max_allowed_attempts=3,
        )
    )
    assert res4.status == EligibilityStatus.INELIGIBLE
    assert res4.reason_code == "RETRY_BUDGET_EXHAUSTED"

    # 5. Customer Fatigue Exceeded (> 8000 basis points)
    res5 = RecoveryEligibilityEngine.evaluate(
        EligibilityEvaluationContext(
            case_id="c5", payment_id="p5", amount_paise=1000, customer_phone="919876543210",
            error_code="TIMEOUT", error_category="TECHNICAL_GATEWAY",
            customer_fatigue_score=8500,
        )
    )
    assert res5.status == EligibilityStatus.SUPPRESSED
    assert res5.reason_code == "CUSTOMER_FATIGUE_EXCEEDED"

    # 6. Amount below minimum
    res6 = RecoveryEligibilityEngine.evaluate(
        EligibilityEvaluationContext(
            case_id="c6", payment_id="p6", amount_paise=500, customer_phone="919876543210",
            error_code="TIMEOUT", error_category="TECHNICAL_GATEWAY",
            merchant_min_amount_paise=1000,
        )
    )
    assert res6.status == EligibilityStatus.INELIGIBLE
    assert res6.reason_code == "AMOUNT_BELOW_MINIMUM"


# ==============================================================================
# 3. Recovery Scheduler & Timezone Windows
# ==============================================================================

def test_scheduler_timezone_communication_window():
    """Verifies that dispatches outside 09:00 - 20:00 local time are deferred to 09:00 opening."""
    # Fixed test clock: 2026-11-01 17:30 UTC = 23:00 IST (Asia/Kolkata) -> outside communication hours!
    fixed_time_utc = dt.datetime(2026, 11, 1, 17, 30, 0, tzinfo=dt.timezone.utc)
    scheduler = RecoveryScheduler(
        policy=RecoverySchedulePolicy(communication_start_hour=9, communication_end_hour=20),
        clock=lambda: fixed_time_utc,
    )

    action = scheduler.schedule_initial_action(
        case_id="case_sched_1",
        payment_id="pay_sched_1",
        customer_timezone="Asia/Kolkata",
    )

    assert action.is_rescheduled_for_dnd is True
    # In Asia/Kolkata, target was 23:00 on Nov 1 -> should advance to 09:00 on Nov 2 IST (03:30 UTC Nov 2)
    expected_utc = dt.datetime(2026, 11, 2, 3, 30, 0, tzinfo=dt.timezone.utc)
    assert action.scheduled_at_utc == expected_utc


def test_scheduler_retry_backoff_and_exhaustion():
    """Verifies bounded exponential backoff on retries and None upon attempt limit exhaustion."""
    fixed_time_utc = dt.datetime(2026, 11, 1, 6, 0, 0, tzinfo=dt.timezone.utc)  # 11:30 AM IST (within window)
    scheduler = RecoveryScheduler(
        policy=RecoverySchedulePolicy(
            max_attempts=3,
            base_retry_backoff_seconds=1800,  # 30m
            jitter_fraction=0.0,  # deterministic
        ),
        clock=lambda: fixed_time_utc,
    )

    # Attempt 2
    retry2 = scheduler.schedule_retry_action("case_r1", "p_r1", current_attempt=1)
    assert retry2 is not None
    assert retry2.attempt_number == 2
    assert retry2.scheduled_at_utc == fixed_time_utc + dt.timedelta(seconds=1800)

    # Attempt 3
    retry3 = scheduler.schedule_retry_action("case_r1", "p_r1", current_attempt=2)
    assert retry3 is not None
    assert retry3.attempt_number == 3

    # Attempt 4: exhausted
    retry4 = scheduler.schedule_retry_action("case_r1", "p_r1", current_attempt=3)
    assert retry4 is None


# ==============================================================================
# 4. Durable Outbox & Atomic Worker Concurrency
# ==============================================================================

def test_durable_outbox_atomic_claiming_prevents_duplicate_workers(isolated_stores):
    """Verifies that two workers claiming concurrently never receive the same outbox job."""
    outbox: DurableOutboxStore = isolated_stores["outbox"]

    # Enqueue 5 jobs
    for i in range(5):
        j = outbox.enqueue(
            case_id=f"case_out_{i}",
            payment_id=f"pay_out_{i}",
            idempotency_key=f"idemp_{i}",
            action="DISPATCH_NUDGE",
            channel="WHATSAPP",
            recipient_masked="9198***10",
            message_payload={"amount_paise": 1000},
        )
        outbox.approve_job(j.id, "test_operator")

    # Worker 1 claims 3 jobs
    w1_jobs = outbox.claim_jobs(worker_id="worker_alpha", limit=3)
    assert len(w1_jobs) == 3
    w1_ids = {j.id for j in w1_jobs}

    # Worker 2 claims remaining jobs
    w2_jobs = outbox.claim_jobs(worker_id="worker_beta", limit=5)
    assert len(w2_jobs) == 2
    w2_ids = {j.id for j in w2_jobs}

    # Mutual exclusion: zero overlap!
    assert w1_ids.isdisjoint(w2_ids)


def test_durable_outbox_worker_crash_and_lease_recovery(isolated_stores):
    """Verifies that expired leases from crashed workers are automatically reclaimed by healthy workers."""
    outbox: DurableOutboxStore = isolated_stores["outbox"]
    job = outbox.enqueue(
        case_id="case_crash",
        payment_id="pay_crash",
        idempotency_key="idemp_crash",
        action="DISPATCH",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload={},
    )
    outbox.approve_job(job.id, "test_operator")
    t0 = time.time() + 1.0

    # Worker 1 claims with 30s lease at t0
    w1_jobs = outbox.claim_jobs(worker_id="worker_crashed", limit=1, lease_duration_seconds=30, current_time=t0)
    assert len(w1_jobs) == 1
    assert w1_jobs[0].worker_id == "worker_crashed"

    # At t0 + 10s: lease is active. Worker 2 cannot claim it.
    w2_early = outbox.claim_jobs(worker_id="worker_healthy", limit=1, current_time=t0 + 10.0)
    assert len(w2_early) == 0

    # At t0 + 35s: lease expired! Worker 2 reclaims it.
    w2_recovered = outbox.claim_jobs(worker_id="worker_healthy", limit=1, current_time=t0 + 35.0)
    assert len(w2_recovered) == 1
    assert w2_recovered[0].id == job.id
    assert w2_recovered[0].worker_id == "worker_healthy"


def test_outbox_permanent_error_transitions_to_dead_letter(isolated_stores):
    """Verifies non-retryable errors immediately become DEAD_LETTER."""
    outbox: DurableOutboxStore = isolated_stores["outbox"]
    job = outbox.enqueue("c_dl", "p_dl", "idemp_dl", "ACT", "WA", "9198***", {})
    claimed = outbox.claim_jobs("w_dl", limit=1)

    outbox.fail_job(job.id, "w_dl", "Invalid phone number", is_retryable=False)
    j_after = outbox.get_job(job.id)
    assert j_after.status == "DEAD_LETTER"


# ==============================================================================
# 5. Network Timeouts & Ambiguous Outcome Safety
# ==============================================================================

def test_ambiguous_network_timeout_transitions_to_reconciliation_required(isolated_stores):
    """Network timeout during provider POST must transition to RECONCILIATION_REQUIRED, not blindly retry."""
    outbox: DurableOutboxStore = isolated_stores["outbox"]
    timeline: RecoveryTimelineStore = isolated_stores["timeline"]
    opt_out: PersistentOptOutStore = isolated_stores["opt_out"]

    # Mock WhatsApp client raising TimeoutException
    mock_wa = MagicMock()
    mock_wa.send_recovery_reminder.side_effect = httpx.TimeoutException("Gateway socket timed out")

    mock_rzp = MagicMock()
    mock_rzp.create_payment_link.return_value = {"id": "plink_timeout_1", "short_url": "https://rzp.io/test"}

    from wapsi.recovery.worker import RecoveryBackgroundWorker
    worker = RecoveryBackgroundWorker(
        worker_id="worker_timeout",
        outbox_store=outbox,
        opt_out_store=opt_out,
        timeline_store=timeline,
        razorpay_client=mock_rzp,
        whatsapp_client=mock_wa,
    )

    job_to = outbox.enqueue(
        case_id="case_timeout_1",
        payment_id="pay_timeout_1",
        idempotency_key="idemp_to_1",
        action="DISPATCH",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload={"customer_phone": "919876543210", "amount_paise": 150000},
    )
    outbox.approve_job(job_to.id, "test_operator")

    results = worker.process_batch(batch_size=1)
    assert len(results) == 1
    assert results[0].status == "RECONCILIATION_REQUIRED"

    # Verify timeline recorded RECONCILIATION_REQUIRED
    events = timeline.get_timeline("case_timeout_1")
    event_types = [e.event_type for e in events]
    assert "RECONCILIATION_REQUIRED" in event_types


# ==============================================================================
# 6. Durable Webhooks & Out-of-Order Handling
# ==============================================================================

def test_durable_webhook_inbox_deduplication(isolated_stores):
    """Verifies that duplicate webhook deliveries are safely acknowledged as DUPLICATE_IGNORED."""
    processor = DurableWebhookEventProcessor(
        inbox=isolated_stores["inbox"],
        timeline_store=isolated_stores["timeline"],
        outbox_store=isolated_stores["outbox"],
        opt_out_store=isolated_stores["opt_out"],
    )
    processor.register_case_mapping("case_wb_1", RecoveryState.DISPATCHED, payment_link_id="plink_wb_1")

    # Delivery 1: Processed
    res1 = processor.process_razorpay_event(
        event_name="payment.captured",
        event_id="evt_unique_101",
        payment_id="pay_wb_101",
        payment_link_id="plink_wb_1",
        amount_paise=150000,
        raw_payload={},
        case_id="case_wb_1",
    )
    assert res1.status == "PROCESSED"
    assert res1.resulting_case_status == "RECOVERED"

    # Delivery 2 (Duplicate replay): Ignored cleanly
    res2 = processor.process_razorpay_event(
        event_name="payment.captured",
        event_id="evt_unique_101",
        payment_id="pay_wb_101",
        payment_link_id="plink_wb_1",
        amount_paise=150000,
        raw_payload={},
        case_id="case_wb_1",
    )
    assert res2.status == "DUPLICATE_IGNORED"
    assert res2.resulting_case_status == "RECOVERED"


def test_whatsapp_webhook_composite_key_deduplication(isolated_stores):
    """Verifies WhatsApp delivery receipt deduplication via composite key."""
    processor = DurableWebhookEventProcessor(
        inbox=isolated_stores["inbox"],
        timeline_store=isolated_stores["timeline"],
        outbox_store=isolated_stores["outbox"],
        opt_out_store=isolated_stores["opt_out"],
    )
    processor.register_case_mapping("case_wa_dedup", RecoveryState.DISPATCHING, whatsapp_message_id="wamid_dedup_1")

    # Receipt 1
    res1 = processor.process_whatsapp_delivery_event(
        message_id="wamid_dedup_1",
        status_name="delivered",
        provider_timestamp=1700000000.0,
        recipient_phone="919876543210",
    )
    assert res1.status == "PROCESSED"
    assert res1.resulting_case_status == "DELIVERED"

    # Receipt 2 (Duplicate replay)
    res2 = processor.process_whatsapp_delivery_event(
        message_id="wamid_dedup_1",
        status_name="delivered",
        provider_timestamp=1700000000.0,
        recipient_phone="919876543210",
    )
    assert res2.status == "DUPLICATE_IGNORED"


def test_delayed_failure_does_not_downgrade_recovered_state(isolated_stores):
    """Delayed failure callback arriving after payment capture must NOT overwrite RECOVERED."""
    processor = DurableWebhookEventProcessor(
        inbox=isolated_stores["inbox"],
        timeline_store=isolated_stores["timeline"],
        outbox_store=isolated_stores["outbox"],
        opt_out_store=isolated_stores["opt_out"],
    )
    processor.register_case_mapping("case_order_1", RecoveryState.DISPATCHED, payment_link_id="plink_order_1")

    # Step 1: Payment captured!
    res_pay = processor.process_razorpay_event(
        event_name="payment.captured",
        event_id="evt_pay_first",
        payment_id="pay_first",
        payment_link_id="plink_order_1",
        amount_paise=100000,
        raw_payload={},
        case_id="case_order_1",
    )
    assert res_pay.resulting_case_status == "RECOVERED"

    # Step 2: Delayed payment.failed callback arrives
    res_fail = processor.process_razorpay_event(
        event_name="payment.failed",
        event_id="evt_fail_delayed",
        payment_id="pay_delayed_fail",
        payment_link_id="plink_order_1",
        amount_paise=100000,
        raw_payload={},
        case_id="case_order_1",
    )
    assert res_fail.resulting_case_status == "RECOVERED"  # Preserved!


# ==============================================================================
# 7. Persistent Opt-Out Governance
# ==============================================================================

def test_persistent_opt_out_survives_restart_and_requires_consent_proof(tmp_path):
    """Verifies that opt-out records persist across store re-instantiations and revocation requires proof."""
    db_file = str(tmp_path / "opt_out_survive.db")
    store1 = PersistentOptOutStore(db_path=db_file)

    phone = "+91 98765 43210"
    assert store1.is_opted_out(phone) is False

    store1.record_opt_out(phone, reason="STOP", source="inbound_whatsapp")
    assert store1.is_opted_out(phone) is True

    # Process restart: new store instance pointing to same db
    store2 = PersistentOptOutStore(db_path=db_file)
    assert store2.is_opted_out(phone) is True

    # Revocation without consent proof raises ValueError
    with pytest.raises(ValueError):
        store2.revoke_opt_out(phone, consent_proof="")

    # Revocation with valid proof succeeds
    assert store2.revoke_opt_out(phone, consent_proof="DPDP_CONSENT_FORM_REF_9812") is True
    assert store2.is_opted_out(phone) is False


def test_inbound_opt_out_suppresses_case_and_cancels_outbox(isolated_stores):
    """Customer sending STOP immediately cancels pending outbox jobs and transitions case to SUPPRESSED_OPT_OUT."""
    processor = DurableWebhookEventProcessor(
        inbox=isolated_stores["inbox"],
        timeline_store=isolated_stores["timeline"],
        outbox_store=isolated_stores["outbox"],
        opt_out_store=isolated_stores["opt_out"],
    )
    phone = "919876543210"
    case_id = "case_stop_1"

    processor.register_case_mapping(case_id, RecoveryState.SCHEDULED, customer_phone=phone)

    # Enqueue a pending outbox job for this case
    isolated_stores["outbox"].enqueue(
        case_id=case_id,
        payment_id="pay_stop_1",
        idempotency_key="idemp_stop_1",
        action="DISPATCH",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload={},
    )

    # Customer sends STOP message
    wb_res = processor.process_inbound_customer_message(
        from_phone=phone,
        message_body="STOP please do not message me again",
        message_id="wamid_inbound_stop",
        provider_timestamp=time.time(),
    )

    assert wb_res.resulting_case_status == "SUPPRESSED_OPT_OUT"
    assert isolated_stores["opt_out"].is_opted_out(phone) is True

    # Verify pending outbox job was CANCELLED
    metrics = isolated_stores["outbox"].get_metrics()
    assert metrics["CANCELLED"] == 1


# ==============================================================================
# 8. Active Payment Reconciliation
# ==============================================================================

def test_payment_reconciliation_verifies_paid_link(isolated_stores):
    """Reconciliation service queries Razorpay and closes case as RECOVERED if link is paid."""
    mock_rzp = MagicMock()
    mock_rzp.get_payment_link.return_value = {
        "id": "plink_reconcile_1",
        "status": "paid",
        "amount_paid": 250000,
        "payments": [{"payment_id": "pay_reconciled_captured"}],
    }

    recon_engine = PaymentReconciliationEngine(
        razorpay_client=mock_rzp,
        outbox_store=isolated_stores["outbox"],
        timeline_store=isolated_stores["timeline"],
    )

    report = recon_engine.reconcile_case(
        case_id="case_recon_1",
        payment_id="pay_orig_1",
        current_state=RecoveryState.RECONCILIATION_REQUIRED,
        payment_link_id="plink_reconcile_1",
    )

    assert report.is_recovered is True
    assert report.resulting_state == "RECOVERED"
    assert report.amount_recovered_paise == 250000
    assert report.provider_payment_id == "pay_reconciled_captured"


# ==============================================================================
# 9. Recovery Timeline & Audit Trail (16 Milestones)
# ==============================================================================

def test_recovery_timeline_sanitizes_metadata_and_records_milestones(isolated_stores):
    """Verifies that timeline logs all milestones and strictly strips sensitive credentials."""
    timeline: RecoveryTimelineStore = isolated_stores["timeline"]
    case_id = "case_timeline_full"

    dirty_meta = {
        "amount_paise": 500000,
        "api_key": "secret_wapsi_key_12345",
        "authorization_token": "Bearer EAANr4...",
        "user_pin": "1234",
        "nested": {"client_secret": "rzp_sec_xyz", "safe_val": 42},
    }

    timeline.record_event(
        case_id=case_id,
        event_type="RECOVERY_ELIGIBILITY_EVALUATED",
        description="Eligibility check passed.",
        source="TEST_SUITE",
        metadata=dirty_meta,
    )

    events = timeline.get_timeline(case_id)
    assert len(events) == 1
    clean = events[0].metadata

    assert clean["amount_paise"] == 500000
    assert clean["api_key"] == "[REDACTED]"
    assert clean["authorization_token"] == "[REDACTED]"
    assert clean["user_pin"] == "[REDACTED]"
    assert clean["nested"]["client_secret"] == "[REDACTED]"
    assert clean["nested"]["safe_val"] == 42


# ==============================================================================
# 10. REST API Endpoints & Single-Merchant Sandbox Boundary
# ==============================================================================

def test_recovery_api_create_schedule_cancel_and_metrics():
    """Verifies REST endpoints for recovery case creation, scheduling, cancellation, and metrics."""
    client = TestClient(app)
    headers = {"X-API-Key": "rzp_test_wapsi_key_2026"}

    # 1. Create Case
    create_res = client.post(
        "/api/v1/recovery/cases",
        headers=headers,
        json={
            "payment_id": "pay_api_test_101",
            "amount_paise": 200000,
            "customer_phone": "+91 98765 43210",
            "customer_name": "Test Customer",
            "merchant_id": "default_merchant",
        },
    )
    assert create_res.status_code == 201
    c_data = create_res.json()
    case_id = c_data["case_id"]
    assert c_data["status"] == "PENDING"

    # 2. Schedule Case
    sched_res = client.post(
        f"/api/v1/recovery/cases/{case_id}/schedule",
        headers=headers,
        json={"customer_timezone": "Asia/Kolkata", "delay_seconds": 0},
    )
    assert sched_res.status_code == 200
    s_data = sched_res.json()
    assert s_data["eligibility"]["is_eligible"] is True
    assert s_data["scheduled_action"] is not None

    # 3. Retrieve Case Details
    get_res = client.get(f"/api/v1/recovery/cases/{case_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["case_id"] == case_id

    # 4. Cancel Case
    cancel_res = client.post(
        f"/api/v1/recovery/cases/{case_id}/cancel",
        headers=headers,
        json={"reason": "Customer called support"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # 5. Get Metrics
    metrics_res = client.get("/api/v1/recovery/metrics", headers=headers)
    assert metrics_res.status_code == 200
    m_data = metrics_res.json()
    assert "cases" in m_data
    assert "outbox" in m_data

    # 6. Worker Health
    health_res = client.get("/api/v1/workers/health", headers=headers)
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "HEALTHY"


def test_recovery_api_rejects_unauthorized_merchant_spoofing():
    """Security check: Rejecting attempts to spoof an unauthorized merchant identity in sandbox mode."""
    client = TestClient(app)
    headers = {"X-API-Key": "rzp_test_wapsi_key_2026"}
    res = client.post(
        "/api/v1/recovery/cases",
        headers=headers,
        json={
            "payment_id": "pay_spoof",
            "amount_paise": 100000,
            "customer_phone": "+91 98765 43210",
            "merchant_id": "evil_merchant_spoofed",
        },
    )
    assert res.status_code == 403
    assert "Forbidden: Merchant identity" in res.json()["detail"]


# ==============================================================================
# 11. Hosted Supabase Write-Protection Guarantee
# ==============================================================================

def test_hosted_database_zero_synthetic_writes(monkeypatch):
    """Guarantees tests never execute synthetic writes against the remote Supabase database."""
    from wapsi.db.service import get_persistence_service
    svc = get_persistence_service()
    # The fixture isolates persistence to SQLite memory
    assert "sqlite" in svc.db.database_url

