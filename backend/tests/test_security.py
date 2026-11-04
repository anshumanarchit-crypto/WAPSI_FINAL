"""
Unit tests for Security, Audit Ledger integrity, TEE Boundary, and Webhook validation.
"""

import pytest
import hmac
import hashlib
from wapsi.security.audit_ledger import AuditLedger
from wapsi.security.tee_boundary import TEEEnclaveBoundary
from wapsi.security.validation import WebhookValidator, InMemoryRateLimiter


def test_audit_ledger_hash_chain_integrity():
    ledger = AuditLedger()
    
    b1 = ledger.append("TEST_EVENT_1", {"order_id": "123", "amount": 500})
    b2 = ledger.append("TEST_EVENT_2", {"order_id": "456", "status": "APPROVED"})
    
    assert b2.prev_hash == b1.block_hash
    
    integrity = ledger.verify_integrity()
    assert integrity["is_valid"] is True
    assert integrity["total_blocks"] == 3  # Genesis + 2 events


def test_audit_ledger_detects_tampering():
    ledger = AuditLedger()
    b1 = ledger.append("TEST_EVENT_1", {"amount": 500})
    ledger.append("TEST_EVENT_2", {"amount": 1000})

    # Tamper with block 1 payload
    b1.data["amount"] = 999999

    integrity = ledger.verify_integrity()
    assert integrity["is_valid"] is False
    assert "Tampered data" in integrity["error"]


def test_tee_boundary_pii_shielding():
    tee = TEEEnclaveBoundary()
    raw_event = {
        "user_id": "usr_99182312",
        "payment_id": "pay_987654321",
        "amount_in_inr": 2499.0
    }

    shielded, sanitized = tee.sanitize_and_shield_pii(raw_event)

    # Internal shielded has full data
    assert shielded["user_id"] == "usr_99182312"
    # Sanitized external has masked data
    assert "***" in sanitized["user_id"]
    assert "***" in sanitized["payment_id"]

    attestation = tee.generate_attestation_report()
    assert attestation["is_hardware_tee"] is False
    assert "attestation_signature" in attestation


def test_webhook_hmac_verification():
    secret = "rzp_webhook_secret_dev_demo"
    payload = b'{"event":"payment.recovered","payment_id":"pay_123"}'
    
    valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert WebhookValidator.verify_signature(payload, valid_sig, secret) is True
    assert WebhookValidator.verify_signature(payload, "invalid_signature", secret) is False
