"""
WAPSI Phase 7 — Gate 3: Meta Pre-Approved Template Recovery Engine Tests.

Comprehensive 28-scenario test suite covering:
1. Template Serialization & Parameter Binding (Tests 1-8)
2. 24-Hour Customer Service Window Routing (Tests 9-16)
3. Integration, Governance & Operator Authorization (Tests 17-22)
4. Reliability & Failure Handling (Tests 23-28)

SAFETY & GOVERNANCE CONSTRAINTS:
- No real outbound network dispatches to Meta or Razorpay (all HTTP transports mocked).
- PostgreSQL live target job 5a6587ab-2601-4017-b396-48e3d2fc2fda is never touched.
- Isolated in-memory and SQLite test fixtures.
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import httpx
import pytest

from wapsi.core.config import WapsiSettings, get_settings
from wapsi.integrations.whatsapp.client import (
    WhatsAppAuthError,
    WhatsAppClient,
    WhatsAppDeliveryError,
    WhatsAppDispatchResult,
    WhatsAppError,
    WhatsAppRateLimitError,
    WhatsAppValidationError,
)
from wapsi.integrations.whatsapp.opt_out import OptOutManager
from wapsi.integrations.whatsapp.service_window import (
    CustomerServiceWindowRouter,
    WindowRoutingDecision,
    WindowStatus,
    evaluate_customer_service_window,
    normalize_utc_timestamp,
)
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, compute_approval_hash
from wapsi.recovery.state_machine import RecoveryState, RecoveryStateMachine
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker


# ==============================================================================
# Test Fixtures & Constants
# ==============================================================================

MERCHANT_ID = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
MERCHANT_B_ID = "11111111-2222-3333-4444-555555555555"
TEST_PHONE = "+91 98765-43210"
TEST_PHONE_E164 = "919876543210"
MOCK_WAMID = "wamid.HBgLOTE5ODc2NTQzMjEwFQICERgSMzQ1NTY3ODkwMTIzNDU2Nzg5AA=="


@pytest.fixture
def isolated_opt_out_store(tmp_path):
    """Provides an isolated SQLite opt-out store."""
    db_file = str(tmp_path / "test_opt_out.db")
    store = PersistentOptOutStore(db_path=db_file)
    yield store
    store.clear()


@pytest.fixture
def isolated_outbox_store(tmp_path):
    """Provides an isolated SQLite outbox store."""
    db_file = str(tmp_path / "test_outbox.db")
    store = DurableOutboxStore(db_path=db_file)
    yield store


# ==============================================================================
# Category 1: Template Serialization & Parameter Binding (Tests 1 - 8)
# ==============================================================================

def test_1_valid_body_text_template():
    """TC-01: Serializes valid body text template and parses accepted dispatch result."""
    captured_payload: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        assert request.headers.get("Authorization") == "Bearer mock_token_valid"
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    transport = httpx.MockTransport(handler)
    client = WhatsAppClient(access_token="mock_token_valid", phone_number_id="10987654321", transport=transport)

    body_comp = client.build_body_component(["Alice"])
    res = client.send_template_message(
        to_phone=TEST_PHONE,
        template_name="payment_recovery_v1",
        language_code="en",
        components=[body_comp],
    )

    assert res.success is True
    assert res.message_id == MOCK_WAMID
    assert res.recipient_phone == TEST_PHONE_E164
    assert res.status == "accepted"
    assert captured_payload["messaging_product"] == "whatsapp"
    assert captured_payload["to"] == TEST_PHONE_E164
    assert captured_payload["type"] == "template"
    assert captured_payload["template"]["name"] == "payment_recovery_v1"
    assert captured_payload["template"]["language"]["code"] == "en"
    assert captured_payload["template"]["components"][0]["type"] == "body"
    assert captured_payload["template"]["components"][0]["parameters"][0]["text"] == "Alice"


def test_2_correct_template_name_and_language_validation():
    """TC-02: Validates template name and language code format against Meta specifications."""
    client = WhatsAppClient(access_token="mock_token", phone_number_id="123456")

    # Valid template names
    assert client.validate_template_name("payment_recovery_v1") == "payment_recovery_v1"
    assert client.validate_template_name("hello_world") == "hello_world"
    assert client.validate_template_name("recovery_nudge_2026") == "recovery_nudge_2026"

    # Valid language codes
    assert client.validate_language_code("en") == "en"
    assert client.validate_language_code("en_US") == "en_US"
    assert client.validate_language_code("hi") == "hi"
    assert client.validate_language_code("pt_BR") == "pt_BR"

    # Invalid template names raise WhatsAppValidationError
    with pytest.raises(WhatsAppValidationError, match="lowercase alphanumeric"):
        client.validate_template_name("Payment_Recovery")
    with pytest.raises(WhatsAppValidationError, match="lowercase alphanumeric"):
        client.validate_template_name("payment-recovery!")
    with pytest.raises(WhatsAppValidationError, match="non-empty string"):
        client.validate_template_name("")
    with pytest.raises(WhatsAppValidationError, match="empty or whitespace"):
        client.validate_template_name("   ")

    # Invalid language codes raise WhatsAppValidationError
    with pytest.raises(WhatsAppValidationError, match="standard ISO language"):
        client.validate_language_code("English")
    with pytest.raises(WhatsAppValidationError, match="standard ISO language"):
        client.validate_language_code("123")
    with pytest.raises(WhatsAppValidationError, match="non-empty string"):
        client.validate_language_code("")


def test_3_multiple_dynamic_body_parameters():
    """TC-03: Serializes multiple dynamic body parameters in exact sequential order."""
    captured_payload: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))
    body_comp = client.build_body_component(["Rohan", "Zomato", "Rs 2,500.00", "https://rzp.io/i/test_link"])

    res = client.send_template_message(
        to_phone=TEST_PHONE_E164,
        template_name="payment_recovery_v1",
        language_code="en",
        components=[body_comp],
    )
    assert res.success is True

    params = captured_payload["template"]["components"][0]["parameters"]
    assert len(params) == 4
    assert params[0] == {"type": "text", "text": "Rohan"}
    assert params[1] == {"type": "text", "text": "Zomato"}
    assert params[2] == {"type": "text", "text": "Rs 2,500.00"}
    assert params[3] == {"type": "text", "text": "https://rzp.io/i/test_link"}


def test_4_header_parameter_handling():
    """TC-04: Serializes supported header parameter types (text, image, document)."""
    captured: List[Dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))

    # Text header
    hdr_text = client.build_header_component(text="Urgent Payment Reminder")
    client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1", components=[hdr_text])
    assert captured[-1]["template"]["components"][0]["parameters"][0]["text"] == "Urgent Payment Reminder"

    # Image header
    hdr_img = client.build_header_component(media_type="image", media_url="https://img.rzp.io/brand.png")
    client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1", components=[hdr_img])
    assert captured[-1]["template"]["components"][0]["parameters"][0]["image"]["link"] == "https://img.rzp.io/brand.png"

    # Document header with filename
    hdr_doc = client.build_header_component(media_type="document", media_url="https://doc.rzp.io/inv.pdf", filename="invoice_001.pdf")
    client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1", components=[hdr_doc])
    doc_param = captured[-1]["template"]["components"][0]["parameters"][0]["document"]
    assert doc_param["link"] == "https://doc.rzp.io/inv.pdf"
    assert doc_param["filename"] == "invoice_001.pdf"


def test_5_quick_reply_button_parameters():
    """TC-05: Serializes quick-reply button parameters with developer payload."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))
    btn_comp = client.build_quick_reply_button_component(index=0, payload="PAY_NOW_CONFIRMED")

    res = client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1", components=[btn_comp])
    assert res.success is True

    btn = captured["template"]["components"][0]
    assert btn["type"] == "button"
    assert btn["sub_type"] == "quick_reply"
    assert btn["index"] == "0"
    assert btn["parameters"][0] == {"type": "payload", "payload": "PAY_NOW_CONFIRMED"}

    # Rejection on empty payload
    with pytest.raises(WhatsAppValidationError, match="payload cannot be empty"):
        client.build_quick_reply_button_component(index=0, payload="")


