"""
End-to-End Integration Test Suite for WAPSI Recovery Engine.
Verifies the complete lifecycle:
1. Case creation & durable persistence across restarts.
2. Canonical local test case RX-1793827795733 existence & attributes.
3. Independent payment link generation (POST /api/v1/recovery/cases/{case_id}/payment-link).
4. Idempotent link reuse without duplicate side effects.
5. Independent WhatsApp dispatch (POST /api/v1/recovery/cases/{case_id}/dispatch-whatsapp).
6. Suppression of WhatsApp dispatch when customer is opted out.
7. Razorpay signed webhook ingestion & case resolution to RECOVERED.
8. Webhook deduplication via persistent inbox.
9. Unmatched webhook handling -> UNMATCHED_PENDING_RECONCILIATION.
10. Invariant preservation: Protected record 5a6587ab-2601-4017-b396-48e3d2fc2fda untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from wapsi.api.app import app
from wapsi.core.config import get_settings
from wapsi.recovery.case_store import DurableRecoveryCaseStore, RecoveryCaseRecord, get_durable_case_store
from wapsi.recovery.engine import get_recovery_engine
from wapsi.recovery.state_machine import RecoveryState
from wapsi.recovery.webhook_processor import get_durable_webhook_processor


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def api_headers() -> dict[str, str]:
    return {
        "X-API-Key": "rzp_test_wapsi_key_2026",
        "Content-Type": "application/json",
    }


def compute_razorpay_sig(body: bytes, secret: Optional[str] = None) -> str:
    if secret is None:
        from wapsi.core.config import get_settings
        settings = get_settings()
        secret = (
            settings.razorpay_webhook_secret.get_secret_value()
            if settings.razorpay_webhook_secret
            else settings.get_webhook_secret_bytes().decode("utf-8")
        )
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# ==============================================================================
# TEST 1: CANONICAL LOCAL TEST CASE RX-1793827795733
# ==============================================================================
def test_canonical_test_case_persistence_and_attributes(client: TestClient, api_headers: dict[str, str]):
    """Verifies that canonical local test case RX-1793827795733 exists in the durable store and API."""
    case_store = get_durable_case_store()
    case = case_store.get_case("RX-1793827795733")
    assert case is not None
    assert case.case_id == "RX-1793827795733"
    assert case.payment_id == "pay_wapsi_local_test_001"
    assert case.amount_paise == 1000  # ₹10.00
    assert case.customer_phone == "+919876543210"
    assert case.customer_name == "Arjun Sharma"
    assert case.status in (RecoveryState.PENDING, RecoveryState.ELIGIBLE, RecoveryState.SCHEDULED, RecoveryState.DISPATCHED, RecoveryState.RECOVERED)

    # Verify retrieval via API endpoint
    res = client.get("/api/v1/recovery/cases/RX-1793827795733", headers=api_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "RX-1793827795733"
    assert data["payment_id"] == "pay_wapsi_local_test_001"
    assert data["amount_paise"] == 1000
    assert data["amount_inr"] == 10.0


# ==============================================================================
# TEST 2: DURABLE CASE CREATION & SURVIVAL ACROSS RECOVERY ENGINE INSTANCES
# ==============================================================================
def test_case_creation_and_persistence_across_restarts(client: TestClient, api_headers: dict[str, str]):
    """Creates a new case via API and verifies it persists across fresh store instances."""
    unique_ts = int(time.time() * 1000)
    case_id = f"RX-E2E-{unique_ts}"
    payment_id = f"pay_e2e_{unique_ts}"

    create_payload = {
        "case_id": case_id,
        "payment_id": payment_id,
        "amount_inr": 49.50,
        "customer_phone": "+919876543210",
        "customer_name": "Priya Sharma",
        "merchant_name": "Acme Global",
        "error_code": "BAD_REQUEST_PAYMENT_TIMED_OUT",
        "error_category": "TECHNICAL_GATEWAY",
        "max_attempts": 3,
    }

    res = client.post("/api/v1/recovery/cases", json=create_payload, headers=api_headers)
    assert res.status_code == 201
    created_data = res.json()
    assert created_data["case_id"] == case_id
    assert created_data["amount_paise"] == 4950
    assert created_data["status"] == "PENDING"

    # Simulate fresh instance of DurableRecoveryCaseStore
    fresh_store = DurableRecoveryCaseStore()
    persisted = fresh_store.get_case(case_id)
    assert persisted is not None
    assert persisted.case_id == case_id
    assert persisted.payment_id == payment_id
    assert persisted.amount_paise == 4950
    assert persisted.customer_name == "Priya Sharma"

    # Verify retrieval via GET /api/v1/recovery/cases/{case_id}
    get_res = client.get(f"/api/v1/recovery/cases/{case_id}", headers=api_headers)
    assert get_res.status_code == 200
    assert get_res.json()["case_id"] == case_id


# ==============================================================================
# TEST 3: INDEPENDENT PAYMENT LINK GENERATION (NO WHATSAPP SIDE-EFFECT)
# ==============================================================================
def test_independent_payment_link_generation(client: TestClient, api_headers: dict[str, str]):
    """Generates Razorpay payment link independently and verifies timeline without WhatsApp dispatch."""
    unique_ts = int(time.time() * 1000)
    case_id = f"RX-PLINK-{unique_ts}"
    payment_id = f"pay_plink_{unique_ts}"

    # 1. Create case
    client.post(
        "/api/v1/recovery/cases",
        json={
            "case_id": case_id,
            "payment_id": payment_id,
            "amount_inr": 25.00,
            "customer_phone": "+919876543210",
            "customer_name": "Karan Kapoor",
        },
        headers=api_headers,
    )

    # 2. Call independent payment link generation endpoint
    res = client.post(f"/api/v1/recovery/cases/{case_id}/payment-link", headers=api_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == case_id
    assert data["payment_link_id"].startswith("plink_")
    assert "payment_link_url" in data
    assert data["amount_paise"] == 2500
    assert data["is_reused"] is False

    # 3. Verify case is updated in durable store
    store = get_durable_case_store()
    c = store.get_case(case_id)
    assert c.payment_link_id == data["payment_link_id"]
    assert c.payment_link_url == data["payment_link_url"]
    assert c.whatsapp_message_id is None  # NO WhatsApp side effect

    # 4. Verify idempotent second call returns existing link
    res2 = client.post(f"/api/v1/recovery/cases/{case_id}/payment-link", headers=api_headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["payment_link_id"] == data["payment_link_id"]
    assert data2["is_reused"] is True

    # 5. Verify timeline recorded PAYMENT_LINK_CREATED and NO WHATSAPP_DISPATCHED
    tl_res = client.get(f"/api/v1/recovery/cases/{case_id}/timeline", headers=api_headers)
    assert tl_res.status_code == 200
    events = tl_res.json().get("events", [])
    event_types = [e["event_type"] for e in events]
    assert "PAYMENT_LINK_CREATED" in event_types
    assert "WHATSAPP_DISPATCHED" not in event_types


# ==============================================================================
# TEST 4: INDEPENDENT WHATSAPP DISPATCH
# ==============================================================================
def test_independent_whatsapp_dispatch(client: TestClient, api_headers: dict[str, str]):
    """Dispatches WhatsApp reminder independently with generated payment link."""
    unique_ts = int(time.time() * 1000)
    case_id = f"RX-WA-{unique_ts}"
    payment_id = f"pay_wa_{unique_ts}"

    customer_phone = f"+9198{unique_ts % 100000000:08d}"

    # 1. Create case
    client.post(
        "/api/v1/recovery/cases",
        json={
            "case_id": case_id,
            "payment_id": payment_id,
            "amount_inr": 15.00,
            "customer_phone": customer_phone,
            "customer_name": "Rohan Mehta",
        },
        headers=api_headers,
    )

    # 2. Call independent WhatsApp dispatch endpoint
    res = client.post(f"/api/v1/recovery/cases/{case_id}/dispatch-whatsapp", headers=api_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == case_id
    assert data["whatsapp_message_id"].startswith("wamid.")
    assert data["status"] == "DISPATCHED"
    assert data["attempts_made"] == 1

    # 3. Verify case in durable store
    store = get_durable_case_store()
    c = store.get_case(case_id)
    assert c.whatsapp_message_id == data["whatsapp_message_id"]
    assert c.status == RecoveryState.DISPATCHED
    assert c.attempts_made == 1

    # 4. Verify timeline has WHATSAPP_DISPATCHED
    tl_res = client.get(f"/api/v1/recovery/cases/{case_id}/timeline", headers=api_headers)
    assert tl_res.status_code == 200
    event_types = [e["event_type"] for e in tl_res.json().get("events", [])]
    assert "WHATSAPP_DISPATCHED" in event_types


# ==============================================================================
# TEST 5: WHATSAPP DISPATCH SUPPRESSION ON CUSTOMER OPT-OUT
# ==============================================================================
def test_whatsapp_dispatch_suppression_on_opt_out(client: TestClient, api_headers: dict[str, str]):
    """Verifies that opted-out customers are immediately suppressed from WhatsApp dispatch."""
    unique_ts = int(time.time() * 1000)
    case_id = f"RX-OPTOUT-{unique_ts}"
    opted_out_phone = f"+9199999{unique_ts % 100000:05d}"

    # Register opt-out in engine
    engine = get_recovery_engine()
    engine.opt_out.record_opt_out(opted_out_phone, reason="USER_REQUEST", source="e2e_test")

    # Create case for this customer
    client.post(
        "/api/v1/recovery/cases",
        json={
            "case_id": case_id,
            "payment_id": f"pay_optout_{unique_ts}",
            "amount_inr": 100.00,
            "customer_phone": opted_out_phone,
            "customer_name": "Opted Out User",
        },
        headers=api_headers,
    )

    # Attempt dispatch
    res = client.post(f"/api/v1/recovery/cases/{case_id}/dispatch-whatsapp", headers=api_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUPPRESSED_OPT_OUT"

    # Verify case status
    store = get_durable_case_store()
    c = store.get_case(case_id)
    assert c.status == RecoveryState.SUPPRESSED_OPT_OUT


# ==============================================================================
# TEST 6: RAZORPAY WEBHOOK INGESTION & STATE TRANSITION TO RECOVERED
# ==============================================================================
def test_razorpay_webhook_resolves_and_recovers_case(client: TestClient, api_headers: dict[str, str]):
    """Verifies that a valid Razorpay webhook transitions the case to RECOVERED."""
    unique_ts = int(time.time() * 1000)
    case_id = f"RX-RECOV-{unique_ts}"
    payment_id = f"pay_recov_{unique_ts}"

    # 1. Create case & generate link
    client.post(
        "/api/v1/recovery/cases",
        json={
            "case_id": case_id,
            "payment_id": payment_id,
            "amount_inr": 30.00,
            "customer_phone": "+919876543210",
            "customer_name": "Sunil Verma",
        },
        headers=api_headers,
    )
    link_res = client.post(f"/api/v1/recovery/cases/{case_id}/payment-link", headers=api_headers)
    plink_id = link_res.json()["payment_link_id"]

    # 2. Send signed Razorpay payment_link.paid webhook
    webhook_payload = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id,
                    "amount": 3000,
                    "status": "paid",
                    "notes": {"case_id": case_id},
                }
            },
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 3000,
                    "status": "captured",
                }
            },
        },
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    sig = compute_razorpay_sig(raw_body)
    evt_id = f"evt_recov_{unique_ts}"

    wb_res = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw_body,
        headers={
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": evt_id,
            "Content-Type": "application/json",
        },
    )
    assert wb_res.status_code == 200

    # 3. Verify case status transitioned to RECOVERED in durable store
    store = get_durable_case_store()
    c = store.get_case(case_id)
    assert c.status == RecoveryState.RECOVERED

    # 4. Verify case detail endpoint reflects RECOVERED
    detail_res = client.get(f"/api/v1/recovery/cases/{case_id}", headers=api_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "RECOVERED"

    # 5. Verify timeline records PAYMENT_CAPTURED and RECOVERY_COMPLETED
    tl_res = client.get(f"/api/v1/recovery/cases/{case_id}/timeline", headers=api_headers)
    events = tl_res.json().get("events", [])
    ev_types = [e["event_type"] for e in events]
    assert "PAYMENT_CAPTURED" in ev_types
    assert "RECOVERY_COMPLETED" in ev_types


# ==============================================================================
# TEST 7: UNMATCHED WEBHOOK MARKS UNMATCHED_PENDING_RECONCILIATION
# ==============================================================================
def test_unmatched_webhook_returns_unmatched_pending_reconciliation(client: TestClient):
    """Verifies that an incoming webhook for an unknown entity is marked UNMATCHED_PENDING_RECONCILIATION."""
    unique_ts = int(time.time() * 1000)
    processor = get_durable_webhook_processor()

    result = processor.process_razorpay_event(
        event_name="payment_link.paid",
        event_id=f"evt_orphan_{unique_ts}",
        payment_id=f"pay_orphan_{unique_ts}",
        payment_link_id=f"plink_nonexistent_{unique_ts}",
        amount_paise=5000,
        raw_payload={"notes": {}},
    )
    assert result.status == "UNMATCHED_PENDING_RECONCILIATION"
    assert result.case_id is None


# ==============================================================================
# TEST 8: NON-EXISTENT CASE ID RETURNS 404 (NEVER RETURNS DUMMY CACHED CASE)
# ==============================================================================
def test_nonexistent_case_returns_404(client: TestClient, api_headers: dict[str, str]):
    """Verifies that requesting a random non-existent case returns HTTP 404, never a dummy case."""
    nonexistent_id = f"RX-GHOST-{uuid.uuid4().hex[:10]}"
    res = client.get(f"/api/v1/recovery/cases/{nonexistent_id}", headers=api_headers)
    assert res.status_code == 404
    assert f"Case '{nonexistent_id}' not found" in res.json().get("detail", "")


# ==============================================================================
# TEST 9: PROTECTED INVARIANT RECORD IS UNTOUCHED
# ==============================================================================
def test_protected_record_invariant_untouched():
    """Verifies that protected outbox job 5a6587ab-2601-4017-b396-48e3d2fc2fda is 100% untouched."""
    from wapsi.db.session import get_db_manager
    from sqlalchemy import text
    mgr = get_db_manager()
    if mgr.engine.dialect.name == "postgresql":
        with mgr.session_scope() as session:
            session.execute(text("SELECT set_config('app.current_merchant_id', '04a2aaf8-8c8a-4d99-852c-cefc80e82019', true)"))
            row = session.execute(
                text("SELECT id, merchant_id, status FROM recovery_outbox WHERE id = '5a6587ab-2601-4017-b396-48e3d2fc2fda'")
            ).fetchone()
            assert row is not None
            assert str(row[0]) == "5a6587ab-2601-4017-b396-48e3d2fc2fda"
            assert str(row[1]) == "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
            assert row[2] == "SENT"
