"""
Tests for WAPSI Phase 4 — WhatsApp Inbound Webhook Integration.

Verifies:
1. Webhook Signature Verification (Valid HMAC-SHA256, tampered, missing in prod, missing secret fail-closed).
2. Subscription Handshake GET (Valid challenge, invalid token 403).
3. Inbound Customer STOP / Opt-Out (Persistent opt-out store, outbox job cancellation, case SUPPRESSED_OPT_OUT, timeline).
4. Inbound Customer Interaction (Meta 24h service window timestamp, no opt-out).
5. Inbound Message Deduplication (Persistent inbox idempotency, DUPLICATE_IGNORED).
6. WhatsApp Delivery Status Receipts (sent, delivered, read, failed transitions, duplicate status deduplication).
7. Out-of-Order WhatsApp Failure Protection (Never downgrade RECOVERED).
8. Mixed Webhook Payloads (Single payload containing both statuses and messages).
9. Database Error Fail-Closed / Retryable (HTTP 500 when persistence fails).
"""

import hashlib
import hmac
import json
import time
import uuid
import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from wapsi.api.app import app
from wapsi.core.config import WapsiSettings, get_settings
from wapsi.integrations.orchestration.recovery_orchestrator import (
    RecoveryDispatchReceipt,
    get_recovery_orchestrator,
)
from wapsi.integrations.whatsapp.opt_out import get_opt_out_manager
from wapsi.recovery.opt_out_store import PersistentOptOutStore, get_persistent_opt_out_store, set_persistent_opt_out_store
from wapsi.recovery.outbox import DurableOutboxStore, get_outbox_store
from wapsi.recovery.state_machine import RecoveryState
from wapsi.recovery.timeline import RecoveryTimelineStore, get_timeline_store
from wapsi.recovery.webhook_processor import (
    DurableWebhookEventProcessor,
    DurableWebhookInbox,
    get_durable_webhook_processor,
    set_durable_webhook_processor,
)


TEST_META_SECRET = "test_meta_app_secret_phase4_xyz"
TEST_VERIFY_TOKEN = "test_verify_token_phase4"


def sign_payload(body: bytes, secret: str = TEST_META_SECRET) -> str:
    """Computes X-Hub-Signature-256 header."""
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def make_whatsapp_payload(statuses=None, messages=None):
    """Builds standard Meta Graph API webhook structure."""
    value = {
        "messaging_product": "whatsapp",
        "metadata": {
            "display_phone_number": "911234567890",
            "phone_number_id": "phone_id_999",
        },
    }
    if statuses is not None:
        value["statuses"] = statuses
    if messages is not None:
        value["messages"] = messages

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "biz_acc_12345",
                "changes": [
                    {
                        "field": "messages",
                        "value": value,
                    }
                ],
            }
        ],
    }