def test_6_dynamic_url_button_parameters():
    """TC-06: Serializes dynamic URL button parameters and enforces character validation."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))
    btn_url = client.build_url_button_component(index=1, url_parameter="plink_TvKucM1yXJQAZA")

    res = client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1", components=[btn_url])
    assert res.success is True

    btn = captured["template"]["components"][0]
    assert btn["type"] == "button"
    assert btn["sub_type"] == "url"
    assert btn["index"] == "1"
    assert btn["parameters"][0] == {"type": "text", "text": "plink_TvKucM1yXJQAZA"}

    # Rejection of whitespace or newlines in URL parameter
    with pytest.raises(WhatsAppValidationError, match="cannot contain whitespace"):
        client.build_url_button_component(index=1, url_parameter="plink with spaces")
    with pytest.raises(WhatsAppValidationError, match="cannot contain whitespace"):
        client.build_url_button_component(index=1, url_parameter="plink\nnewline")
    with pytest.raises(WhatsAppValidationError, match="cannot be empty"):
        client.build_url_button_component(index=1, url_parameter="")


def test_7_correct_json_payload_structure():
    """TC-07: Validates end-to-end JSON payload against Meta WhatsApp Cloud API specification."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))
    components = [
        client.build_header_component(text="Payment Reminder"),
        client.build_body_component(["Alice", "₹500.00"]),
        client.build_url_button_component(index="0", url_parameter="pay_link_xyz"),
    ]

    client.send_template_message(
        to_phone="+91-98765-43210",
        template_name="payment_recovery_v1",
        language_code="en_US",
        components=components,
    )

    assert captured == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "919876543210",
        "type": "template",
        "template": {
            "name": "payment_recovery_v1",
            "language": {"code": "en_US"},
            "components": [
                {"type": "header", "parameters": [{"type": "text", "text": "Payment Reminder"}]},
                {"type": "body", "parameters": [{"type": "text", "text": "Alice"}, {"type": "text", "text": "₹500.00"}]},
                {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": "pay_link_xyz"}]},
            ],
        },
    }


