"""
WAPSI Phase 6 — Webhook Authentication and Durable Ingestion Tests.

Verifies:
1. Correct HMAC-SHA256 signature accepted in development mode.
2. Incorrect signature rejected with HTTP 401.
3. Missing signature rejected with HTTP 401.
4. Malformed signature rejected with HTTP 401.
5. Missing META_APP_SECRET fails closed with HTTP 500 in development mode.
6. Signature verification strictly enforced in development mode (no WAPSI_ENV bypass).
7. Raw bytes used for HMAC verification without JSON reserialization.
8. Mismatched WABA ID or Phone Number ID rejected with HTTP 400.
9. Genuine inbound events persist in webhook_inbox.
10. Customer interaction is persisted and 24h window unlocked.
11. Duplicate wamid is deduplicated idempotently (DUPLICATE_IGNORED).
12. Database persistence failure returns retryable HTTP 500, never false success.
13. Inbound message NEVER approves or transitions an outbox job in PENDING_APPROVAL.
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
from wapsi.recovery.opt_out_store import (
    PersistentOptOutStore,
    get_persistent_opt_out_store,
    set_persistent_opt_out_store,
)
from wapsi.recovery.outbox import DurableOutboxStore, get_outbox_store
from wapsi.recovery.state_machine import RecoveryState
from wapsi.recovery.timeline import RecoveryTimelineStore, get_timeline_store
from wapsi.recovery.webhook_processor import (
    DurableWebhookEventProcessor,
    DurableWebhookInbox,
    get_durable_webhook_processor,
    set_durable_webhook_processor,
)


TEST_META_SECRET = "p6_test_meta_app_secret_963047183124334"
TEST_VERIFY_TOKEN = "p6_test_verify_token_2026"
TEST_WABA_ID = "969727602419694"
TEST_PHONE_ID = "1407090562487899"


def sign_raw_bytes(body: bytes, secret: str = TEST_META_SECRET) -> str:
    """Computes exact X-Hub-Signature-256 header over raw bytes."""
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def make_whatsapp_payload(statuses=None, messages=None, waba_id=TEST_WABA_ID, phone_id=TEST_PHONE_ID):
    """Builds valid Meta WhatsApp webhook payload matching WAPSI test configuration."""
    value = {
        "messaging_product": "whatsapp",
        "metadata": {
            "display_phone_number": "15552148539",
            "phone_number_id": phone_id,
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
                "id": waba_id,
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
def setup_isolated_phase6_test_environment(tmp_path, monkeypatch):
    """
    Sets up isolated test environment:
    - Explicit development environment (wapsi_env = 'development')
    - Test credentials for Meta WABA and Phone ID
    - Isolated temporary SQLite databases for inbox, outbox, opt_outs, and timeline
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "wapsi_env", "development")
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr(TEST_META_SECRET))
    monkeypatch.setattr(settings, "whatsapp_webhook_verify_token", SecretStr(TEST_VERIFY_TOKEN))
    monkeypatch.setattr(settings, "whatsapp_business_account_id", TEST_WABA_ID)
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", TEST_PHONE_ID)
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

    orch = get_recovery_orchestrator()
    orch._cases.clear()
    orch._message_to_case.clear()
    orch._link_to_case.clear()
    orch._processed_events.clear()

    opt_mgr = get_opt_out_manager()
    opt_mgr.clear()

    yield {
        "processor": processor,
        "inbox": inbox,
        "opt_out_store": opt_out_store,
        "outbox_store": outbox_store,
        "timeline_store": timeline_store,
        "orchestrator": orch,
        "client": TestClient(app),
    }

    set_durable_webhook_processor(None)
    set_persistent_opt_out_store(None)


# -------------------------------------------------------------------------
# 1. Webhook Signature Verification Tests
# -------------------------------------------------------------------------