@pytest.fixture(autouse=True)
def setup_isolated_phase4_environment(tmp_path, monkeypatch):
    """
    Isolates all stores in a temporary SQLite directory for each test run.
    Resets singletons and configures test secrets.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "wapsi_env", "development")
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr(TEST_META_SECRET))
    monkeypatch.setattr(settings, "whatsapp_webhook_verify_token", SecretStr(TEST_VERIFY_TOKEN))
    monkeypatch.setattr(settings, "whatsapp_business_account_id", "biz_acc_12345")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "phone_id_999")
    monkeypatch.setattr(
        WapsiSettings,
        "get_meta_app_secret_bytes",
        lambda self: TEST_META_SECRET.encode("utf-8"),
    )
    monkeypatch.setattr(
        WapsiSettings,
        "get_whatsapp_verify_token_str",
        lambda self: TEST_VERIFY_TOKEN,
    )

    # Initialize isolated SQLite stores
    inbox_db = str(tmp_path / "inbox.db")
    opt_out_db = str(tmp_path / "opt_outs.db")
    outbox_db = str(tmp_path / "outbox.db")
    timeline_db = str(tmp_path / "timeline.db")

    inbox = DurableWebhookInbox(db_path=inbox_db)
    opt_out_store = PersistentOptOutStore(db_path=opt_out_db)
    set_persistent_opt_out_store(opt_out_store)

    outbox_store = DurableOutboxStore(db_path=outbox_db)
    timeline_store = RecoveryTimelineStore(db_path=timeline_db)

    processor = DurableWebhookEventProcessor(
        inbox=inbox,
        timeline_store=timeline_store,
        outbox_store=outbox_store,
        opt_out_store=opt_out_store,
    )
    set_durable_webhook_processor(processor)

    # Clean in-memory orchestrator and opt_out_manager
    orch = get_recovery_orchestrator()
    orch._cases.clear()
    orch._message_to_case.clear()
    orch._link_to_case.clear()
    orch._processed_events.clear()

    opt_mgr = get_opt_out_manager()
    opt_mgr.clear()

    yield {
        "processor": processor,
        "opt_out_store": opt_out_store,
        "outbox_store": outbox_store,
        "timeline_store": timeline_store,
        "orchestrator": orch,
        "client": TestClient(app),
    }

    # Teardown
    set_durable_webhook_processor(None)
    set_persistent_opt_out_store(None)


# -------------------------------------------------------------------------
# Scenario 1: Webhook Signature Verification
# -------------------------------------------------------------------------

def test_signature_verification_valid_signature(setup_isolated_phase4_environment):
    """Valid HMAC-SHA256 signature succeeds with HTTP 200."""
    client = setup_isolated_phase4_environment["client"]
    payload = make_whatsapp_payload(statuses=[
        {
            "id": "wamid.TEST_SIG_1",
            "recipient_id": "919876543210",
            "status": "delivered",
            "timestamp": str(int(time.time())),
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_bytes, TEST_META_SECRET)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "received"
    assert res.json()["statuses_processed"] == 1


def test_signature_verification_tampered_payload_rejected(setup_isolated_phase4_environment):
    """Tampered payload or bad signature is rejected with HTTP 401."""
    client = setup_isolated_phase4_environment["client"]
    payload = make_whatsapp_payload(statuses=[{"id": "wamid.TAMPER", "status": "sent"}])
    raw_bytes = json.dumps(payload).encode("utf-8")

    # Pass completely incorrect signature
    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=invalid_hash_value"},
    )
    assert res.status_code == 401
    assert "cryptographic verification failed" in res.json()["detail"].lower()


def test_signature_verification_missing_signature_with_secret_rejected(setup_isolated_phase4_environment):
    """When META_APP_SECRET is configured, missing signature header is rejected with HTTP 401."""
    client = setup_isolated_phase4_environment["client"]
    payload = make_whatsapp_payload(statuses=[{"id": "wamid.NO_SIG", "status": "sent"}])
    raw_bytes = json.dumps(payload).encode("utf-8")

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 401


def test_signature_verification_production_missing_secret_fails_closed(setup_isolated_phase4_environment, monkeypatch):
    """In production (wapsi_env == 'production'), missing META_APP_SECRET fails closed with HTTP 500."""
    client = setup_isolated_phase4_environment["client"]
    settings = get_settings()
    monkeypatch.setattr(settings, "wapsi_env", "production")
    monkeypatch.setattr(settings, "meta_app_secret", None)

    payload = make_whatsapp_payload(statuses=[{"id": "wamid.PROD_FAIL", "status": "sent"}])
    raw_bytes = json.dumps(payload).encode("utf-8")

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 500
    assert "Production configuration error" in res.json()["detail"]


# -------------------------------------------------------------------------
# Scenario 2: Subscription Handshake GET
# -------------------------------------------------------------------------

def test_subscription_handshake_success(setup_isolated_phase4_environment):
    """Correct hub.mode=subscribe and hub.verify_token returns hub.challenge as plain text HTTP 200."""
    client = setup_isolated_phase4_environment["client"]
    res = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": TEST_VERIFY_TOKEN,
            "hub.challenge": "CHALLENGE_PHASE4_ACCEPTED",
        },
    )
    assert res.status_code == 200
    assert res.text == "CHALLENGE_PHASE4_ACCEPTED"


def test_subscription_handshake_invalid_token(setup_isolated_phase4_environment):
    """Incorrect hub.verify_token returns HTTP 403."""
    client = setup_isolated_phase4_environment["client"]
    res = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token_123",
            "hub.challenge": "CHALLENGE",
        },
    )
    assert res.status_code == 403
    assert "subscription verification failed" in res.json()["detail"].lower()


# -------------------------------------------------------------------------
# Scenario 3: Inbound Customer STOP / Opt-Out
# -------------------------------------------------------------------------

def test_inbound_opt_out_suppresses_case_and_cancels_outbox(setup_isolated_phase4_environment):
    """
    Inbound 'STOP' keyword:
    - Registers persistent opt-out in PersistentOptOutStore.
    - Transitions pending case to SUPPRESSED_OPT_OUT.
    - Cancels scheduled outbox jobs for that case.
    - Records CUSTOMER_OPTED_OUT in timeline.
    """
    env = setup_isolated_phase4_environment
    client = env["client"]
    processor = env["processor"]
    opt_out = env["opt_out_store"]
    outbox = env["outbox_store"]
    timeline = env["timeline_store"]
    orch = env["orchestrator"]

    case_id = "CASE-OPT-001"
    customer_phone = "919988776655"
    norm_phone = PersistentOptOutStore.normalize_phone(customer_phone)

    # Setup pending recovery case
    processor.register_case_mapping(
        case_id=case_id,
        initial_status=RecoveryState.DISPATCHED,
        customer_phone=customer_phone,
        whatsapp_message_id="wamid.INITIAL_MSG",
    )
    # Simulate pending retry job in outbox
    job = outbox.enqueue(
        case_id=case_id,
        payment_id="pay_001",
        idempotency_key="key_retry_001",
        action="WHATSAPP_NUDGE",
        channel="whatsapp",
        recipient_masked=customer_phone,
        message_payload={"text": "recovery reminder"},
        delay_seconds=3600,
    )
    job_id = job.id
    # Register in orchestrator memory
    orch._cases[case_id] = RecoveryDispatchReceipt(
        case_id=case_id,
        payment_id="pay_001",
        amount_paise=150000,
        amount_inr=1500.0,
        payment_link_id="plink_001",
        payment_link_url="https://rzp.io/i/plink_001",
        whatsapp_message_id="wamid.INITIAL_MSG",
        recipient_phone=customer_phone,
        status="DISPATCHED",
        created_at=time.time(),
        updated_at=time.time(),
    )

    # Inbound STOP message
    payload = make_whatsapp_payload(messages=[
        {
            "id": "wamid.INBOUND_STOP_1",
            "from": customer_phone,
            "timestamp": str(int(time.time())),
            "type": "text",
            "text": {"body": "STOP please do not contact me"},
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_bytes)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200
    assert res.json()["messages_processed"] == 1

    # 1. Persistent Opt-Out Store verification
    assert opt_out.is_opted_out(norm_phone) is True

    # 2. Case state transition to SUPPRESSED_OPT_OUT
    assert processor.get_case_status(case_id) == RecoveryState.SUPPRESSED_OPT_OUT
    assert orch._cases[case_id].status == "SUPPRESSED_OPT_OUT"

    # 3. Outbox job cancelled
    job = outbox.get_job(job_id)
    assert job is not None
    assert job.status == "CANCELLED"
    assert job.last_error == "CUSTOMER_OPTED_OUT"

    # 4. Timeline record verification
    events = timeline.get_timeline(case_id)
    opt_events = [e for e in events if e.event_type == "CUSTOMER_OPTED_OUT"]
    assert len(opt_events) >= 1
    assert opt_events[0].to_state == "SUPPRESSED_OPT_OUT"


# -------------------------------------------------------------------------
# Scenario 4: Inbound Customer Interaction (Service Window)
# -------------------------------------------------------------------------

def test_inbound_customer_interaction_updates_window_without_opt_out(setup_isolated_phase4_environment):
    """
    Non-opt-out customer message ('Where is my order?'):
    - Updates 24h Meta customer service window interaction timestamp.
    - Does NOT trigger opt-out.
    - Returns HTTP 200.
    """
    env = setup_isolated_phase4_environment
    client = env["client"]
    opt_out = env["opt_out_store"]

    customer_phone = "919123456789"
    norm_phone = PersistentOptOutStore.normalize_phone(customer_phone)
    msg_time = time.time()

    payload = make_whatsapp_payload(messages=[
        {
            "id": "wamid.INBOUND_QUESTION_1",
            "from": customer_phone,
            "timestamp": str(int(msg_time)),
            "type": "text",
            "text": {"body": "Hi, where is my order delivery?"},
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_bytes)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200
    assert res.json()["messages_processed"] == 1

    # Opt-out is NOT recorded
    assert opt_out.is_opted_out(norm_phone) is False

    # 24-hour service window IS active
    assert opt_out.is_within_24h_window(norm_phone, current_time=msg_time + 3600) is True
    # Beyond 24 hours (86,401 seconds), window expires
    assert opt_out.is_within_24h_window(norm_phone, current_time=msg_time + 86401) is False


# -------------------------------------------------------------------------
# Scenario 5: Inbound Message Deduplication
# -------------------------------------------------------------------------

def test_inbound_message_deduplication(setup_isolated_phase4_environment):
    """Repeated delivery of the same inbound message_id is acknowledged as DUPLICATE_IGNORED."""
    env = setup_isolated_phase4_environment
    client = env["client"]

    msg_id = "wamid.DEDUP_MSG_999"
    payload = make_whatsapp_payload(messages=[
        {
            "id": msg_id,
            "from": "919876500000",
            "timestamp": str(int(time.time())),
            "type": "text",
            "text": {"body": "Hello support"},
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_bytes)

    # First delivery
    res1 = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res1.status_code == 200
    assert res1.json()["messages_processed"] == 1
    assert res1.json()["messages_duplicate"] == 0

    # Second delivery (identical message_id)
    res2 = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res2.status_code == 200
    assert res2.json()["messages_processed"] == 0
    assert res2.json()["messages_duplicate"] == 1


# -------------------------------------------------------------------------
# Scenario 6: WhatsApp Delivery Status Receipts & Deduplication
# -------------------------------------------------------------------------

def test_whatsapp_delivery_status_progression_and_deduplication(setup_isolated_phase4_environment):
    """
    Tests progression through 'sent' -> 'delivered' -> 'read',
    and verifies that identical delivery callbacks are deduplicated idempotently.
    """
    env = setup_isolated_phase4_environment
    client = env["client"]
    processor = env["processor"]
    timeline = env["timeline_store"]
    orch = env["orchestrator"]

    case_id = "CASE-STATUS-001"
    msg_id = "wamid.PROGRESSION_100"
    phone = "919876543210"

    processor.register_case_mapping(
        case_id=case_id,
        initial_status=RecoveryState.PENDING,
        whatsapp_message_id=msg_id,
        customer_phone=phone,
    )
    orch._cases[case_id] = RecoveryDispatchReceipt(
        case_id=case_id,
        payment_id="pay_002",
        amount_paise=100000,
        amount_inr=1000.0,
        payment_link_id="plink_002",
        payment_link_url="https://rzp.io/i/plink_002",
        whatsapp_message_id=msg_id,
        recipient_phone=phone,
        status="PENDING",
        created_at=time.time(),
        updated_at=time.time(),
    )
    orch._message_to_case[msg_id] = case_id

    # 1. 'sent' callback
    ts = str(int(time.time()))
    p_sent = make_whatsapp_payload(statuses=[{"id": msg_id, "status": "sent", "timestamp": ts, "recipient_id": phone}])
    r_sent = client.post(
        "/api/v1/webhooks/whatsapp",
        content=json.dumps(p_sent).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_payload(json.dumps(p_sent).encode())},
    )
    assert r_sent.status_code == 200
    assert processor.get_case_status(case_id) == RecoveryState.DISPATCHED
    assert orch._cases[case_id].status == "SENT"

    # 2. 'delivered' callback
    p_deliv = make_whatsapp_payload(statuses=[{"id": msg_id, "status": "delivered", "timestamp": ts, "recipient_id": phone}])
    r_deliv = client.post(
        "/api/v1/webhooks/whatsapp",
        content=json.dumps(p_deliv).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_payload(json.dumps(p_deliv).encode())},
    )
    assert r_deliv.status_code == 200
    assert processor.get_case_status(case_id) == RecoveryState.DELIVERED
    assert orch._cases[case_id].status == "DELIVERED"

    # 3. Duplicate 'delivered' callback (exact same timestamp)
    r_deliv_dup = client.post(
        "/api/v1/webhooks/whatsapp",
        content=json.dumps(p_deliv).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_payload(json.dumps(p_deliv).encode())},
    )
    assert r_deliv_dup.status_code == 200
    assert r_deliv_dup.json()["statuses_duplicate"] == 1
    assert r_deliv_dup.json()["statuses_processed"] == 0

    # 4. 'read' callback
    p_read = make_whatsapp_payload(statuses=[{"id": msg_id, "status": "read", "timestamp": ts, "recipient_id": phone}])
    r_read = client.post(
        "/api/v1/webhooks/whatsapp",
        content=json.dumps(p_read).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_payload(json.dumps(p_read).encode())},
    )
    assert r_read.status_code == 200
    assert processor.get_case_status(case_id) == RecoveryState.READ
    assert orch._cases[case_id].status == "READ"

    # Verify timeline events recorded
    events = timeline.get_timeline(case_id)
    event_types = [e.event_type for e in events]
    assert "WHATSAPP_DISPATCHED" in event_types
    assert "WHATSAPP_DELIVERED" in event_types
    assert "WHATSAPP_READ" in event_types


# -------------------------------------------------------------------------
# Scenario 7: Out-of-Order WhatsApp Failure Protection
# -------------------------------------------------------------------------

def test_out_of_order_failure_never_downgrades_recovered_case(setup_isolated_phase4_environment):
    """
    When a case is already RECOVERED (e.g. from Razorpay payment capture),
    a delayed WhatsApp 'failed' callback must NEVER downgrade the case status.
    """
    env = setup_isolated_phase4_environment
    client = env["client"]
    processor = env["processor"]
    orch = env["orchestrator"]

    case_id = "CASE-RECOVERED-001"
    msg_id = "wamid.LATE_FAIL_123"
    phone = "919876543210"

    # Register as RECOVERED
    processor.register_case_mapping(
        case_id=case_id,
        initial_status=RecoveryState.RECOVERED,
        whatsapp_message_id=msg_id,
        customer_phone=phone,
    )
    orch._cases[case_id] = RecoveryDispatchReceipt(
        case_id=case_id,
        payment_id="pay_rec_001",
        amount_paise=250000,
        amount_inr=2500.0,
        payment_link_id="plink_rec_001",
        payment_link_url="https://rzp.io/i/plink_rec_001",
        whatsapp_message_id=msg_id,
        recipient_phone=phone,
        status="RECOVERED",
        created_at=time.time(),
        updated_at=time.time(),
    )
    orch._message_to_case[msg_id] = case_id

    # Delayed 'failed' status delivery arrives from Meta
    payload = make_whatsapp_payload(statuses=[
        {
            "id": msg_id,
            "status": "failed",
            "timestamp": str(int(time.time())),
            "recipient_id": phone,
            "errors": [{"code": 131026, "title": "Message undeliverable"}],
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_bytes)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200

    # Invariant check: Status remains RECOVERED
    assert processor.get_case_status(case_id) == RecoveryState.RECOVERED
    assert orch._cases[case_id].status == "RECOVERED"


# -------------------------------------------------------------------------
# Scenario 8: Mixed Webhook Payloads
# -------------------------------------------------------------------------

def test_mixed_webhook_payload_with_statuses_and_messages(setup_isolated_phase4_environment):
    """A single webhook payload containing BOTH statuses and messages is parsed and processed without dropping either."""
    env = setup_isolated_phase4_environment
    client = env["client"]
    processor = env["processor"]
    opt_out = env["opt_out_store"]

    case_id = "CASE-MIXED-001"
    msg_id = "wamid.MIXED_STATUS_1"
    phone_status = "919876543210"
    phone_msg = "919988771122"

    processor.register_case_mapping(
        case_id=case_id,
        initial_status=RecoveryState.DISPATCHING,
        whatsapp_message_id=msg_id,
        customer_phone=phone_status,
    )

    payload = make_whatsapp_payload(
        statuses=[
            {
                "id": msg_id,
                "status": "delivered",
                "timestamp": str(int(time.time())),
                "recipient_id": phone_status,
            }
        ],
        messages=[
            {
                "id": "wamid.MIXED_INBOUND_MSG_1",
                "from": phone_msg,
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": "STOP notifications"},
            }
        ],
    )
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_bytes)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["event_type"] == "mixed"
    assert body["statuses_processed"] == 1
    assert body["messages_processed"] == 1

    # Verify status progressed
    assert processor.get_case_status(case_id) == RecoveryState.DELIVERED
    # Verify opt-out recorded
    assert opt_out.is_opted_out(PersistentOptOutStore.normalize_phone(phone_msg)) is True


# -------------------------------------------------------------------------
# Scenario 9: Database Error Fail-Closed / Retryable
# -------------------------------------------------------------------------

def test_database_error_fails_closed_with_http_500(setup_isolated_phase4_environment, monkeypatch):
    """
    If durable persistence encounters an unexpected database failure,
    the endpoint does NOT acknowledge success, returning retryable HTTP 500 to Meta.
    """
    env = setup_isolated_phase4_environment
    client = env["client"]
    processor = env["processor"]

    # Monkeypatch inbox.check_or_record to simulate unexpected database outage
    def failing_check_or_record(*args, **kwargs):
        raise RuntimeError("PostgreSQL pooler connection refused: database offline")

    monkeypatch.setattr(processor.inbox, "check_or_record", failing_check_or_record)

    payload = make_whatsapp_payload(statuses=[
        {
            "id": "wamid.DB_FAIL_1",
            "status": "delivered",
            "timestamp": str(int(time.time())),
            "recipient_id": "919876543210",
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw_bytes)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 500
    assert "Durable webhook processing failed" in res.json()["detail"]