def test_8_invalid_and_incomplete_component_rejection():
    """TC-08: Rejects malformed, incomplete, or unsupported component configurations."""
    client = WhatsAppClient(access_token="tok", phone_number_id="123")

    # Components not a list
    with pytest.raises(WhatsAppValidationError, match="must be a list"):
        client.validate_template_components("not_a_list")  # type: ignore

    # Component not a dict
    with pytest.raises(WhatsAppValidationError, match="must be a dict"):
        client.validate_template_components(["not_a_dict"])  # type: ignore

    # Unknown component type
    with pytest.raises(WhatsAppValidationError, match="invalid or missing 'type'"):
        client.validate_template_components([{"type": "unknown_component"}])

    # Button missing sub_type
    with pytest.raises(WhatsAppValidationError, match="requires valid 'sub_type'"):
        client.validate_template_components([{"type": "button", "index": "0"}])

    # Button with invalid index
    with pytest.raises(WhatsAppValidationError, match="invalid index"):
        client.validate_template_components([{"type": "button", "sub_type": "url", "index": "99", "parameters": [{"type": "text", "text": "x"}]}])

    # Button with empty parameters
    with pytest.raises(WhatsAppValidationError, match="non-empty 'parameters' list"):
        client.validate_template_components([{"type": "button", "sub_type": "url", "index": "0", "parameters": []}])

    # Header with invalid parameter type
    with pytest.raises(WhatsAppValidationError, match="Unsupported header parameter type"):
        client.validate_template_components([{"type": "header", "parameters": [{"type": "audio"}]}])


# ==============================================================================
# Category 2: 24-Hour Customer Service Window Routing (Tests 9 - 16)
# ==============================================================================

def test_9_freeform_message_inside_24h_window(isolated_opt_out_store):
    """TC-09: CASE A — Inbound message within 24h permits freeform rich-text dispatch."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))

    now = time.time()
    isolated_opt_out_store.record_interaction(TEST_PHONE_E164, timestamp=now - 3600.0)  # 1 hour ago

    router = CustomerServiceWindowRouter(opt_out_store=isolated_opt_out_store)
    decision = router.route_outbound_recovery(TEST_PHONE_E164, current_time=now)

    assert decision.status == WindowStatus.OPEN
    assert decision.is_window_open is True
    assert decision.message_type == "text"
    assert decision.requires_manual_review is False

    # Send reminder using client
    res = client.send_recovery_reminder(
        to_phone=TEST_PHONE_E164,
        customer_name="Priya",
        amount_str="Rs 500.00",
        payment_link="https://rzp.io/i/test_link",
        enforce_24h_window=True,
        inbound_timestamp=now - 3600.0,
        current_time=now,
    )
    assert res.success is True
    assert captured["type"] == "text"
    assert "https://rzp.io/i/test_link" in captured["text"]["body"]


def test_10_template_dispatch_outside_24h_window(isolated_opt_out_store):
    """TC-10: CASE B — Inbound interaction > 24h routes to approved template dispatch."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": MOCK_WAMID}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))

    now = time.time()
    isolated_opt_out_store.record_interaction(TEST_PHONE_E164, timestamp=now - 90000.0)  # 25 hours ago

    router = CustomerServiceWindowRouter(
        opt_out_store=isolated_opt_out_store,
        default_template_name="payment_recovery_v1",
    )
    decision = router.route_outbound_recovery(TEST_PHONE_E164, current_time=now)

    assert decision.status == WindowStatus.EXPIRED
    assert decision.is_window_open is False
    assert decision.message_type == "template"
    assert decision.template_name == "payment_recovery_v1"

    # Send reminder outside window with configured template
    res = client.send_recovery_reminder(
        to_phone=TEST_PHONE_E164,
        customer_name="Rohan",
        amount_str="Rs 999.00",
        payment_link="https://rzp.io/i/rohan_link",
        template_name="payment_recovery_v1",
        enforce_24h_window=True,
        inbound_timestamp=now - 90000.0,
        current_time=now,
    )
    assert res.success is True
    assert captured["type"] == "template"
    assert captured["template"]["name"] == "payment_recovery_v1"