def test_correct_signature_accepted_development_mode(setup_isolated_phase6_test_environment):
    """Correct HMAC-SHA256 signature is accepted with HTTP 200 in development mode."""
    client = setup_isolated_phase6_test_environment["client"]
    payload = make_whatsapp_payload(messages=[
        {
            "id": "wamid.TEST_VALID_01",
            "from": "916260055671",
            "timestamp": str(int(time.time())),
            "type": "text",
            "text": {"body": "Hii"},
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_raw_bytes(raw_bytes, TEST_META_SECRET)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "received"
    assert res.json()["messages_processed"] == 1


def test_incorrect_signature_rejected_with_401(setup_isolated_phase6_test_environment):
    """Incorrect signature header is rejected with HTTP 401."""
    client = setup_isolated_phase6_test_environment["client"]
    payload = make_whatsapp_payload(messages=[{"id": "wamid.TAMPER", "from": "916260055671", "type": "text", "text": {"body": "Hii"}}])
    raw_bytes = json.dumps(payload).encode("utf-8")

    # Deliberately bad signature hash
    bad_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"
    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": bad_sig},
    )
    assert res.status_code == 401
    assert "cryptographic verification failed" in res.json()["detail"].lower()


def test_missing_signature_rejected_with_401(setup_isolated_phase6_test_environment):
    """Missing X-Hub-Signature-256 header is rejected with HTTP 401 in development mode."""
    client = setup_isolated_phase6_test_environment["client"]
    payload = make_whatsapp_payload(messages=[{"id": "wamid.NO_SIG", "from": "916260055671", "type": "text", "text": {"body": "Hii"}}])
    raw_bytes = json.dumps(payload).encode("utf-8")

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 401
    assert "Missing X-Hub-Signature-256 header" in res.json()["detail"]


def test_malformed_signature_rejected_with_401(setup_isolated_phase6_test_environment):
    """Malformed signature header (missing sha256= prefix or empty hash) returns HTTP 401."""
    client = setup_isolated_phase6_test_environment["client"]
    payload = make_whatsapp_payload(messages=[{"id": "wamid.MALFORMED", "from": "916260055671", "type": "text", "text": {"body": "Hii"}}])
    raw_bytes = json.dumps(payload).encode("utf-8")

    # Missing prefix
    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "abcdef1234567890"},
    )
    assert res.status_code == 401
    assert "Malformed X-Hub-Signature-256 header" in res.json()["detail"]

    # Empty hash
    res2 = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256="},
    )
    assert res2.status_code == 401


def test_missing_app_secret_fails_closed_in_development(setup_isolated_phase6_test_environment, monkeypatch):
    """When META_APP_SECRET is not configured in development mode, requests fail closed with HTTP 500."""
    client = setup_isolated_phase6_test_environment["client"]
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_secret", None)

    payload = make_whatsapp_payload(messages=[{"id": "wamid.NO_SECRET", "from": "916260055671", "type": "text", "text": {"body": "Hii"}}])
    raw_bytes = json.dumps(payload).encode("utf-8")

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=somehash"},
    )
    assert res.status_code == 500
    assert "Configuration error" in res.json()["detail"]


def test_raw_bytes_used_without_json_reserialization(setup_isolated_phase6_test_environment):
    """
    Signature must be verified directly against raw bytes as transmitted over the wire.
    Whitespace differences between raw bytes and reserialized JSON would fail if reserialized.
    """
    client = setup_isolated_phase6_test_environment["client"]
    # Intentional unconventional spacing in raw JSON
    raw_bytes = (
        b'{\n  "object":   "whatsapp_business_account"  ,\n'
        b'  "entry": [\n    {\n      "id": "' + TEST_WABA_ID.encode() + b'",\n'
        b'      "changes": [\n        {\n'
        b'          "field": "messages",\n'
        b'          "value": {\n'
        b'            "messaging_product": "whatsapp",\n'
        b'            "metadata": {"display_phone_number": "15552148539", "phone_number_id": "' + TEST_PHONE_ID.encode() + b'"},\n'
        b'            "messages": [{"id": "wamid.RAW_BYTES_TEST", "from": "916260055671", "type": "text", "text": {"body": "Test Raw"}}]\n'
        b'          }\n'
        b'        }\n      ]\n    }\n  ]\n}'
    )
    sig = sign_raw_bytes(raw_bytes, TEST_META_SECRET)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200
    assert res.json()["messages_processed"] == 1


