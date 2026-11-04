"""
Tests for Phase 3: Dedicated Razorpay Webhook Compatibility & Hardening.
Validates all 12 criteria from Section 5:
1. Valid raw-body signature.
2. Invalid signature (401).
3. Modified raw request body (401).
4. Missing signature header (401).
5. Malformed JSON after valid signature validation (400).
6. Valid payment_link.paid event structure (200).
7. Valid payment.captured event structure (200).
8. Duplicate event ID (duplicate_ignored).
9. Missing event ID header (gracefully handled via payload/hash).
10. Out-of-order event handling (preserves RECOVERED state).
11. Invalid amount or currency handling.
12. Mismatched payment-link identifier handling.
13. Backward-compatibility of internal /api/v1/webhook.
14. Verification of WhatsApp webhooks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from pydantic import SecretStr
from wapsi.api.app import app
from wapsi.core.config import WapsiSettings, get_settings
from wapsi.integrations.orchestration.recovery_orchestrator import (
    RecoveryDispatchReceipt,
    get_recovery_orchestrator,
)
from wapsi.integrations.razorpay.webhook import RazorpayWebhookEvent, RazorpayWebhookHandler

TEST_WEBHOOK_SECRET = "test_rzp_webhook_secret_gate_2026"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """TestClient with monkeypatched test webhook secret."""
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "razorpay_webhook_secret",
        SecretStr(TEST_WEBHOOK_SECRET),
    )
    monkeypatch.setattr(
        WapsiSettings,
        "get_webhook_secret_bytes",
        lambda self: TEST_WEBHOOK_SECRET.encode("utf-8"),
    )
    return TestClient(app)


def compute_signature(raw_body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


# ==============================================================================
# 1. Valid Raw-Body Signature
# ==============================================================================

def test_razorpay_webhook_valid_signature(client: TestClient):
    payload = {
        "entity": "event",
        "account_id": "acc_test_gate_1",
        "event": "payment_link.paid",
        "contains": ["payment_link", "payment"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_gate_valid_01",
                    "amount": 1000,
                    "amount_paid": 1000,
                    "currency": "INR",
                    "status": "paid",
                    "notes": {"case_id": "REC-GATE-01"},
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_gate_valid_01",
                    "amount": 1000,
                    "currency": "INR",
                    "status": "captured",
                }
            },
        },
        "created_at": int(time.time()),
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)

    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": f"evt_{int(time.time()*1000)}_01",
        "Content-Type": "application/json",
    }
    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "received"
    assert data["event"] == "payment_link.paid"
    assert data["signature_verified"] is True
    assert data["idempotency_status"] == "processed"
    assert data["payment_link_id"] == "plink_gate_valid_01"
    assert data["payment_id"] == "pay_gate_valid_01"


# ==============================================================================
# 2. Invalid Signature
# ==============================================================================

def test_razorpay_webhook_invalid_signature(client: TestClient):
    raw_body = b'{"entity": "event", "event": "payment.captured"}'
    headers = {
        "X-Razorpay-Signature": "invalid_hex_digest_00000000000000000000000000000000",
        "Content-Type": "application/json",
    }
    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 401
    assert "Invalid X-Razorpay-Signature" in res.json()["detail"]


# ==============================================================================
# 3. Modified Raw Request Body
# ==============================================================================

def test_razorpay_webhook_modified_raw_body(client: TestClient):
    original_body = b'{"entity": "event", "event": "payment.captured", "amount": 1000}'
    sig = compute_signature(original_body)

    # Tamper with the body
    tampered_body = b'{"entity": "event", "event": "payment.captured", "amount": 9999}'

    headers = {
        "X-Razorpay-Signature": sig,
        "Content-Type": "application/json",
    }
    res = client.post("/api/v1/webhooks/razorpay", content=tampered_body, headers=headers)
    assert res.status_code == 401
    assert "Invalid X-Razorpay-Signature" in res.json()["detail"]


# ==============================================================================
# 4. Missing Signature Header
# ==============================================================================

def test_razorpay_webhook_missing_signature_header(client: TestClient):
    raw_body = b'{"entity": "event", "event": "payment.captured"}'
    res = client.post("/api/v1/webhooks/razorpay", content=raw_body)
    assert res.status_code == 401
    assert "Missing X-Razorpay-Signature" in res.json()["detail"]


# ==============================================================================
# 5. Malformed JSON After Valid Signature Validation
# ==============================================================================

def test_razorpay_webhook_malformed_json_after_valid_signature(client: TestClient):
    malformed_raw = b"This is completely invalid non-JSON body payload!"
    sig = compute_signature(malformed_raw)

    headers = {
        "X-Razorpay-Signature": sig,
        "Content-Type": "application/json",
    }
    res = client.post("/api/v1/webhooks/razorpay", content=malformed_raw, headers=headers)
    assert res.status_code == 400
    assert "Invalid JSON" in res.json()["detail"]


# ==============================================================================
# 6. Valid payment_link.paid Event Structure
# ==============================================================================

def test_razorpay_webhook_payment_link_paid(client: TestClient):
    payload = {
        "entity": "event",
        "account_id": "acc_merchant_abc",
        "event": "payment_link.paid",
        "contains": ["payment_link"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_only_paid_001",
                    "amount": 1500,
                    "amount_paid": 1500,
                    "currency": "INR",
                    "status": "paid",
                    "notes": {"case_id": "REC-PLINK-ONLY-01"},
                }
            }
        },
        "created_at": 1730460000,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)
    evt_id = f"evt_plink_{int(time.time()*1000)}"

    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": evt_id,
        "Content-Type": "application/json",
    }
    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["event"] == "payment_link.paid"
    assert data["payment_link_id"] == "plink_only_paid_001"
    assert data["idempotency_status"] == "processed"


# ==============================================================================
# 7. Valid payment.captured Event Structure
# ==============================================================================

def test_razorpay_webhook_payment_captured(client: TestClient):
    payload = {
        "entity": "event",
        "account_id": "acc_merchant_abc",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_captured_direct_001",
                    "amount": 1000,
                    "currency": "INR",
                    "status": "captured",
                    "notes": {"case_id": "REC-PAY-ONLY-01"},
                }
            }
        },
        "created_at": 1730460000,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)
    evt_id = f"evt_pay_{int(time.time()*1000)}"

    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": evt_id,
        "Content-Type": "application/json",
    }
    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["event"] == "payment.captured"
    assert data["payment_id"] == "pay_captured_direct_001"


# ==============================================================================
# 8. Duplicate Event ID (Idempotency)
# ==============================================================================

def test_razorpay_webhook_duplicate_event_id(client: TestClient):
    evt_id = f"evt_dedup_test_{int(time.time()*1000)}"
    payload = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment_link.paid",
        "contains": ["payment_link"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_dedup_01",
                    "amount": 1000,
                    "status": "paid",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)

    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": evt_id,
        "Content-Type": "application/json",
    }

    # First delivery: processed
    res1 = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["idempotency_status"] == "processed"

    # Second delivery: duplicate_ignored
    res2 = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["idempotency_status"] == "duplicate_ignored"


# ==============================================================================
# 9. Missing Event ID Header (Graceful Derivation)
# ==============================================================================

def test_razorpay_webhook_missing_event_id_header(client: TestClient):
    payload = {
        "entity": "event",
        "id": "evt_embedded_in_payload_99",
        "account_id": "acc_test",
        "event": "payment_link.paid",
        "contains": ["payment_link"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_no_hdr_01",
                    "amount": 1000,
                    "status": "paid",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)

    # Note: No X-Razorpay-Event-Id header
    headers = {
        "X-Razorpay-Signature": sig,
        "Content-Type": "application/json",
    }
    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["event_id"] == "evt_embedded_in_payload_99"


# ==============================================================================
# 10. Out-of-Order Event Handling
# ==============================================================================

def test_razorpay_webhook_out_of_order_preserves_recovered(client: TestClient):
    orchestrator = get_recovery_orchestrator()
    case_id = f"REC-OOO-{int(time.time())}"

    # Setup case in RECOVERED state
    receipt = RecoveryDispatchReceipt(
        case_id=case_id,
        payment_id=f"pay_{case_id}",
        recipient_phone="+919876543210",
        amount_paise=1000,
        amount_inr=10.0,
        payment_link_id=f"plink_{case_id}",
        payment_link_url=f"https://rzp.io/i/plink_{case_id}",
        whatsapp_message_id=f"wamid_{case_id}",
        status="RECOVERED",
        created_at=time.time(),
        updated_at=time.time(),
    )
    orchestrator._cases[case_id] = receipt
    orchestrator._link_to_case[receipt.payment_link_id] = case_id

    # Simulate delayed payment.failed event arriving for already RECOVERED case
    payload = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": receipt.payment_id,
                    "payment_link_id": receipt.payment_link_id,
                    "status": "failed",
                    "amount": 1000,
                    "notes": {"case_id": case_id},
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)
    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": f"evt_ooo_{int(time.time()*1000)}",
        "Content-Type": "application/json",
    }

    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200

    # Case MUST remain RECOVERED
    assert orchestrator._cases[case_id].status == "RECOVERED"


# ==============================================================================
# 11. Invalid Amount or Currency Handling
# ==============================================================================

def test_razorpay_webhook_invalid_amount_or_currency(client: TestClient):
    payload = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment_link.paid",
        "contains": ["payment_link"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_usd_test_01",
                    "amount": 0,
                    "currency": "USD",
                    "status": "paid",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)
    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": f"evt_usd_{int(time.time()*1000)}",
        "Content-Type": "application/json",
    }

    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "received"


# ==============================================================================
# 12. Mismatched Payment-Link Identifier Handling
# ==============================================================================

def test_razorpay_webhook_mismatched_payment_link_id(client: TestClient):
    payload = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment_link.paid",
        "contains": ["payment_link"],
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_unregistered_xyz_999",
                    "amount": 1000,
                    "status": "paid",
                    "notes": {"case_id": "REC-NONEXISTENT-999"},
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)
    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": f"evt_mismatch_{int(time.time()*1000)}",
        "Content-Type": "application/json",
    }

    res = client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "received"


# ==============================================================================
# 13. Backward-Compatibility of Internal /api/v1/webhook
# ==============================================================================

def test_internal_webhook_endpoint_still_operational(client: TestClient):
    """
    Verifies that the internal /api/v1/webhook route continues to serve
    internal benchmark testing and synthetic WebhookPayloadRequest payloads.
    """
    payload = {
        "event": "payment.recovered",
        "payment_id": f"pay_int_{int(time.time()*1000)}",
        "merchant_id": "merch_default",
        "amount": 1000.0,
        "status": "captured",
        "timestamp": int(time.time()),
        "nonce": f"nonce_int_{int(time.time()*1000)}",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_signature(raw_body)
    headers = {
        "X-Razorpay-Signature": sig,
        "Content-Type": "application/json",
    }

    res = client.post("/api/v1/webhook", content=raw_body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "received"
    assert data["signature_verified"] is True


# ==============================================================================
# 14. WhatsApp Webhook Endpoints Still Operational
# ==============================================================================

def test_whatsapp_webhook_endpoints_still_operational(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """
    Verifies that WhatsApp GET handshake and POST event endpoints remain intact.
    """
    # 1. GET Handshake
    res_get = client.get("/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.challenge=11559955&hub.verify_token=wrong")
    assert res_get.status_code == 403

    # 2. POST Delivery event (signed with configured meta_app_secret)
    import hmac
    import hashlib
    from pydantic import SecretStr

    test_secret = "test_meta_webhook_secret_key"
    monkeypatch.setattr(get_settings(), "meta_app_secret", SecretStr(test_secret))
    test_waba_id = get_settings().whatsapp_business_account_id or "969727602419694"
    test_phone_id = get_settings().whatsapp_phone_number_id or "1407090562487899"
    wa_body = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": test_waba_id,
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "123", "phone_number_id": test_phone_id},
                            "statuses": [
                                {
                                    "id": f"wamid_test_{int(time.time()*1000)}",
                                    "status": "delivered",
                                    "timestamp": str(int(time.time())),
                                    "recipient_id": "919876543210",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(wa_body).encode("utf-8")
    sig = hmac.new(test_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    res_post = client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert res_post.status_code == 200
    assert res_post.json()["status"] == "received"