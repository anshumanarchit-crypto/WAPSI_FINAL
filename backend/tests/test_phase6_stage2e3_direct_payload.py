"""
Phase 6 Stage 2E.3 — Regression Tests: Direct WhatsApp Payload Remediation

Tests the two-mode worker dispatch architecture introduced in Stage 2E.3:
  - Mode B: Pre-formed Meta WhatsApp Cloud API payload dispatched verbatim.
  - Mode A: Action Specification payload with JIT Razorpay link creation.

All 16 required regression test cases.

IMPORTANT CONSTRAINTS:
  - No real outbound calls to Meta, Razorpay, or PostgreSQL.
  - Target production job 5a6587ab-2601-4017-b396-48e3d2fc2fda is NOT touched.
  - All provider interactions are mocked.
  - In-memory / SQLite outbox used (not hosted PostgreSQL).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
import uuid
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch, call

import httpx
import pytest

from wapsi.integrations.whatsapp.client import (
    WhatsAppDeliveryError,
    WhatsAppDispatchResult,
    WhatsAppRateLimitError,
    WhatsAppValidationError,
    WhatsAppClient,
)
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker
from wapsi.recovery.outbox import OutboxJob


# =============================================================================
# Fixtures & Helpers
# =============================================================================

MERCHANT_ID = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
CASE_ID = "wapsi_case_phase6_stage2_001"
PAYMENT_ID = "pay_phase6_test_dummy_001"
IDEMPOTENCY_KEY = "idemp_p6_s2_plink_TvKucM1yXJQAZA"
RECIPIENT_E164 = "916260055671"
PAYMENT_LINK_ID = "plink_TvKucM1yXJQAZA"
PAYMENT_LINK_URL = "https://rzp.io/rzp/NCf137AL"
EXPECTED_WAMID = "wamid.HBgL916260055671VwIGERgSMzQ1NTY3ODkwMTIzNDU2Nzg5AA=="

APPROVED_TEXT_BODY = (
    f"WAPSI SANDBOX TEST: Your payment link for INR 10.00 is ready: {PAYMENT_LINK_URL}. "
    "Complete your payment now."
)

# --- Mode B payload (pre-formed Meta WhatsApp Cloud API object) ---
DIRECT_META_PAYLOAD: Dict[str, Any] = {
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": RECIPIENT_E164,
    "type": "text",
    "text": {"body": APPROVED_TEXT_BODY, "preview_url": True},
}

# --- Mode A payload (Action Specification) ---
ACTION_SPEC_PAYLOAD: Dict[str, Any] = {
    "customer_phone": RECIPIENT_E164,
    "amount_paise": 1000,
    "customer_name": "Test Customer",
    "merchant_name": "WAPSI Merchant",
    "merchant_id": MERCHANT_ID,
    "payment_link_id": PAYMENT_LINK_ID,
    "payment_link_url": PAYMENT_LINK_URL,
}

# Razorpay GET response for the existing payment link
RAZORPAY_LINK_DATA: Dict[str, Any] = {
    "id": PAYMENT_LINK_ID,
    "amount": 1000,
    "currency": "INR",
    "status": "created",
    "amount_paid": 0,
    "short_url": PAYMENT_LINK_URL,
    "expired": False,
}


def _make_approval_hash(payload: Dict[str, Any], job_id: str, merchant_id: str) -> str:
    """Mirrors compute_approval_hash() logic for test setup."""
    canonical = json.dumps(
        {"job_id": job_id, "merchant_id": merchant_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _make_job(
    payload: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    approved: bool = True,
    idempotency_key: Optional[str] = None,
    merchant_id: str = MERCHANT_ID,
) -> OutboxJob:
    """Creates a synthetic OutboxJob for testing. Does NOT touch PostgreSQL."""
    now_ts = time.time()
    jid = job_id or str(uuid.uuid4())
    p = payload if payload is not None else dict(DIRECT_META_PAYLOAD)
    snap_hash = _make_approval_hash(p, jid, merchant_id) if approved else None
    approved_ts = now_ts if approved else None
    return OutboxJob(
        id=jid,
        merchant_id=merchant_id,
        case_id=CASE_ID,
        payment_id=PAYMENT_ID,
        message_payload=p,
        idempotency_key=idempotency_key or IDEMPOTENCY_KEY,
        action="SEND_WHATSAPP_RECOVERY",
        channel="whatsapp",
        recipient_masked=RECIPIENT_E164[:4] + "****" + RECIPIENT_E164[-2:],
        status="RETRY" if approved else "PENDING_APPROVAL",
        retry_count=1,
        max_retries=3,
        next_attempt_at=now_ts,
        lease_expires_at=None,
        worker_id=None,
        last_error=None,
        created_at=now_ts,
        updated_at=now_ts,
        requires_operator_approval=True,
        approved_by_operator_id="operator_arpit" if approved else None,
        approved_at=approved_ts,
        approval_snapshot_hash=snap_hash,
    )


def _make_wa_result(wamid: str = EXPECTED_WAMID) -> WhatsAppDispatchResult:
    return WhatsAppDispatchResult(
        success=True,
        message_id=wamid,
        recipient_phone=RECIPIENT_E164,
        status="accepted",
        timestamp=time.time(),
        raw_response={"messages": [{"id": wamid}]},
    )


def _make_worker(
    wa_mock: Optional[Any] = None,
    rzp_mock: Optional[Any] = None,
    outbox_mock: Optional[Any] = None,
    opt_out_mock: Optional[Any] = None,
    timeline_mock: Optional[Any] = None,
) -> RecoveryBackgroundWorker:
    """Builds a worker with mocked collaborators. Skips all real I/O."""
    # Default outbox mock: auth always passes, no-op mutations
    if outbox_mock is None:
        outbox_mock = MagicMock()
        outbox_mock.verify_dispatch_authorization.return_value = (True, None)
        outbox_mock.complete_job.return_value = None
        outbox_mock.fail_job.return_value = None
        outbox_mock.mark_reconciliation_required.return_value = None
        outbox_mock.cancel_jobs_for_case.return_value = None
        outbox_mock.claim_job_by_id.return_value = None  # no real claim

    if opt_out_mock is None:
        opt_out_mock = MagicMock()
        opt_out_mock.is_opted_out.return_value = False

    if timeline_mock is None:
        timeline_mock = MagicMock()
        timeline_mock.record_event.return_value = None

    if wa_mock is None:
        wa_mock = MagicMock(spec=WhatsAppClient)
        wa_mock.send_prepared_payload.return_value = _make_wa_result()
        wa_mock.send_recovery_reminder.return_value = _make_wa_result()

    if rzp_mock is None:
        rzp_mock = MagicMock()
        rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)
        rzp_mock.create_payment_link.return_value = {
            "id": PAYMENT_LINK_ID,
            "short_url": PAYMENT_LINK_URL,
        }

    return RecoveryBackgroundWorker(
        worker_id="worker_test_2e3",
        outbox_store=outbox_mock,
        opt_out_store=opt_out_mock,
        timeline_store=timeline_mock,
        razorpay_client=rzp_mock,
        whatsapp_client=wa_mock,
    )


# =============================================================================
# TC-01: Mode Detection — Direct Meta Payload
# =============================================================================

def test_is_direct_payload_detected_correctly():
    """TC-01: Mode B is correctly detected for a well-formed direct Meta payload."""
    assert RecoveryBackgroundWorker._is_direct_meta_payload(DIRECT_META_PAYLOAD) is True


def test_is_direct_payload_not_detected_for_action_spec():
    """TC-01b: Mode A (action spec) is NOT incorrectly identified as Mode B."""
    assert RecoveryBackgroundWorker._is_direct_meta_payload(ACTION_SPEC_PAYLOAD) is False


def test_mode_detection_requires_text_or_template():
    """TC-01c: Payload without 'text' or 'template' is NOT detected as Mode B."""
    p = dict(DIRECT_META_PAYLOAD)
    del p["text"]
    assert RecoveryBackgroundWorker._is_direct_meta_payload(p) is False


def test_mode_detection_requires_individual_recipient():
    """TC-01d: 'recipient_type' != 'individual' prevents Mode B detection."""
    p = {**DIRECT_META_PAYLOAD, "recipient_type": "group"}
    assert RecoveryBackgroundWorker._is_direct_meta_payload(p) is False


# =============================================================================
# TC-02: Direct Payload NEVER calls create_payment_link
# =============================================================================

def test_direct_payload_never_calls_create_payment_link():
    """TC-02: Mode B dispatch must never invoke rzp.create_payment_link."""
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)
    worker = _make_worker(rzp_mock=rzp_mock)
    job = _make_job()
    worker.process_single_job(job)
    rzp_mock.create_payment_link.assert_not_called()


# =============================================================================
# TC-03: Existing payment link validated and reused
# =============================================================================

def test_existing_payment_link_validated_and_reused():
    """TC-03: Mode B resolves plink from idempotency key and validates it via GET."""
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)
    worker = _make_worker(rzp_mock=rzp_mock)
    job = _make_job(idempotency_key=IDEMPOTENCY_KEY)
    result = worker.process_single_job(job)
    rzp_mock.get_payment_link.assert_called_once_with(PAYMENT_LINK_ID)
    assert result.payment_link_id == PAYMENT_LINK_ID
    assert result.status == "COMPLETED"


# =============================================================================
# TC-04: Approved URL must match link short_url
# =============================================================================

def test_approved_url_must_match_link_short_url():
    """TC-04: Dispatch is blocked (DEAD_LETTER) if approved body doesn't contain link short_url."""
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = {
        **RAZORPAY_LINK_DATA,
        "short_url": "https://rzp.io/rzp/DIFFERENT_LINK",
    }
    payload = {
        **DIRECT_META_PAYLOAD,
        "text": {"body": "Your link is: https://rzp.io/rzp/NCf137AL", "preview_url": True},
    }
    # Build a fresh job with re-computed hash for the modified payload
    job = _make_job(payload=payload)
    worker = _make_worker(rzp_mock=rzp_mock)
    result = worker.process_single_job(job)
    assert result.status == "DEAD_LETTER"
    assert "validation failed" in (result.error_message or "").lower()