def test_waba_and_phone_number_id_validation_rejects_mismatch(setup_isolated_phase6_test_environment):
    """Webhook with unexpected WABA ID or Phone Number ID is rejected with HTTP 400."""
    client = setup_isolated_phase6_test_environment["client"]

    # Wrong WABA ID
    payload_bad_waba = make_whatsapp_payload(
        messages=[{"id": "wamid.BAD_WABA", "from": "916260055671", "type": "text", "text": {"body": "Hii"}}],
        waba_id="wrong_waba_id_000",
    )
    raw_bad_waba = json.dumps(payload_bad_waba).encode("utf-8")
    sig_bad_waba = sign_raw_bytes(raw_bad_waba, TEST_META_SECRET)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bad_waba,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig_bad_waba},
    )
    assert res.status_code == 400
    assert "Invalid WhatsApp Business Account ID" in res.json()["detail"]

    # Wrong Phone Number ID
    payload_bad_phone = make_whatsapp_payload(
        messages=[{"id": "wamid.BAD_PHONE", "from": "916260055671", "type": "text", "text": {"body": "Hii"}}],
        phone_id="wrong_phone_id_000",
    )
    raw_bad_phone = json.dumps(payload_bad_phone).encode("utf-8")
    sig_bad_phone = sign_raw_bytes(raw_bad_phone, TEST_META_SECRET)

    res2 = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bad_phone,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig_bad_phone},
    )
    assert res2.status_code == 400
    assert "Invalid WhatsApp Phone Number ID" in res2.json()["detail"]


# -------------------------------------------------------------------------
# 2. Durable Persistence and Idempotency Tests
# -------------------------------------------------------------------------

