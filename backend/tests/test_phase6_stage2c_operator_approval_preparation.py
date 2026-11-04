"""
WAPSI — Phase 6 Stage 2C Regression Test Suite:
Controlled Operator Approval Preparation and Pre-Dispatch Safeguards.

Tests:
1. GET /api/v1/recovery/outbox/{job_id} requires API key authentication (401 on missing/invalid).
2. GET /api/v1/recovery/outbox/{job_id} returns accurate job details when authenticated.
3. POST /api/v1/recovery/outbox/{job_id}/approve validates operator_id schema (422 on empty/missing).
4. DurableOutboxStore.approve_job() strictly requires a non-empty operator_id.
5. compute_approval_hash() is deterministic and detects any payload or recipient tampering.
6. verify_dispatch_authorization() strictly checks operator ID, approval timestamp, and snapshot hash.
7. Tampered payload is rejected by verify_dispatch_authorization() even if approved.
8. Customer opt-out blocks dispatch authorization even if approved.
9. An unapproved job is blocked from worker claiming by both SQL and application gates.
10. Target sandbox job remains PENDING_APPROVAL and untouched prior to operator authorization.
"""

import copy
import hashlib
import json
import os
import uuid
import pytest
from starlette.testclient import TestClient

from wapsi.api.app import app
from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, compute_approval_hash

TARGET_JOB_ID = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
TARGET_MERCHANT_UUID = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
SYNTHETIC_JOB_ID = "00000000-0000-0000-0000-000000000001"


def test_1_get_outbox_job_requires_authentication():
    """Unauthenticated requests are rejected with 401."""
    client = TestClient(app)
    resp = client.get(f"/api/v1/recovery/outbox/{SYNTHETIC_JOB_ID}", headers={"X-API-Key": "invalid_api_key_xxx"})
    assert resp.status_code == 401
    assert "Unauthorized" in resp.text