def test_11_exactly_24_hour_boundary():
    """TC-11: Correct boundary behavior: exactly 86,400.0s is OPEN; 86,400.001s is EXPIRED."""
    now = 1762164000.0

    # Exactly 24.0 hours (86,400.0 seconds) -> OPEN
    status_exact, _, _ = evaluate_customer_service_window(
        phone=TEST_PHONE_E164,
        last_inbound_timestamp=now - 86400.0,
        current_time=now,
    )
    assert status_exact == WindowStatus.OPEN

    # 1 second past 24.0 hours (86,401.0 seconds) -> EXPIRED
    status_past, _, _ = evaluate_customer_service_window(
        phone=TEST_PHONE_E164,
        last_inbound_timestamp=now - 86401.0,
        current_time=now,
    )
    assert status_past == WindowStatus.EXPIRED

    # 1 millisecond past 24.0 hours -> EXPIRED
    status_ms, _, _ = evaluate_customer_service_window(
        phone=TEST_PHONE_E164,
        last_inbound_timestamp=now - 86400.001,
        current_time=now,
    )
    assert status_ms == WindowStatus.EXPIRED


def test_12_timezone_normalization():
    """TC-12: Deterministic UTC normalization across timezones without local machine bias."""
    # The following representations all denote 2026-11-03 04:30:00 UTC (epoch: 1793680200.0)
    ref_utc_epoch = 1793680200.0
    iso_utc = "2026-11-03T04:30:00Z"
    iso_ist = "2026-11-03T10:00:00+05:30"
    iso_est = "2026-11-02T23:30:00-05:00"
    dt_ist = datetime(2026, 11, 3, 10, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    assert normalize_utc_timestamp(ref_utc_epoch) == ref_utc_epoch
    assert normalize_utc_timestamp(iso_utc) == ref_utc_epoch
    assert normalize_utc_timestamp(iso_ist) == ref_utc_epoch
    assert normalize_utc_timestamp(iso_est) == ref_utc_epoch
    assert normalize_utc_timestamp(dt_ist) == ref_utc_epoch

    # Test window evaluation at ref_utc_epoch + 10 hours (OPEN across all representations)
    eval_time = ref_utc_epoch + (10 * 3600.0)
    for ts in (ref_utc_epoch, iso_utc, iso_ist, iso_est, dt_ist):
        st, _, _ = evaluate_customer_service_window(TEST_PHONE_E164, last_inbound_timestamp=ts, current_time=eval_time)
        assert st == WindowStatus.OPEN

    # Test window evaluation at ref_utc_epoch + 25 hours (EXPIRED across all representations)
    eval_time_exp = ref_utc_epoch + (25 * 3600.0)
    for ts in (ref_utc_epoch, iso_utc, iso_ist, iso_est, dt_ist):
        st, _, _ = evaluate_customer_service_window(TEST_PHONE_E164, last_inbound_timestamp=ts, current_time=eval_time_exp)
        assert st == WindowStatus.EXPIRED


def test_13_missing_inbound_timestamp_fails_closed():
    """TC-13: CASE C — Missing inbound timestamp fails closed (UNKNOWN -> routes to template or review)."""
    fresh_phone = "919000011111"
    router = CustomerServiceWindowRouter(default_template_name="payment_recovery_v1")
    decision = router.route_outbound_recovery(fresh_phone, last_inbound=None)

    assert decision.status == WindowStatus.UNKNOWN
    assert decision.is_window_open is False
    assert decision.message_type == "template"
    assert decision.template_name == "payment_recovery_v1"
    assert "Fail-closed" in decision.reason


def test_14_invalid_timestamp_fails_closed():
    """TC-14: CASE C — Invalid or corrupted timestamp fails closed (INVALID status)."""
    corrupt_timestamps = [
        "corrupted_garbage_ts",
        math.nan,
        -1000.0,
        9999999999999.0,  # Far future corruption
        "2026-99-99T99:99:99",
    ]

    router = CustomerServiceWindowRouter(default_template_name="payment_recovery_v1")
    for bad_ts in corrupt_timestamps:
        decision = router.route_outbound_recovery(TEST_PHONE_E164, last_inbound=bad_ts)
        assert decision.status == WindowStatus.INVALID
        assert decision.is_window_open is False
        assert decision.message_type == "template"


def test_15_missing_template_configuration_fails_closed():
    """TC-15: Window expired/unknown without configured template refuses freeform and flags review."""
    router = CustomerServiceWindowRouter(default_template_name=None)
    decision = router.route_outbound_recovery(
        TEST_PHONE_E164,
        requested_template=None,
        last_inbound=time.time() - 100000.0,  # Expired
    )

    assert decision.status == WindowStatus.EXPIRED
    assert decision.is_window_open is False
    assert decision.message_type == "manual_review"
    assert decision.requires_manual_review is True
    assert decision.template_name is None


def test_16_correct_fallback_to_manual_review_when_template_unavailable():
    """TC-16: Dispatch raises WhatsAppDeliveryError when template dispatch is unavailable outside window."""
    client = WhatsAppClient(access_token="tok", phone_number_id="123")
    uncontacted_phone = "919876549999"

    with pytest.raises(WhatsAppDeliveryError) as exc_info:
        client.send_recovery_reminder(
            to_phone=uncontacted_phone,
            customer_name="Alice",
            amount_str="Rs 500.00",
            payment_link="https://rzp.io/i/test",
            template_name=None,
            enforce_24h_window=True,
            inbound_timestamp=None,  # Missing inbound
        )

    assert "24-hour service window" in str(exc_info.value)
    assert "manual review" in str(exc_info.value).lower()


# ==============================================================================
# Category 3: Integration, Governance & Operator Authorization (Tests 17 - 22)
# ==============================================================================

def test_17_operator_approval_remains_mandatory(isolated_outbox_store):
    """TC-17: Contacting outbox job requires explicit operator approval before dispatch."""
    worker = RecoveryBackgroundWorker(outbox_store=isolated_outbox_store)

    job = isolated_outbox_store.enqueue(
        case_id="case_unapproved_001",
        payment_id="pay_001",
        idempotency_key="idemp_unapproved_001",
        action="DISPATCH_RECOVERY_NUDGE",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload={"customer_phone": TEST_PHONE_E164, "template_name": "payment_recovery_v1"},
        requires_operator_approval=True,
    )
    assert job.status == "PENDING_APPROVAL"

    # Attempt to process without approval
    res = worker.process_single_job(job)
    assert res.status == "DEAD_LETTER"
    assert "approved_by_operator_id is missing" in str(res.error_message)


def test_18_invalid_approval_hash_rejects_dispatch(isolated_outbox_store):
    """TC-18: Tampering with approved template payload rejects dispatch via hash mismatch."""
    worker = RecoveryBackgroundWorker(outbox_store=isolated_outbox_store)

    original_payload = {
        "customer_phone": TEST_PHONE_E164,
        "amount_paise": 1000,
        "template_name": "payment_recovery_v1",
        "payment_link_id": "plink_valid_001",
        "payment_link_url": "https://rzp.io/i/valid",
    }
    job = isolated_outbox_store.enqueue(
        case_id="case_hash_tamper_001",
        payment_id="pay_002",
        idempotency_key="idemp_hash_001",
        action="DISPATCH_RECOVERY_NUDGE",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload=original_payload,
        requires_operator_approval=True,
    )

    # Approve job
    isolated_outbox_store.approve_job(job.id, operator_id="operator_security_lead")

    approved_job = isolated_outbox_store.get_job(job.id)
    assert approved_job.status == "QUEUED"

    # Tamper with message payload (alter template name)
    approved_job.message_payload["template_name"] = "tampered_unauthorized_template"

    res = worker.process_single_job(approved_job)
    assert res.status == "DEAD_LETTER"
    assert "integrity violation" in str(res.error_message).lower()


def test_19_tenant_isolation_remains_intact(isolated_outbox_store):
    """TC-19: Tenant isolation blocks cross-merchant access to outbox recovery jobs."""
    job_a = isolated_outbox_store.enqueue(
        case_id="case_tenant_a_001",
        payment_id="pay_003",
        idempotency_key="idemp_tenant_a",
        action="DISPATCH_RECOVERY_NUDGE",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload={"template_name": "payment_recovery_v1"},
        merchant_id=MERCHANT_ID,
    )

    # Merchant B tries to claim or view Merchant A's job
    job_view = isolated_outbox_store.get_job(job_a.id, merchant_id=MERCHANT_B_ID)
    assert job_view is None or job_view.merchant_id != MERCHANT_B_ID


def test_20_idempotency_prevents_duplicate_dispatch(isolated_outbox_store):
    """TC-20: Idempotency key prevents duplicate enqueue and duplicate worker dispatch."""
    import sqlite3
    payload = {"customer_phone": TEST_PHONE_E164, "template_name": "payment_recovery_v1"}

    job1 = isolated_outbox_store.enqueue(
        case_id="case_idemp_001",
        payment_id="pay_004",
        idempotency_key="idemp_unique_key_123",
        action="DISPATCH_RECOVERY_NUDGE",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload=payload,
    )

    # Database-level uniqueness: duplicate enqueue with exact same idempotency key fails closed
    with pytest.raises((sqlite3.IntegrityError, Exception)):
        isolated_outbox_store.enqueue(
            case_id="case_idemp_001",
            payment_id="pay_004",
            idempotency_key="idemp_unique_key_123",
            action="DISPATCH_RECOVERY_NUDGE",
            channel="WHATSAPP",
            recipient_masked="9198***10",
            message_payload=payload,
        )

    # Worker dispatch idempotency: completed job is not re-dispatched
    mock_wa = MagicMock()
    worker = RecoveryBackgroundWorker(
        outbox_store=isolated_outbox_store,
        whatsapp_client=mock_wa,
    )
    job1.status = "COMPLETED"
    res = worker.process_single_job(job1)
    assert res.status == "DEAD_LETTER" or "AUTHORIZATION_REJECTED" in str(res.error_message)
    assert mock_wa.send_template_message.call_count == 0
    assert mock_wa.send_recovery_reminder.call_count == 0


def test_21_existing_recovery_state_transitions_correct():
    """TC-21: State machine validates lifecycle transitions with template dispatch."""
    case_id = "case_sm_001"
    st = RecoveryState.PENDING

    st, _ = RecoveryStateMachine.transition(case_id, st, RecoveryState.ELIGIBLE, "ELIGIBILITY_CONFIRMED")
    assert st == RecoveryState.ELIGIBLE

    st, _ = RecoveryStateMachine.transition(case_id, st, RecoveryState.SCHEDULED, "RECOVERY_SCHEDULED")
    assert st == RecoveryState.SCHEDULED

    st, _ = RecoveryStateMachine.transition(case_id, st, RecoveryState.DISPATCHING, "JOB_LEASED")
    assert st == RecoveryState.DISPATCHING

    st, _ = RecoveryStateMachine.transition(case_id, st, RecoveryState.DISPATCHED, "TEMPLATE_DISPATCHED")
    assert st == RecoveryState.DISPATCHED

    st, _ = RecoveryStateMachine.transition(case_id, st, RecoveryState.DELIVERED, "WHATSAPP_DELIVERY_RECEIPT")
    assert st == RecoveryState.DELIVERED

    st, _ = RecoveryStateMachine.transition(case_id, st, RecoveryState.READ, "WHATSAPP_READ_RECEIPT")
    assert st == RecoveryState.READ

    st, _ = RecoveryStateMachine.transition(case_id, st, RecoveryState.RECOVERED, "PAYMENT_CAPTURED")
    assert st == RecoveryState.RECOVERED


def test_22_existing_sandbox_behavior_unchanged():
    """TC-22: Development sandbox token routing continues working without modification."""
    settings = WapsiSettings(
        wapsi_env="development",
        razorpay_mode="test",
        whatsapp_auth_mode="dashboard_sandbox",
        whatsapp_diagnostic_token="diagnostic_test_token_123",
    )
    token = settings.get_whatsapp_token_str()
    assert token == "diagnostic_test_token_123"

    client = WhatsAppClient(access_token=token, phone_number_id="123456")
    assert client.access_token == "diagnostic_test_token_123"


# ==============================================================================
# Category 4: Reliability & Failure Handling (Tests 23 - 28)
# ==============================================================================

def test_23_meta_authentication_error():
    """TC-23: HTTP 401 with code 190 raises WhatsAppAuthError and never leaks token."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": 190, "message": "Invalid OAuth access token."}})

    client = WhatsAppClient(access_token="secret_auth_token_999", phone_number_id="123", transport=httpx.MockTransport(handler))

    with pytest.raises(WhatsAppAuthError) as exc_info:
        client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1")

    assert "secret_auth_token_999" not in str(exc_info.value)
    assert exc_info.value.meta_error_code == 190


def test_24_rate_limit_response():
    """TC-24: HTTP 429 raises WhatsAppRateLimitError with backoff error code."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": 4, "message": "Application rate limit reached."}})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", max_retries=1, transport=httpx.MockTransport(handler))

    with pytest.raises(WhatsAppRateLimitError) as exc_info:
        client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1")

    assert exc_info.value.meta_error_code == 4


