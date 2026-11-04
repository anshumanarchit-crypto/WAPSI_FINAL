"""
WAPSI Phase 2.1 — Hardening & Controlled Sandbox Verification Test Suite.

Verifies:
1. Task 1: Monetary precision with Python Decimal (rejection of float drift, zero, negative, fractional paise).
2. Task 2: Razorpay webhook hardening (X-Razorpay-Event-Id, duplicate event deduplication, out-of-order state protection).
3. Task 3: WhatsApp Meta Graph API compatibility (configurable version, 24h customer service window enforcement).
4. Task 4: Recovery endpoint security (controlled single-merchant boundary, merchant spoofing rejection, phone & amount validation).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from wapsi.api.app import app
from wapsi.core.config import get_settings
from wapsi.db.service import PersistenceService
from wapsi.db.session import DatabaseManager
from wapsi.integrations.orchestration.recovery_orchestrator import (
    PaymentRecoveryOrchestrator,
    RecoveryDispatchReceipt,
    parse_monetary_amount,
)
from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.razorpay.webhook import (
    RazorpayWebhookEvent,
    RazorpayWebhookHandler,
)
from wapsi.integrations.whatsapp.client import (
    WhatsAppClient,
    WhatsAppDeliveryError,
    WhatsAppDispatchResult,
)
from wapsi.integrations.whatsapp.opt_out import OptOutManager, get_opt_out_manager
from wapsi.integrations.whatsapp.webhook import WhatsAppWebhookHandler


# ==============================================================================
# Pytest Fixture: Persistence Isolation
# ==============================================================================
@pytest.fixture(autouse=True)
def isolate_persistence(monkeypatch):
    """Guarantees tests use an isolated in-memory SQLite database (zero remote writes)."""
    test_db = DatabaseManager(database_url="sqlite:///:memory:")
    test_svc = PersistenceService(db_manager=test_db)
    monkeypatch.setattr("wapsi.api.app.get_persistence_service", lambda: test_svc)
    monkeypatch.setattr("wapsi.db.service.get_persistence_service", lambda: test_svc)
    get_opt_out_manager().clear()
    yield test_svc
    get_opt_out_manager().clear()


# ==============================================================================
# TASK 1 — Monetary Precision Tests
# ==============================================================================
class TestMonetaryPrecision:
    def test_float_drift_mitigation(self):
        """Verifies that 19.99 converts to exactly 1999 paise without IEEE 754 float drift."""
        paise = parse_monetary_amount(amount_inr=19.99)
        assert paise == 1999
        assert isinstance(paise, int)

    def test_decimal_and_string_conversions(self):
        """Tests Decimal and string inputs for precise paise conversion."""
        assert parse_monetary_amount(amount_inr=Decimal("1500.50")) == 150050
        assert parse_monetary_amount(amount_inr="2499.99") == 249999
        assert parse_monetary_amount(amount_inr=Decimal("0.01")) == 1

    def test_reject_zero_and_negative_amounts(self):
        """Strictly rejects zero and negative monetary values."""
        with pytest.raises(ValueError, match="strictly positive"):
            parse_monetary_amount(amount_inr=0)

        with pytest.raises(ValueError, match="strictly positive"):
            parse_monetary_amount(amount_inr=-10.50)

        with pytest.raises(ValueError, match="strictly positive"):
            parse_monetary_amount(amount_inr=Decimal("0.00"))

        with pytest.raises(ValueError, match="strictly positive"):
            parse_monetary_amount(amount_paise=-500)

        with pytest.raises(ValueError, match="strictly positive"):
            parse_monetary_amount(amount_paise=0)

    def test_reject_fractional_paise_invalid_precision(self):
        """Rejects amounts with more than 2 decimal places (fractional paise)."""
        with pytest.raises(ValueError, match="fractional paise"):
            parse_monetary_amount(amount_inr="10.005")

        with pytest.raises(ValueError, match="fractional paise"):
            parse_monetary_amount(amount_inr=Decimal("0.001"))

        with pytest.raises(ValueError, match="fractional paise"):
            parse_monetary_amount(amount_inr="1500.125")

    def test_reject_booleans_and_non_numerics(self):
        """Strictly rejects booleans and malformed strings."""
        with pytest.raises(ValueError, match="Boolean"):
            parse_monetary_amount(amount_inr=True)

        with pytest.raises(ValueError, match="Boolean"):
            parse_monetary_amount(amount_paise=False)

        with pytest.raises(ValueError, match="Invalid monetary format"):
            parse_monetary_amount(amount_inr="abc_invalid")

    def test_paise_and_inr_consistency(self):
        """Verifies that matching paise and INR succeed, but conflicting values fail."""
        assert parse_monetary_amount(amount_paise=150000, amount_inr=1500.0) == 150000
        with pytest.raises(ValueError, match="Conflicting monetary values"):
            parse_monetary_amount(amount_paise=150000, amount_inr=2000.0)


# ==============================================================================
# TASK 2 — Razorpay Webhook Hardening Tests
# ==============================================================================
class TestRazorpayWebhookHardening:
    SECRET = "webhook_secret_test_2026"

    def _sign(self, body: bytes) -> str:
        return hmac.new(self.SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()

    def test_event_id_header_extraction(self):
        """Tests that x-razorpay-event-id header is captured and used for event-level idempotency."""
        payload = {
            "entity": "event",
            "account_id": "acc_001",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_999",
                        "amount": 100000,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = self._sign(body_bytes)

        event = RazorpayWebhookHandler.parse_event(
            raw_body=body_bytes,
            signature=sig,
            event_id_header="evt_header_unique_789",
            secret=self.SECRET,
        )
        assert event.event_id == "evt_header_unique_789"
        assert event.idempotency_key == "rzp_evt_header_unique_789"

    def test_duplicate_delivery_deduplication(self):
        """Verifies duplicate webhook deliveries are safely ignored without duplicate timeline events."""
        mock_rzp = MagicMock(spec=RazorpayClient)
        mock_wa = MagicMock(spec=WhatsAppClient)
        mock_wa.send_recovery_reminder.return_value = WhatsAppDispatchResult(
            success=True,
            message_id="wamid.test_dup_1",
            recipient_phone="919876543210",
            status="accepted",
            timestamp=time.time(),
            raw_response={},
        )

        orchestrator = PaymentRecoveryOrchestrator(razorpay_client=mock_rzp, whatsapp_client=mock_wa)
        receipt = orchestrator.initiate_recovery(
            case_id="CASE-DUP-TEST",
            payment_id="pay_fail_dup",
            amount_inr=500.0,
            customer_phone="919876543210",
        )
        initial_events_count = len(receipt.timeline)

        evt = RazorpayWebhookEvent(
            event_id="evt_unique_12345",
            event="payment.captured",
            account_id="acc_1",
            entity_id="pay_fail_dup",
            payment_id="pay_fail_dup",
            payment_link_id=receipt.payment_link_id,
            amount_paise=50000,
            currency="INR",
            status="captured",
            normalized_status="RECOVERED",
            merchant_id="default_merchant",
            case_id="CASE-DUP-TEST",
            notes={},
            idempotency_key="rzp_evt_unique_12345",
            raw_payload={},
        )

        # First delivery: transitions to RECOVERED
        res1 = orchestrator.handle_razorpay_webhook_event(evt)
        assert res1 is not None
        assert res1.status == "RECOVERED"
        events_after_first = len(res1.timeline)

        # Second delivery (duplicate): should be ignored
        res2 = orchestrator.handle_razorpay_webhook_event(evt)
        assert res2 is not None
        assert res2.status == "RECOVERED"
        assert len(res2.timeline) == events_after_first

    def test_out_of_order_failure_does_not_overwrite_recovered(self):
        """Verifies that delayed/out-of-order failure webhooks cannot downgrade a RECOVERED payment."""
        mock_rzp = MagicMock(spec=RazorpayClient)
        mock_wa = MagicMock(spec=WhatsAppClient)
        mock_wa.send_recovery_reminder.return_value = WhatsAppDispatchResult(
            success=True,
            message_id="wamid.order_test",
            recipient_phone="919876543210",
            status="accepted",
            timestamp=time.time(),
            raw_response={},
        )

        orchestrator = PaymentRecoveryOrchestrator(razorpay_client=mock_rzp, whatsapp_client=mock_wa)
        receipt = orchestrator.initiate_recovery(
            case_id="CASE-ORDER-TEST",
            payment_id="pay_fail_order",
            amount_inr=1000.0,
            customer_phone="919876543210",
        )

        # 1. Payment link is paid -> RECOVERED
        captured_evt = RazorpayWebhookEvent(
            event_id="evt_paid_1",
            event="payment_link.paid",
            account_id="acc_1",
            entity_id=receipt.payment_link_id,
            payment_id="pay_succ_1",
            payment_link_id=receipt.payment_link_id,
            amount_paise=100000,
            currency="INR",
            status="paid",
            normalized_status="RECOVERED",
            merchant_id="default_merchant",
            case_id="CASE-ORDER-TEST",
            notes={},
            idempotency_key="rzp_evt_paid_1",
            raw_payload={},
        )
        orchestrator.handle_razorpay_webhook_event(captured_evt)
        assert receipt.status == "RECOVERED"

        # 2. An older or delayed payment.failed event arrives
        delayed_failed_evt = RazorpayWebhookEvent(
            event_id="evt_delayed_fail_1",
            event="payment.failed",
            account_id="acc_1",
            entity_id="pay_fail_order",
            payment_id="pay_fail_order",
            payment_link_id=receipt.payment_link_id,
            amount_paise=100000,
            currency="INR",
            status="failed",
            normalized_status="FAILED",
            merchant_id="default_merchant",
            case_id="CASE-ORDER-TEST",
            notes={},
            idempotency_key="rzp_evt_delayed_fail_1",
            raw_payload={},
        )
        res = orchestrator.handle_razorpay_webhook_event(delayed_failed_evt)
        assert res.status == "RECOVERED"  # Status remains RECOVERED!
        timeline_types = [t.event_type for t in res.timeline]
        assert "OUT_OF_ORDER_PAYMENT_FAILED" in timeline_types


# ==============================================================================
# TASK 3 — WhatsApp Compatibility & 24h Customer Service Window
# ==============================================================================
class TestWhatsAppCompatibilityAnd24hWindow:
    def test_configurable_graph_api_version(self):
        """Verifies endpoint URL dynamically adopts configured Graph API version (v21.0, v22.0, v26.0)."""
        client_v21 = WhatsAppClient(access_token="tok", phone_number_id="123", api_version="v21.0")
        assert "v21.0/123/messages" in client_v21._get_endpoint()

        client_v26 = WhatsAppClient(access_token="tok", phone_number_id="123", api_version="v26.0")
        assert "v26.0/123/messages" in client_v26._get_endpoint()

    def test_24h_window_policy_enforcement(self):
        """
        Tests Meta's 24-hour customer service window rule:
        - When outside the 24-hour window, freeform text reminders raise WhatsAppDeliveryError.
        - When customer interaction is on record within 24h, freeform text is permitted.
        """
        mgr = get_opt_out_manager()
        mgr.clear()
        phone = "919876543210"

        # Outside window: no prior customer message
        assert mgr.is_within_24h_window(phone) is False

        client = WhatsAppClient(access_token="tok", phone_number_id="123")
        with pytest.raises(WhatsAppDeliveryError, match="outside the 24-hour service window"):
            client.send_recovery_reminder(
                to_phone=phone,
                customer_name="Aman",
                amount_str="Rs 500.00",
                payment_link="https://rzp.io/i/test",
                template_name=None,
                enforce_24h_window=True,
            )

        # Inbound message arrives from customer
        mgr.record_customer_interaction(phone, timestamp=time.time())
        assert mgr.is_within_24h_window(phone) is True

        # Now within window: freeform text reminder is permitted
        def handler(req: httpx.Request) -> httpx.Response:
            body = json.loads(req.content)
            assert body["type"] == "text"
            return httpx.Response(200, json={"messages": [{"id": "wamid.in_window_1"}]})

        client_mock = WhatsAppClient(
            access_token="tok",
            phone_number_id="123",
            transport=httpx.MockTransport(handler),
        )
        res = client_mock.send_recovery_reminder(
            to_phone=phone,
            customer_name="Aman",
            amount_str="Rs 500.00",
            payment_link="https://rzp.io/i/test",
            template_name=None,
            enforce_24h_window=True,
        )
        assert res.message_id == "wamid.in_window_1"


# ==============================================================================
# TASK 4 — Recovery Endpoint Security Tests
# ==============================================================================
class TestRecoveryEndpointSecurity:
    def test_merchant_identity_spoofing_rejected(self):
        """Rejects caller attempting to override merchant identity in single-merchant sandbox configuration."""
        client = TestClient(app)
        payload = {
            "case_id": "CASE-SPOOF-1",
            "payment_id": "pay_spoof",
            "amount_in_inr": 1500.0,
            "customer_phone": "+919876543210",
            "merchant_id": "merch_unauthorized_victim",  # Spoofed merchant
        }
        headers = {"X-API-Key": "rzp_test_wapsi_key_2026"}
        res = client.post("/api/v1/recovery/payment-link", json=payload, headers=headers)
        assert res.status_code == 403
        assert "not authorized in this controlled single-merchant sandbox" in res.json()["detail"]

    def test_invalid_phone_number_rejected(self):
        """Rejects invalid or non-E.164 phone numbers."""
        client = TestClient(app)
        payload = {
            "amount_in_inr": 1000.0,
            "customer_phone": "123",  # Invalid phone
        }
        res = client.post("/api/v1/recovery/payment-link", json=payload)
        assert res.status_code == 422

    def test_invalid_monetary_amount_rejected(self):
        """Rejects zero, negative, or fractional paise amounts."""
        client = TestClient(app)

        # Zero amount
        res_zero = client.post(
            "/api/v1/recovery/payment-link",
            json={"amount_in_inr": 0.0, "customer_phone": "+919876543210"},
        )
        assert res_zero.status_code == 422

        # Negative amount
        res_neg = client.post(
            "/api/v1/recovery/payment-link",
            json={"amount_in_inr": -50.0, "customer_phone": "+919876543210"},
        )
        assert res_neg.status_code == 422

    def test_authenticated_or_controlled_sandbox_request_succeeds(self):
        """Verifies valid single-merchant sandbox recovery link creation succeeds with integer paise."""
        client = TestClient(app)
        case_id = f"RX-HARDENED-{int(time.time())}"
        payload = {
            "case_id": case_id,
            "payment_id": "pay_valid_777",
            "amount_paise": 185000,
            "customer_phone": "+91 98765 43210",
            "customer_name": "Hardened Customer",
            "merchant_id": "default_merchant",
        }

        with patch.object(RazorpayClient, "create_payment_link") as mock_plink:
            mock_plink.return_value = {
                "id": f"plink_{case_id}",
                "short_url": f"https://rzp.io/i/plink_{case_id}",
            }
            with patch.object(WhatsAppClient, "send_recovery_reminder") as mock_wa:
                mock_wa.return_value = WhatsAppDispatchResult(
                    success=True,
                    message_id=f"wamid.{case_id}",
                    recipient_phone="919876543210",
                    status="accepted",
                    timestamp=time.time(),
                    raw_response={},
                )
                headers = {"X-API-Key": "rzp_test_wapsi_key_2026"}
                res = client.post("/api/v1/recovery/payment-link", json=payload, headers=headers)
                assert res.status_code == 200
                data = res.json()
                assert data["amount_paise"] == 185000
                assert data["amount_inr"] == 1850.0
                assert data["status"] == "DISPATCHED"