# =============================================================================
# TC-05: Exact payload transmitted verbatim
# =============================================================================

def test_exact_payload_transmitted_verbatim():
    """TC-05: send_prepared_payload is called with the approved payload (phone normalized)."""
    wa_mock = MagicMock(spec=WhatsAppClient)
    wa_mock.send_prepared_payload.return_value = _make_wa_result()
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)
    worker = _make_worker(wa_mock=wa_mock, rzp_mock=rzp_mock)
    job = _make_job()
    worker.process_single_job(job)
    wa_mock.send_prepared_payload.assert_called_once()
    called_payload = wa_mock.send_prepared_payload.call_args[0][0]
    # Text body must be preserved verbatim
    assert called_payload["text"]["body"] == APPROVED_TEXT_BODY
    # send_recovery_reminder must NOT be called
    wa_mock.send_recovery_reminder.assert_not_called()


# =============================================================================
# TC-06: Opted-out recipient is rejected (SUPPRESSED)
# =============================================================================

def test_opted_out_recipient_is_rejected():
    """TC-06: If recipient has opted out, dispatch is SUPPRESSED and wa.send_prepared_payload is NOT called."""
    opt_out_mock = MagicMock()
    opt_out_mock.is_opted_out.return_value = True
    wa_mock = MagicMock(spec=WhatsAppClient)
    worker = _make_worker(wa_mock=wa_mock, opt_out_mock=opt_out_mock)
    job = _make_job()
    result = worker.process_single_job(job)
    assert result.status == "SUPPRESSED"
    wa_mock.send_prepared_payload.assert_not_called()