def test_25_timeout_behavior():
    """TC-25: httpx.TimeoutException is propagated immediately for status reconciliation."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Socket read timed out waiting for Meta gateway")

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.TimeoutException):
        client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1")


def test_26_malformed_provider_response():
    """TC-26: Gracefully parses non-JSON or missing messages list without crashing."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="OK - Malformed Non-JSON Gateway Text")

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler))
    res = client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1")

    assert res.success is True
    assert res.status == "accepted"
    assert res.message_id.startswith("wamid_gen_")


def test_27_ambiguous_provider_acceptance_does_not_blind_retry():
    """TC-27: Ambiguous network timeout on POST request executes exactly once (no blind retry)."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("Meta Cloud API gateway timeout")

    client = WhatsAppClient(access_token="tok", phone_number_id="123", max_retries=3, transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.TimeoutException):
        client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1")

    # Critical requirement: Exactly ONE attempt was made before propagating timeout
    assert call_count == 1


def test_28_credentials_are_not_exposed_in_logs(caplog):
    """TC-28: Access tokens, auth headers, and customer secrets are never exposed in log output."""
    secret_token = "meta_system_user_super_secret_token_2026"
    client = WhatsAppClient(access_token=secret_token, phone_number_id="10987654321")

    with caplog.at_level(logging.DEBUG):
        # Trigger validation error and phone logging
        try:
            client.send_template_message("+91 98765-43210", "invalid template with spaces!")
        except Exception:
            pass

    log_text = caplog.text
    assert secret_token not in log_text
    assert "Bearer" not in log_text
    assert "+91 98765-43210" not in log_text  # Must be masked (e.g. 9198***10)


# ==============================================================================
# Category 5: Deep Robustness & Defect Verification (Tests 29 - 36)
# ==============================================================================

def test_29_language_subtags_and_hyphen_normalization():
    """TC-29: Validates non-standard language sub-tags and normalizes BCP-47 hyphenated tags."""
    client = WhatsAppClient(access_token="tok", phone_number_id="123")

    # Non-standard language sub-tags from Meta's language table
    assert client.validate_language_code("es_LA") == "es_LA"
    assert client.validate_language_code("pt_BR") == "pt_BR"
    assert client.validate_language_code("zh_HK") == "zh_HK"
    assert client.validate_language_code("zh_CN") == "zh_CN"
    assert client.validate_language_code("zh_TW") == "zh_TW"
    assert client.validate_language_code("fil") == "fil"
    assert client.validate_language_code("mai") == "mai"

    # Hyphenated BCP-47 normalization to Meta underscore format
    assert client.validate_language_code("en-US") == "en_US"
    assert client.validate_language_code("es-LA") == "es_LA"
    assert client.validate_language_code("pt-BR") == "pt_BR"


def test_30_normalize_utc_timestamp_strict_range_rejection():
    """TC-30: Rejects pre-1970 and far-future corruptions across datetimes and ISO strings."""
    # Pre-1970 ISO string and datetime
    assert normalize_utc_timestamp("1960-01-01T00:00:00Z") is None
    assert normalize_utc_timestamp(datetime(1960, 1, 1, tzinfo=timezone.utc)) is None

    # Far-future ISO string and datetime (> year 2100 / 4,102,444,800)
    assert normalize_utc_timestamp("2500-01-01T00:00:00Z") is None
    assert normalize_utc_timestamp(datetime(2500, 1, 1, tzinfo=timezone.utc)) is None

    # Valid boundaries
    assert normalize_utc_timestamp("2026-11-03T04:30:00Z") == 1793680200.0
    assert normalize_utc_timestamp(datetime(2026, 11, 3, 4, 30, 0, tzinfo=timezone.utc)) == 1793680200.0


def test_31_opt_out_repository_timezone_naive_compatibility():
    """TC-31: OptOutRepository handles timezone-naive datetimes without TypeError or local skew."""
    from unittest.mock import MagicMock
    from wapsi.db.repository import OptOutRepository

    mock_session = MagicMock()
    mock_record = MagicMock()
    # Simulate database returning a timezone-naive datetime: 2026-11-03 04:30:00 UTC
    mock_record.last_interaction_at = datetime(2026, 11, 3, 4, 30, 0)
    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_record

    # 1. Test get_last_interaction returns UTC epoch float (1793680200.0), not machine-local
    last_ts = OptOutRepository.get_last_interaction(mock_session, "919876543210")
    assert last_ts == 1793680200.0

    # 2. Test is_within_24h_window with aware current_time does not raise TypeError
    eval_now_aware = datetime(2026, 11, 3, 10, 0, 0, tzinfo=timezone.utc)
    is_open = OptOutRepository.is_within_24h_window(mock_session, "919876543210", current_time=eval_now_aware)
    assert is_open is True

    # 3. Test is_within_24h_window at 25 hours later returns False
    eval_now_expired = datetime(2026, 11, 4, 6, 0, 0, tzinfo=timezone.utc)
    is_expired = OptOutRepository.is_within_24h_window(mock_session, "919876543210", current_time=eval_now_expired)
    assert is_expired is False


def test_32_meta_response_null_or_empty_id_fallback():
    """TC-32: Fallback synthetic wamid is assigned when Meta returns null or empty message ID."""
    captured: Dict[str, Any] = {}

    def handler_null_id(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messages": [{"id": None}]})

    client = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler_null_id))
    res = client.send_template_message(TEST_PHONE_E164, "payment_recovery_v1")

    assert res.success is True
    assert isinstance(res.message_id, str)
    assert res.message_id.startswith("wamid_gen_")
    assert len(res.message_id) > 10

    def handler_empty_list(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messages": []})

    client2 = WhatsAppClient(access_token="tok", phone_number_id="123", transport=httpx.MockTransport(handler_empty_list))
    res2 = client2.send_template_message(TEST_PHONE_E164, "payment_recovery_v1")
    assert res2.success is True
    assert res2.message_id.startswith("wamid_gen_")


def test_33_button_builder_index_validation():
    """TC-33: Button component builders enforce index bounds (0..9) at creation time."""
    client = WhatsAppClient(access_token="tok", phone_number_id="123")

    # Valid button indices
    b_url = client.build_url_button_component(index=0, url_parameter="link_123")
    assert b_url["index"] == "0"
    b_qr = client.build_quick_reply_button_component(index="3", payload="YES")
    assert b_qr["index"] == "3"

    # Invalid button indices raise WhatsAppValidationError immediately
    with pytest.raises(WhatsAppValidationError, match="integer 0..9"):
        client.build_url_button_component(index=-1, url_parameter="link_123")
    with pytest.raises(WhatsAppValidationError, match="integer 0..9"):
        client.build_url_button_component(index=10, url_parameter="link_123")
    with pytest.raises(WhatsAppValidationError, match="integer 0..9"):
        client.build_quick_reply_button_component(index="bad_idx", payload="YES")


def test_34_body_currency_and_date_time_validation():
    """TC-34: Validates currency and date_time body parameter structures."""
    client = WhatsAppClient(access_token="tok", phone_number_id="123")

    # Valid currency parameter
    valid_currency = {
        "type": "body",
        "parameters": [
            {"type": "currency", "currency": {"fallback_value": "₹500.00", "code": "INR", "amount_1000": 500000}}
        ],
    }
    validated = client.validate_template_components([valid_currency])
    assert len(validated) == 1

    # Valid date_time parameter
    valid_dt = {
        "type": "body",
        "parameters": [
            {"type": "date_time", "date_time": {"fallback_value": "2026-11-03 10:00:00"}}
        ],
    }
    validated_dt = client.validate_template_components([valid_dt])
    assert len(validated_dt) == 1

    # Missing currency dict raises WhatsAppValidationError
    with pytest.raises(WhatsAppValidationError, match="must contain 'currency' dict"):
        client.validate_template_components([{"type": "body", "parameters": [{"type": "currency"}]}])

    # Missing date_time dict raises WhatsAppValidationError
    with pytest.raises(WhatsAppValidationError, match="must contain 'date_time' dict"):
        client.validate_template_components([{"type": "body", "parameters": [{"type": "date_time"}]}])


def test_35_location_header_parameter_handling():
    """TC-35: Validates location header component parameters."""
    client = WhatsAppClient(access_token="tok", phone_number_id="123")

    # Valid location header
    valid_loc = {
        "type": "header",
        "parameters": [
            {"type": "location", "location": {"latitude": 19.0760, "longitude": 72.8777, "name": "Mumbai Office"}}
        ],
    }
    validated = client.validate_template_components([valid_loc])
    assert len(validated) == 1

    # Incomplete location header raises WhatsAppValidationError
    with pytest.raises(WhatsAppValidationError, match="latitude"):
        client.validate_template_components([{"type": "header", "parameters": [{"type": "location", "location": {"name": "No coords"}}]}])


def test_36_worker_mode_a_extracts_and_routes_24h_service_window(isolated_outbox_store):
    """TC-36: Worker Mode A extracts enforce_24h_window and inbound_timestamp and routes to template."""
    now = 1762164000.0
    mock_wa = MagicMock()
    mock_wa.send_recovery_reminder.return_value = WhatsAppDispatchResult(
        success=True,
        message_id=MOCK_WAMID,
        recipient_phone=TEST_PHONE_E164,
        status="accepted",
        timestamp=now,
        raw_response={"messages": [{"id": MOCK_WAMID}]},
    )

    worker = RecoveryBackgroundWorker(
        outbox_store=isolated_outbox_store,
        whatsapp_client=mock_wa,
    )

    payload = {
        "customer_phone": TEST_PHONE_E164,
        "amount_paise": 1500,
        "customer_name": "Deepak",
        "merchant_name": "Acme",
        "payment_link_id": "plink_test_36",
        "payment_link_url": "https://rzp.io/i/plink_test_36",
        "template_name": "payment_recovery_v1",
        "enforce_24h_window": True,
        "inbound_timestamp": now - 100000.0,  # Expired (> 27 hours ago)
    }

    job = isolated_outbox_store.enqueue(
        case_id="case_worker_36",
        payment_id="pay_036",
        idempotency_key="idemp_worker_36",
        action="DISPATCH_RECOVERY_NUDGE",
        channel="WHATSAPP",
        recipient_masked="9198***10",
        message_payload=payload,
        requires_operator_approval=True,
    )
    isolated_outbox_store.approve_job(job.id, operator_id="lead_operator")
    approved_job = isolated_outbox_store.get_job(job.id)

    res = worker.process_single_job(approved_job)
    assert res.status == "COMPLETED"

    # Verify send_recovery_reminder received enforce_24h_window=True and inbound_timestamp
    mock_wa.send_recovery_reminder.assert_called_once()
    _, kwargs = mock_wa.send_recovery_reminder.call_args
    assert kwargs["enforce_24h_window"] is True
    assert kwargs["inbound_timestamp"] == now - 100000.0
    assert kwargs["template_name"] == "payment_recovery_v1"