def test_genuine_inbound_persists_in_webhook_inbox_and_interactions(setup_isolated_phase6_test_environment):
    """
    Genuine inbound message:
    1. Persists event in webhook_inbox.
    2. Persists interaction in customer_interactions and unlocks 24h window.
    3. Returns HTTP 200 with messages_processed=1.
    """
    env = setup_isolated_phase6_test_environment
    client = env["client"]
    inbox = env["inbox"]
    opt_out_store = env["opt_out_store"]

    target_wamid = "wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBQjRBNEU4NTk3NEI2RjVFMjQ1Njc4QTVDNzg5QjQA"
    phone = "916260055671"
    event_ts = 1793637318

    payload = make_whatsapp_payload(messages=[
        {
            "id": target_wamid,
            "from": phone,
            "timestamp": str(event_ts),
            "type": "text",
            "text": {"body": "Hii"},
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_raw_bytes(raw_bytes, TEST_META_SECRET)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200
    assert res.json()["messages_processed"] == 1
    assert res.json()["messages_duplicate"] == 0

    # 1. Verify persistence in webhook_inbox
    composite_event_id = f"inbound_{target_wamid}"
    with inbox._get_sqlite_connection() as conn:
        row = conn.execute("SELECT * FROM webhook_inbox WHERE event_id = ?", (composite_event_id,)).fetchone()
        assert row is not None
        assert row["status"] == "PROCESSED"
        assert row["provider"] == "whatsapp_meta"

    # 2. Verify 24h customer window unlocked
    assert opt_out_store.is_within_24h_window(phone, current_time=event_ts + 3600) is True
    assert opt_out_store.is_within_24h_window(phone, current_time=event_ts + 86401) is False


def test_customer_interaction_persisted_exactly_once(setup_isolated_phase6_test_environment):
    """Repeated interactions from the same customer update timestamp without duplicating records."""
    env = setup_isolated_phase6_test_environment
    client = env["client"]
    opt_out_store = env["opt_out_store"]

    phone = "916260055671"
    t1 = 1793637318
    t2 = t1 + 600

    for idx, (wamid, ts) in enumerate([("wamid.MSG_A", t1), ("wamid.MSG_B", t2)]):
        payload = make_whatsapp_payload(messages=[
            {"id": wamid, "from": phone, "timestamp": str(ts), "type": "text", "text": {"body": f"Msg {idx}"}}
        ])
        raw_bytes = json.dumps(payload).encode("utf-8")
        sig = sign_raw_bytes(raw_bytes, TEST_META_SECRET)
        res = client.post(
            "/api/v1/webhooks/whatsapp",
            content=raw_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        assert res.status_code == 200

    # Verify only 1 customer interaction record exists for phone in SQLite
    with opt_out_store._get_sqlite_connection() as conn:
        rows = conn.execute("SELECT count(*) FROM customer_interactions WHERE phone = ?", (phone,)).fetchone()
        assert rows[0] == 1
        last_ts = conn.execute("SELECT last_interaction_at FROM customer_interactions WHERE phone = ?", (phone,)).fetchone()[0]
        assert float(last_ts) == float(t2)


def test_duplicate_wamid_is_deduplicated(setup_isolated_phase6_test_environment):
    """Duplicate webhook redelivery of the same wamid returns DUPLICATE_IGNORED."""
    client = setup_isolated_phase6_test_environment["client"]

    wamid = "wamid.DEDUP_TEST_001"
    payload = make_whatsapp_payload(messages=[
        {"id": wamid, "from": "916260055671", "timestamp": str(int(time.time())), "type": "text", "text": {"body": "First"}}
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_raw_bytes(raw_bytes, TEST_META_SECRET)

    # First delivery
    res1 = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res1.status_code == 200
    assert res1.json()["messages_processed"] == 1
    assert res1.json()["messages_duplicate"] == 0

    # Second delivery
    res2 = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res2.status_code == 200
    assert res2.json()["messages_processed"] == 0
    assert res2.json()["messages_duplicate"] == 1


def test_database_failure_returns_retryable_500_not_false_success(setup_isolated_phase6_test_environment, monkeypatch):
    """If database persistence fails, endpoint returns retryable HTTP 500, never a false success."""
    env = setup_isolated_phase6_test_environment
    client = env["client"]
    processor = env["processor"]

    def failing_check_or_record(*args, **kwargs):
        raise RuntimeError("Database connection pool exhausted")

    monkeypatch.setattr(processor.inbox, "check_or_record", failing_check_or_record)

    payload = make_whatsapp_payload(messages=[
        {"id": "wamid.DB_FAIL_TEST", "from": "916260055671", "timestamp": str(int(time.time())), "type": "text", "text": {"body": "Hii"}}
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_raw_bytes(raw_bytes, TEST_META_SECRET)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 500
    assert "Durable webhook processing failed" in res.json()["detail"]


# -------------------------------------------------------------------------
# 3. Outbox Authorization Safety Verification
# -------------------------------------------------------------------------

def test_no_inbound_message_automatically_approves_outbox_job(setup_isolated_phase6_test_environment):
    """
    Receiving an inbound message (even from the case's customer or with 'approve' text)
    must NEVER transition an outbox job out of PENDING_APPROVAL or set approved_by_operator_id.
    """
    env = setup_isolated_phase6_test_environment
    client = env["client"]
    outbox = env["outbox_store"]

    case_id = "wapsi_case_phase6_safety_check"
    customer_phone = "916260055671"

    # Enqueue a job requiring explicit operator approval
    job = outbox.enqueue(
        case_id=case_id,
        payment_id="pay_test_01",
        idempotency_key="idemp_test_01",
        action="whatsapp_recovery_nudge",
        channel="whatsapp",
        recipient_masked="+91 62600 55671",
        message_payload={"payment_link": "https://rzp.io/i/test"},
        delay_seconds=0,
        status="PENDING_APPROVAL",
        requires_operator_approval=True,
    )
    # Explicitly set status to PENDING_APPROVAL
    with outbox._get_sqlite_connection() as conn:
        conn.execute(
            "UPDATE recovery_outbox SET status = 'PENDING_APPROVAL', requires_operator_approval = 1 WHERE id = ?",
            (job.id,),
        )
        conn.commit()

    initial_job = outbox.get_job(job.id)
    assert initial_job.status == "PENDING_APPROVAL"
    assert initial_job.worker_id is None

    # Customer sends incoming message
    payload = make_whatsapp_payload(messages=[
        {
            "id": "wamid.SAFETY_CHECK_01",
            "from": customer_phone,
            "timestamp": str(int(time.time())),
            "type": "text",
            "text": {"body": "YES please proceed with recovery"},
        }
    ])
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_raw_bytes(raw_bytes, TEST_META_SECRET)

    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res.status_code == 200

    # Inspect outbox job after inbound webhook processing
    post_job = outbox.get_job(job.id)
    assert post_job is not None
    assert post_job.status == "PENDING_APPROVAL", "Job must strictly remain PENDING_APPROVAL"
    assert post_job.worker_id is None, "Worker ID must remain None"