# =============================================================================
# TC-07: Invalid recipient phone is rejected (DEAD_LETTER)
# =============================================================================

def test_invalid_recipient_phone_rejected():
    """TC-07: A malformed 'to' field causes DEAD_LETTER before any dispatch."""
    payload = {**DIRECT_META_PAYLOAD, "to": "not-a-phone"}
    job = _make_job(payload=payload)
    wa_mock = MagicMock(spec=WhatsAppClient)
    worker = _make_worker(wa_mock=wa_mock)
    result = worker.process_single_job(job)
    assert result.status == "DEAD_LETTER"
    wa_mock.send_prepared_payload.assert_not_called()


# =============================================================================
# TC-08: Approval hash mismatch blocks dispatch
# =============================================================================

def test_approval_hash_mismatch_blocks_dispatch():
    """TC-08: A tampered payload (hash mismatch) must be rejected by the auth gate."""
    outbox_mock = MagicMock()
    # Simulate the outbox returning auth failure on hash mismatch
    outbox_mock.verify_dispatch_authorization.return_value = (
        False, "Approval snapshot hash mismatch: payload may have been tampered."
    )
    outbox_mock.fail_job.return_value = None
    wa_mock = MagicMock(spec=WhatsAppClient)
    worker = _make_worker(wa_mock=wa_mock, outbox_mock=outbox_mock)
    job = _make_job()
    result = worker.process_single_job(job)
    assert result.status == "DEAD_LETTER"
    assert "Authorization rejected" in (result.error_message or "")
    wa_mock.send_prepared_payload.assert_not_called()


# =============================================================================
# TC-09: Wrong merchant context — job not claimable
# =============================================================================

def test_wrong_merchant_context_blocked():
    """TC-09: claim_job_by_id with wrong merchant_id returns None (UNCLAIMED)."""
    outbox_mock = MagicMock()
    outbox_mock.claim_job_by_id.return_value = None  # Tenant boundary: job not found for wrong merchant
    worker = _make_worker(outbox_mock=outbox_mock)
    result = worker.process_single_job_by_id(
        job_id=str(uuid.uuid4()),
        merchant_id="wrong-merchant-id",
    )
    assert result.status == "UNCLAIMED"