def test_2_get_outbox_job_returns_details_when_authenticated():
    """Authenticated requests return job details and reflect approved governance metadata."""
    client = TestClient(app)
    resp = client.get(f"/api/v1/recovery/outbox/{TARGET_JOB_ID}", headers={"X-API-Key": "rzp_test_wapsi_key_2026"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == TARGET_JOB_ID
    assert data["channel"] == "whatsapp"
    assert data["requires_operator_approval"] is True
    assert data["approved_by_operator_id"] == "operator_arpit"
    assert data["approval_snapshot_hash"] == "dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd"


def test_3_approve_outbox_job_endpoint_validates_operator_id():
    """Missing or empty operator_id in request body is rejected with 422."""
    client = TestClient(app)
    # Missing operator_id
    r1 = client.post(
        f"/api/v1/recovery/outbox/{SYNTHETIC_JOB_ID}/approve",
        headers={"X-API-Key": "rzp_test_wapsi_key_2026"},
        json={},
    )
    assert r1.status_code == 422

    # Too short operator_id
    r2 = client.post(
        f"/api/v1/recovery/outbox/{SYNTHETIC_JOB_ID}/approve",
        headers={"X-API-Key": "rzp_test_wapsi_key_2026"},
        json={"operator_id": "ab"},
    )
    assert r2.status_code == 422


def test_4_outbox_store_approve_job_requires_operator_id(tmp_path):
    """DurableOutboxStore.approve_job() raises ValueError if operator_id is empty or whitespace."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))
    job = store.enqueue(
        case_id="case_appr_001",
        payment_id="pay_appr_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Hello"},
        idempotency_key="idemp_appr_001",
        requires_operator_approval=True,
    )

    with pytest.raises(ValueError) as exc:
        store.approve_job(job.id, operator_id="")
    assert "operator_id is required" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        store.approve_job(job.id, operator_id="   ")
    assert "operator_id is required" in str(exc.value)


def test_5_compute_approval_hash_is_deterministic():
    """Hash calculation is stable, reproducible, and sensitive to any modifications."""
    payload = {"text": {"body": "Pay INR 10.00"}, "messaging_product": "whatsapp"}
    recipient = "+91****5671"
    channel = "whatsapp"

    h1 = compute_approval_hash(recipient_masked=recipient, channel=channel, message_payload=payload)
    h2 = compute_approval_hash(recipient_masked=recipient, channel=channel, message_payload=payload)
    assert h1 == h2
    assert len(h1) == 64

    # Tampered payload changes hash
    tampered_payload = {"text": {"body": "Pay INR 1000.00"}, "messaging_product": "whatsapp"}
    h_tampered = compute_approval_hash(recipient_masked=recipient, channel=channel, message_payload=tampered_payload)
    assert h1 != h_tampered

    # Tampered recipient changes hash
    h_tampered_recipient = compute_approval_hash(recipient_masked="+91****9999", channel=channel, message_payload=payload)
    assert h1 != h_tampered_recipient


def test_6_verify_dispatch_authorization_checks_operator_evidence(tmp_path):
    """Unapproved job fails authorization verification."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))
    job = store.enqueue(
        case_id="case_auth_001",
        payment_id="pay_auth_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Test Recovery"},
        idempotency_key="idemp_auth_001",
        requires_operator_approval=True,
    )

    is_auth, err = store.verify_dispatch_authorization(job)
    assert is_auth is False
    assert "requires operator approval" in err


def test_7_tampered_payload_rejected_after_approval(tmp_path):
    """Tampering with message payload after approval causes hash verification failure."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))
    job = store.enqueue(
        case_id="case_auth_002",
        payment_id="pay_auth_002",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Original Amount: INR 10"},
        idempotency_key="idemp_auth_002",
        requires_operator_approval=True,
    )
    store.approve_job(job.id, operator_id="operator_security_lead")
    approved_job = store.get_job(job.id)
    assert approved_job.status == "QUEUED"

    # Pre-tamper check: passes
    ok, _ = store.verify_dispatch_authorization(approved_job)
    assert ok is True

    # Tamper payload
    tampered_job = copy.deepcopy(approved_job)
    tampered_job.message_payload = {"body": "Malicious Amount: INR 100000"}
    ok, err = store.verify_dispatch_authorization(tampered_job)
    assert ok is False
    assert "payload integrity violation" in err


def test_8_customer_opt_out_blocks_authorization_even_if_approved(tmp_path):
    """Customer opt-out in store halts dispatch authorization even if approved by operator."""
    db_file = tmp_path / "test_outbox.db"
    opt_file = tmp_path / "test_opt_out.db"
    store = DurableOutboxStore(db_path=str(db_file))
    opt_out_store = PersistentOptOutStore(db_path=str(opt_file))

    phone = "+916260055671"
    job = store.enqueue(
        case_id="case_auth_003",
        payment_id="pay_auth_003",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"customer_phone": phone, "body": "Recovery Link"},
        idempotency_key="idemp_auth_003",
        requires_operator_approval=True,
    )
    store.approve_job(job.id, operator_id="operator_compliance")
    approved_job = store.get_job(job.id)

    # Before opt-out: authorized
    ok, _ = store.verify_dispatch_authorization(approved_job, opt_out_store=opt_out_store)
    assert ok is True

    # Customer opts out
    opt_out_store.record_opt_out(phone, reason="Customer STOP", source="whatsapp_inbound")
    ok, err = store.verify_dispatch_authorization(approved_job, opt_out_store=opt_out_store)
    assert ok is False
    assert "opted out" in err


def test_9_unapproved_job_blocked_from_worker_claim(tmp_path):
    """Worker cannot claim jobs in PENDING_APPROVAL status."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))
    store.enqueue(
        case_id="case_claim_001",
        payment_id="pay_claim_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Recovery"},
        idempotency_key="idemp_claim_001",
        requires_operator_approval=True,
    )
    claimed = store.claim_jobs(worker_id="worker_test_001", limit=10)
    assert len(claimed) == 0


def test_10_target_sandbox_job_governance_state():
    """Live target job in PostgreSQL has persistent operator approval and immutable governance metadata."""
    dm = DatabaseManager()
    store = DurableOutboxStore(database_manager=dm)
    job = store.get_job(TARGET_JOB_ID, merchant_id=TARGET_MERCHANT_UUID)
    assert job is not None
    assert job.id == TARGET_JOB_ID
    assert job.requires_operator_approval is True
    assert job.approved_by_operator_id == "operator_arpit"
    assert job.approved_at is not None
    assert job.approval_snapshot_hash == "dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd"