# =============================================================================
# TC-10: Mode A (action spec) still works correctly
# =============================================================================

def test_action_spec_mode_still_works():
    """TC-10: A valid action spec payload dispatches via send_recovery_reminder (Mode A)."""
    wa_mock = MagicMock(spec=WhatsAppClient)
    wa_mock.send_recovery_reminder.return_value = _make_wa_result()
    rzp_mock = MagicMock()
    # payment_link_id already in payload so no create call needed
    worker = _make_worker(wa_mock=wa_mock, rzp_mock=rzp_mock)
    job = _make_job(payload=dict(ACTION_SPEC_PAYLOAD), idempotency_key="action_spec_test_key")
    result = worker.process_single_job(job)
    assert result.status == "COMPLETED"
    wa_mock.send_recovery_reminder.assert_called_once()
    wa_mock.send_prepared_payload.assert_not_called()
    rzp_mock.create_payment_link.assert_not_called()


# =============================================================================
# TC-11: Zero amount without existing link goes to DEAD_LETTER (Mode A)
# =============================================================================

def test_zero_amount_without_existing_link_goes_to_dead_letter():
    """TC-11: Action spec with amount_paise=0 and no link ID → DEAD_LETTER (not infinite retry)."""
    payload = {
        "customer_phone": RECIPIENT_E164,
        "amount_paise": 0,
        "customer_name": "Test",
        "merchant_name": "Merchant",
        "merchant_id": MERCHANT_ID,
        # NO payment_link_id
    }
    job = _make_job(payload=payload, idempotency_key="action_spec_zero_amount_test_key")
    rzp_mock = MagicMock()
    wa_mock = MagicMock(spec=WhatsAppClient)
    worker = _make_worker(wa_mock=wa_mock, rzp_mock=rzp_mock)
    result = worker.process_single_job(job)
    assert result.status == "DEAD_LETTER"
    assert "amount_paise" in (result.error_message or "")
    rzp_mock.create_payment_link.assert_not_called()
    wa_mock.send_prepared_payload.assert_not_called()


# =============================================================================
# TC-12: Exactly one Meta provider request made (Mode B)
# =============================================================================

def test_exactly_one_meta_provider_request():
    """TC-12: Exactly one call to send_prepared_payload is made for a Mode B job."""
    wa_mock = MagicMock(spec=WhatsAppClient)
    wa_mock.send_prepared_payload.return_value = _make_wa_result()
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)
    worker = _make_worker(wa_mock=wa_mock, rzp_mock=rzp_mock)
    job = _make_job()
    worker.process_single_job(job)
    assert wa_mock.send_prepared_payload.call_count == 1


# =============================================================================
# TC-13: Ambiguous timeout → RECONCILIATION_REQUIRED (not a second send)
# =============================================================================

def test_ambiguous_timeout_does_not_trigger_retry_send():
    """TC-13: httpx.TimeoutException → RECONCILIATION_REQUIRED; mark_reconciliation_required called."""
    wa_mock = MagicMock(spec=WhatsAppClient)
    wa_mock.send_prepared_payload.side_effect = httpx.TimeoutException("Read timeout")
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)
    outbox_mock = MagicMock()
    outbox_mock.verify_dispatch_authorization.return_value = (True, None)
    outbox_mock.mark_reconciliation_required.return_value = None
    outbox_mock.fail_job.return_value = None
    outbox_mock.cancel_jobs_for_case.return_value = None
    worker = _make_worker(wa_mock=wa_mock, rzp_mock=rzp_mock, outbox_mock=outbox_mock)
    job = _make_job()
    result = worker.process_single_job(job)
    assert result.status == "RECONCILIATION_REQUIRED"
    outbox_mock.mark_reconciliation_required.assert_called_once()
    # fail_job must NOT be called (ambiguous timeout is not a confirmed failure)
    for kall in outbox_mock.fail_job.call_args_list:
        # If fail_job was called at all, it should not have been from the dispatch path
        assert False, f"fail_job was called unexpectedly: {kall}"


# =============================================================================
# TC-14: Successful dispatch records wamid
# =============================================================================

def test_successful_dispatch_records_wamid():
    """TC-14: On success, result.whatsapp_message_id equals the wamid returned by Meta."""
    expected_wamid = "wamid.UNIQUE_TEST_ID_001"
    wa_mock = MagicMock(spec=WhatsAppClient)
    wa_mock.send_prepared_payload.return_value = _make_wa_result(wamid=expected_wamid)
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)
    worker = _make_worker(wa_mock=wa_mock, rzp_mock=rzp_mock)
    job = _make_job()
    result = worker.process_single_job(job)
    assert result.status == "COMPLETED"
    assert result.whatsapp_message_id == expected_wamid


# =============================================================================
# TC-15: Exact job isolation maintained
# =============================================================================

def test_exact_job_isolation_maintained():
    """TC-15: process_single_job_by_id with a non-existent / wrong job_id returns UNCLAIMED."""
    outbox_mock = MagicMock()
    outbox_mock.claim_job_by_id.return_value = None
    worker = _make_worker(outbox_mock=outbox_mock)
    result = worker.process_single_job_by_id(
        job_id="00000000-0000-0000-0000-000000000000",
        merchant_id=MERCHANT_ID,
    )
    assert result.status == "UNCLAIMED"
    outbox_mock.claim_job_by_id.assert_called_once_with(
        job_id="00000000-0000-0000-0000-000000000000",
        worker_id="worker_test_2e3",
        lease_duration_seconds=60,
        merchant_id=MERCHANT_ID,
    )


# =============================================================================
# TC-16: Already-approved job dispatched without re-approval
# =============================================================================

def test_already_approved_job_dispatched_without_re_approval():
    """TC-16: A job already approved by operator_arpit is dispatched without any approval mutation."""
    outbox_mock = MagicMock()
    outbox_mock.verify_dispatch_authorization.return_value = (True, None)
    outbox_mock.complete_job.return_value = None
    outbox_mock.fail_job.return_value = None

    wa_mock = MagicMock(spec=WhatsAppClient)
    wa_mock.send_prepared_payload.return_value = _make_wa_result()
    rzp_mock = MagicMock()
    rzp_mock.get_payment_link.return_value = dict(RAZORPAY_LINK_DATA)

    worker = _make_worker(wa_mock=wa_mock, rzp_mock=rzp_mock, outbox_mock=outbox_mock)
    job = _make_job(approved=True)

    assert job.approved_by_operator_id == "operator_arpit"
    result = worker.process_single_job(job)

    # Dispatch succeeds; outbox.complete_job called exactly once
    assert result.status == "COMPLETED"
    outbox_mock.complete_job.assert_called_once()
    # No approval-related calls — there must be no call to approve_job or equivalent
    assert not hasattr(outbox_mock, "approve_job") or outbox_mock.approve_job.call_count == 0

    # wamid must be recorded
    assert result.whatsapp_message_id == EXPECTED_WAMID


# =============================================================================
# Additional: send_prepared_payload unit tests (WhatsAppClient)
# =============================================================================

def test_send_prepared_payload_rejects_missing_messaging_product():
    """send_prepared_payload raises WhatsAppValidationError if messaging_product is wrong."""
    transport = MagicMock(spec=httpx.BaseTransport)
    client = WhatsAppClient(
        access_token="test_token",
        phone_number_id="12345",
        transport=transport,
    )
    with pytest.raises(WhatsAppValidationError, match="messaging_product"):
        client.send_prepared_payload({"to": "919876543210", "type": "text", "text": {"body": "hi"}})


def test_send_prepared_payload_rejects_empty_to():
    """send_prepared_payload raises WhatsAppValidationError if 'to' is missing."""
    transport = MagicMock(spec=httpx.BaseTransport)
    client = WhatsAppClient(
        access_token="test_token",
        phone_number_id="12345",
        transport=transport,
    )
    with pytest.raises(WhatsAppValidationError, match="'to'"):
        client.send_prepared_payload({
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {"body": "hi"},
        })


def test_send_prepared_payload_normalizes_phone_and_calls_send():
    """send_prepared_payload normalizes phone and delegates to _send_payload."""
    transport = MagicMock(spec=httpx.BaseTransport)
    # Build a mock transport that returns a 200 OK
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"messages": [{"id": "wamid.TEST001"}]}

    client = WhatsAppClient(
        access_token="test_token",
        phone_number_id="12345",
        transport=transport,
    )
    with patch.object(client, "_send_payload", return_value=_make_wa_result()) as mock_send:
        result = client.send_prepared_payload(DIRECT_META_PAYLOAD)
        mock_send.assert_called_once()
        called_payload = mock_send.call_args[0][0]
        # Phone should remain as-is (already normalized E.164)
        assert called_payload["to"] == RECIPIENT_E164
        # Text body must not be modified
        assert called_payload["text"]["body"] == APPROVED_TEXT_BODY
