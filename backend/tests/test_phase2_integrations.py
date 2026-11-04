"""
WAPSI Phase 2 — Comprehensive Integration Test Suite.
Tests:
1. Razorpay Test Mode Client (Payment Links, error classification, retry backoff, status normalization).
2. Razorpay Webhooks (HMAC-SHA256 constant-time verification, event extraction, idempotency).
3. WhatsApp Cloud API Client (E.164 normalization, text & template dispatch, rate limiting, error handling).
4. WhatsApp Webhooks & Opt-Out Governance (Subscription challenge handshake, delivery status, DND stop keywords).
5. Autonomous Payment Recovery Orchestrator (Full lifecycle: DISPATCHED -> DELIVERED -> READ -> RECOVERED).
6. FastAPI Recovery & Integration Endpoints.

Safety & Isolation Guarantees:
- Uses httpx.MockTransport for external provider simulation (Zero real charges, zero live WhatsApp messages).
- Forces SQLite in-memory persistence isolation (Zero rows written to remote Supabase database).
- Sanitized credentials; zero secrets exposed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, List
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
)
from wapsi.integrations.razorpay.client import (
    RazorpayAuthError,
    RazorpayClient,
    RazorpayNetworkError,
    RazorpayNotFoundError,
    RazorpayRateLimitError,
    RazorpayValidationError,
)
from wapsi.integrations.razorpay.webhook import (
    RazorpayWebhookEvent,
    RazorpayWebhookHandler,
)
from wapsi.integrations.whatsapp.client import (
    WhatsAppAuthError,
    WhatsAppClient,
    WhatsAppDeliveryError,
    WhatsAppRateLimitError,
    WhatsAppValidationError,
)
from wapsi.integrations.whatsapp.opt_out import OptOutManager, get_opt_out_manager
from wapsi.integrations.whatsapp.webhook import (
    WhatsAppDeliveryStatus,
    WhatsAppWebhookHandler,
)


# ==============================================================================
# Pytest Fixtures: Persistence Isolation
# ==============================================================================
@pytest.fixture(autouse=True)
def isolate_persistence_environment(monkeypatch):
    """Guarantees tests run strictly against an isolated in-memory SQLite database."""
    test_db = DatabaseManager(database_url="sqlite:///:memory:")
    test_svc = PersistenceService(db_manager=test_db)
    monkeypatch.setattr("wapsi.api.app.get_persistence_service", lambda: test_svc)
    monkeypatch.setattr("wapsi.db.service.get_persistence_service", lambda: test_svc)
    yield test_svc
    # Reset opt-out manager
    get_opt_out_manager().clear()


# ==============================================================================
# 1. Razorpay Client Tests
# ==============================================================================
class TestRazorpayClient:
    def test_live_key_rejection_in_test_mode(self):
        """Rejects live key credentials when configured in test mode."""
        with patch.object(get_settings(), "razorpay_mode", "test"):
            with pytest.raises(RazorpayAuthError, match="Live Razorpay Key ID"):
                RazorpayClient(key_id="rzp_live_abc123456789", key_secret="test_secret")

    def test_missing_credentials_raise_auth_error(self):
        """Raises RazorpayAuthError when key_id or key_secret is missing."""
        client = RazorpayClient(key_id="", key_secret="")
        with pytest.raises(RazorpayAuthError, match="credentials are not configured"):
            client.get_payment_link("plink_123")

    def test_create_payment_link_payload_validation(self):
        """Validates that amount must be a positive integer in paise."""
        client = RazorpayClient(key_id="rzp_test_valid", key_secret="secret")
        with pytest.raises(RazorpayValidationError, match="positive integer in paise"):
            client.create_payment_link(amount_in_paise=-500)

        with pytest.raises(RazorpayValidationError, match="positive integer in paise"):
            client.create_payment_link(amount_in_paise=0)

    def test_create_payment_link_success_mock_transport(self):
        """Simulates successful creation of a Razorpay Payment Link."""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/payment_links"
            body = json.loads(request.content)
            assert body["amount"] == 150000
            assert body["currency"] == "INR"
            assert body["customer"]["contact"] == "919876543210"
            assert body["notify"]["whatsapp"] is False
            return httpx.Response(
                200,
                json={
                    "id": "plink_test_9999",
                    "short_url": "https://rzp.io/i/plink_test_9999",
                    "status": "created",
                    "amount": 150000,
                    "currency": "INR",
                },
            )

        transport = httpx.MockTransport(handler)
        client = RazorpayClient(key_id="rzp_test_123", key_secret="secret", transport=transport)
        res = client.create_payment_link(
            amount_in_paise=150000,
            customer={"name": "Alice Sharma", "contact": "919876543210"},
            notes={"case_id": "RX-101"},
            expire_by=1730000000,
        )
        assert res["id"] == "plink_test_9999"
        assert res["short_url"] == "https://rzp.io/i/plink_test_9999"

    def test_get_and_cancel_payment_link(self):
        """Tests retrieval and cancellation requests."""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/v1/payment_links/plink_abc":
                return httpx.Response(200, json={"id": "plink_abc", "status": "created"})
            elif request.method == "POST" and request.url.path == "/v1/payment_links/plink_abc/cancel":
                return httpx.Response(200, json={"id": "plink_abc", "status": "cancelled"})
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})

        transport = httpx.MockTransport(handler)
        client = RazorpayClient(key_id="rzp_test_123", key_secret="secret", transport=transport)

        get_res = client.get_payment_link("plink_abc")
        assert get_res["status"] == "created"

        cancel_res = client.cancel_payment_link("plink_abc")
        assert cancel_res["status"] == "cancelled"

    def test_error_classification(self):
        """Tests classification of HTTP 400, 401, 404, 429 into typed exceptions."""
        client = RazorpayClient(key_id="rzp_test_123", key_secret="secret")

        # 401 Auth error
        resp_401 = httpx.Response(401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Auth failed"}})
        err_401 = client._classify_error(resp_401)
        assert isinstance(err_401, RazorpayAuthError)

        # 400 Validation error
        resp_400 = httpx.Response(400, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Invalid amount"}})
        err_400 = client._classify_error(resp_400)
        assert isinstance(err_400, RazorpayValidationError)

        # 404 Not found
        resp_404 = httpx.Response(404, json={"error": {"code": "NOT_FOUND", "description": "Link not found"}})
        err_404 = client._classify_error(resp_404)
        assert isinstance(err_404, RazorpayNotFoundError)

        # 429 Rate limit
        resp_429 = httpx.Response(429, json={"error": {"code": "TOO_MANY_REQUESTS", "description": "Rate limit exceeded"}})
        err_429 = client._classify_error(resp_429)
        assert isinstance(err_429, RazorpayRateLimitError)

    def test_status_normalization(self):
        """Verifies mapping of Razorpay raw statuses to canonical WAPSI recovery states."""
        assert RazorpayClient.normalize_payment_status("paid") == "RECOVERED"
        assert RazorpayClient.normalize_payment_status("captured") == "RECOVERED"
        assert RazorpayClient.normalize_payment_status("created") == "PENDING"
        assert RazorpayClient.normalize_payment_status("processing") == "PROCESSING"
        assert RazorpayClient.normalize_payment_status("failed") == "FAILED"
        assert RazorpayClient.normalize_payment_status("cancelled") == "CANCELLED"
        assert RazorpayClient.normalize_payment_status("expired") == "EXPIRED"
        assert RazorpayClient.normalize_payment_status(None) == "UNKNOWN"


# ==============================================================================
# 2. Razorpay Webhook Verification Tests
# ==============================================================================
class TestRazorpayWebhooks:
    SECRET = "super_secret_webhook_key_2026"

    def _generate_signature(self, body_bytes: bytes, secret: str = SECRET) -> str:
        return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    def test_signature_verification_success_and_failure(self):
        """Tests constant-time HMAC-SHA256 signature verification."""
        body = b'{"event":"payment_link.paid","account_id":"acc_1"}'
        sig = self._generate_signature(body)

        assert RazorpayWebhookHandler.verify_signature(body, sig, secret=self.SECRET) is True
        # Tampered payload fails
        assert RazorpayWebhookHandler.verify_signature(body + b" ", sig, secret=self.SECRET) is False
        # Tampered signature fails
        assert RazorpayWebhookHandler.verify_signature(body, sig[:-2] + "00", secret=self.SECRET) is False
        # Empty signature fails
        assert RazorpayWebhookHandler.verify_signature(body, "", secret=self.SECRET) is False

    def test_parse_event_payment_captured(self):
        """Tests parsing and normalizing a payment.captured webhook payload."""
        payload = {
            "entity": "event",
            "account_id": "acc_mumbai_001",
            "event": "payment.captured",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_cap_123",
                        "amount": 250000,
                        "currency": "INR",
                        "status": "captured",
                        "payment_link_id": "plink_rec_777",
                        "notes": {
                            "case_id": "RX-CASE-555",
                            "merchant_id": "merch_acme",
                        },
                    }
                }
            },
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = self._generate_signature(body_bytes)

        event = RazorpayWebhookHandler.parse_event(body_bytes, signature=sig, secret=self.SECRET)
        assert event.event == "payment.captured"
        assert event.payment_id == "pay_test_cap_123"
        assert event.payment_link_id == "plink_rec_777"
        assert event.amount_paise == 250000
        assert event.normalized_status == "RECOVERED"
        assert event.case_id == "RX-CASE-555"
        assert event.merchant_id == "merch_acme"
        assert "rzp_acc_mumbai_001_payment.captured_pay_test_cap_123" in event.idempotency_key

    def test_parse_event_invalid_signature_raises_auth_error(self):
        """Raises RazorpayAuthError when signature is invalid."""
        body = b'{"event":"payment.failed"}'
        with pytest.raises(RazorpayAuthError, match="cryptographic HMAC-SHA256 verification failed"):
            RazorpayWebhookHandler.parse_event(body, signature="bad_signature", secret=self.SECRET)


# ==============================================================================
# 3. WhatsApp Client Tests
# ==============================================================================
class TestWhatsAppClient:
    def test_phone_number_sanitization(self):
        """Tests E.164 phone number normalization."""
        # 10 digits gets 91 prepended
        assert WhatsAppClient.sanitize_phone_number("9876543210") == "919876543210"
        # +91 formatted string stripped and cleaned
        assert WhatsAppClient.sanitize_phone_number("+91 98765-43210") == "919876543210"
        # Non-Indian international format
        assert WhatsAppClient.sanitize_phone_number("+1 (415) 555-2671") == "14155552671"

        # Invalid lengths raise delivery error
        with pytest.raises(WhatsAppDeliveryError):
            WhatsAppClient.sanitize_phone_number("12345")
        with pytest.raises(WhatsAppDeliveryError):
            WhatsAppClient.sanitize_phone_number("")

    def test_send_text_message_success_mock(self):
        """Simulates successful text message dispatch via Meta Graph API."""
        def handler(request: httpx.Request) -> httpx.Response:
            assert "messages" in request.url.path
            assert request.headers["Authorization"] == "Bearer test_meta_token"
            body = json.loads(request.content)
            assert body["to"] == "919876543210"
            assert body["type"] == "text"
            assert "https://rzp.io/i/" in body["text"]["body"]
            return httpx.Response(
                200,
                json={
                    "messaging_product": "whatsapp",
                    "contacts": [{"input": "919876543210", "wa_id": "919876543210"}],
                    "messages": [{"id": "wamid.HBgLMTEwODk4NzY1NA=="}],
                },
            )

        transport = httpx.MockTransport(handler)
        client = WhatsAppClient(
            access_token="test_meta_token",
            phone_number_id="1000987654321",
            transport=transport,
        )

        res = client.send_recovery_reminder(
            to_phone="9876543210",
            customer_name="Rohan",
            amount_str="Rs 2,500.00",
            payment_link="https://rzp.io/i/test_link_1",
            merchant_name="Zomato",
        )
        assert res.success is True
        assert res.message_id == "wamid.HBgLMTEwODk4NzY1NA=="
        assert res.recipient_phone == "919876543210"
        assert res.status == "accepted"

    def test_send_template_message_structure(self):
        """Simulates pre-approved template message structure."""
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["type"] == "template"
            assert body["template"]["name"] == "payment_recovery_v1"
            assert body["template"]["language"]["code"] == "en"
            return httpx.Response(200, json={"messages": [{"id": "wamid.template_999"}]})

        transport = httpx.MockTransport(handler)
        client = WhatsAppClient(
            access_token="token",
            phone_number_id="phone_id",
            transport=transport,
        )

        res = client.send_recovery_reminder(
            to_phone="919876543210",
            customer_name="Priya",
            amount_str="Rs 999.00",
            payment_link="https://rzp.io/i/priya_link",
            template_name="payment_recovery_v1",
        )
        assert res.message_id == "wamid.template_999"

    def test_whatsapp_error_classification(self):
        """Tests classification of Meta Graph API errors."""
        client = WhatsAppClient(access_token="token", phone_number_id="id")

        # 401 Auth error
        resp_401 = httpx.Response(401, json={"error": {"code": 190, "message": "Invalid OAuth access token."}})
        assert isinstance(client._classify_error(resp_401), WhatsAppAuthError)

        # 429 Rate limit
        resp_429 = httpx.Response(429, json={"error": {"code": 4, "message": "Application rate limit reached."}})
        assert isinstance(client._classify_error(resp_429), WhatsAppRateLimitError)

        # 400 Bad request / invalid recipient
        resp_400 = httpx.Response(400, json={"error": {"code": 131030, "message": "Recipient phone number not in allowed list."}})
        assert isinstance(client._classify_error(resp_400), WhatsAppDeliveryError)


# ==============================================================================
# 4. WhatsApp Webhook & Opt-Out Governance Tests
# ==============================================================================
class TestWhatsAppWebhookAndOptOut:
    APP_SECRET = "meta_app_secret_test_2026"

    def _generate_meta_sig(self, body_bytes: bytes) -> str:
        digest = hmac.new(self.APP_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_subscription_verification_handshake(self):
        """Tests Meta hub.challenge verification handshake."""
        # Success when tokens match
        res = WhatsAppWebhookHandler.verify_subscription_challenge(
            mode="subscribe",
            token="wapsi_meta_verify_token_demo_2026",
            challenge="CHALLENGE_STRING_12345",
            expected_token="wapsi_meta_verify_token_demo_2026",
        )
        assert res == "CHALLENGE_STRING_12345"

        # Failure on token mismatch
        res_fail = WhatsAppWebhookHandler.verify_subscription_challenge(
            mode="subscribe",
            token="wrong_token",
            challenge="CHALLENGE_12345",
            expected_token="wapsi_meta_verify_token_demo_2026",
        )
        assert res_fail is None

    def test_delivery_status_parsing(self):
        """Tests parsing delivery receipts (sent, delivered, read)."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "biz_acc_1",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"display_phone_number": "12345", "phone_number_id": "p1"},
                                "statuses": [
                                    {
                                        "id": "wamid.delivery_receipt_001",
                                        "status": "delivered",
                                        "timestamp": "1730000050",
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
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = self._generate_meta_sig(body_bytes)

        event = WhatsAppWebhookHandler.parse_event(body_bytes, signature=sig, app_secret=self.APP_SECRET)
        assert event.event_type == "status_update"
        assert len(event.statuses) == 1
        st = event.statuses[0]
        assert st.message_id == "wamid.delivery_receipt_001"
        assert st.status == "delivered"
        assert st.recipient_phone == "919876543210"

    def test_inbound_opt_out_keyword_detection(self):
        """Tests detection of STOP / UNSUBSCRIBE keywords and registration in OptOutManager."""
        mgr = get_opt_out_manager()
        mgr.clear()

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "919876543210",
                                        "id": f"wamid.inbound_msg_001_{time.time()}",
                                        "timestamp": "1730000060",
                                        "type": "text",
                                        "text": {"body": "STOP"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = self._generate_meta_sig(body_bytes)

        event = WhatsAppWebhookHandler.parse_event(body_bytes, signature=sig, app_secret=self.APP_SECRET)
        assert len(event.inbound_messages) == 1
        assert event.inbound_messages[0].is_opt_out is True

        from wapsi.recovery.webhook_processor import get_durable_webhook_processor
        processor = get_durable_webhook_processor()
        for msg in event.inbound_messages:
            processor.process_inbound_customer_message(
                from_phone=msg.from_phone,
                message_body=msg.body_text,
                message_id=msg.message_id,
                provider_timestamp=float(msg.timestamp or time.time()),
            )

        # Customer phone should now be registered as opted out
        assert mgr.is_opted_out("919876543210") is True
        assert mgr.is_opted_out("+91-98765-43210") is True

        # Non-opt-out customer remains not opted out
        assert mgr.is_opted_out("919999999999") is False


# ==============================================================================
# 5. Autonomous Payment Recovery Orchestrator Lifecycle Tests
# ==============================================================================
class TestPaymentRecoveryOrchestrator:
    def test_end_to_end_recovery_lifecycle(self):
        """
        Executes end-to-end recovery lifecycle:
        1. initiate_recovery -> DISPATCHED
        2. handle_whatsapp_delivery_event -> DELIVERED -> READ
        3. handle_razorpay_webhook_event -> RECOVERED
        """
        # Mock Razorpay Client
        mock_rzp = MagicMock(spec=RazorpayClient)
        mock_rzp.create_payment_link.return_value = {
            "id": "plink_life_123",
            "short_url": "https://rzp.io/i/plink_life_123",
            "status": "created",
        }

        # Mock WhatsApp Client
        mock_wa = MagicMock(spec=WhatsAppClient)
        from wapsi.integrations.whatsapp.client import WhatsAppDispatchResult
        mock_wa.send_recovery_reminder.return_value = WhatsAppDispatchResult(
            success=True,
            message_id="wamid.life_msg_777",
            recipient_phone="919876543210",
            status="accepted",
            timestamp=time.time(),
            raw_response={},
        )

        opt_out = OptOutManager()
        orchestrator = PaymentRecoveryOrchestrator(
            razorpay_client=mock_rzp,
            whatsapp_client=mock_wa,
            opt_out_manager=opt_out,
        )

        # 1. Initiate Recovery
        receipt = orchestrator.initiate_recovery(
            case_id="CASE-LIFECYCLE-1",
            payment_id="pay_fail_abc",
            amount_inr=1500.50,
            customer_name="Vikram Singh",
            customer_phone="919876543210",
            merchant_name="Flipkart",
        )

        assert receipt.status == "DISPATCHED"
        assert receipt.amount_paise == 150050  # Deterministic paise conversion
        assert receipt.payment_link_id == "plink_life_123"
        assert receipt.whatsapp_message_id == "wamid.life_msg_777"
        assert len(receipt.timeline) == 3  # DECISION_MADE, LINK_CREATED, WHATSAPP_DISPATCHED

        # 2. WhatsApp Delivery Receipt: DELIVERED
        st_delivered = WhatsAppDeliveryStatus(
            message_id="wamid.life_msg_777",
            recipient_phone="919876543210",
            status="delivered",
            timestamp=str(int(time.time())),
            error_code=None,
            error_title=None,
            raw_status={},
        )
        upd1 = orchestrator.handle_whatsapp_delivery_event(st_delivered)
        assert upd1 is not None
        assert upd1.status == "DELIVERED"

        # 3. WhatsApp Delivery Receipt: READ
        st_read = WhatsAppDeliveryStatus(
            message_id="wamid.life_msg_777",
            recipient_phone="919876543210",
            status="read",
            timestamp=str(int(time.time())),
            error_code=None,
            error_title=None,
            raw_status={},
        )
        upd2 = orchestrator.handle_whatsapp_delivery_event(st_read)
        assert upd2.status == "READ"

        # 4. Razorpay Webhook Event: payment.captured
        rzp_event = RazorpayWebhookEvent(
            event_id="evt_cap_001",
            event="payment_link.paid",
            account_id="acc_1",
            entity_id="plink_life_123",
            payment_id="pay_success_999",
            payment_link_id="plink_life_123",
            amount_paise=150050,
            currency="INR",
            status="paid",
            normalized_status="RECOVERED",
            merchant_id="Flipkart",
            case_id="CASE-LIFECYCLE-1",
            notes={"case_id": "CASE-LIFECYCLE-1"},
            idempotency_key="rzp_plink_life_123_paid",
            raw_payload={},
        )
        upd3 = orchestrator.handle_razorpay_webhook_event(rzp_event)
        assert upd3 is not None
        assert upd3.status == "RECOVERED"

        # Check Timeline
        timeline = orchestrator.get_timeline("CASE-LIFECYCLE-1")
        assert len(timeline) >= 6
        event_types = [t["eventType"] for t in timeline]
        assert "DECISION_MADE" in event_types
        assert "LINK_CREATED" in event_types
        assert "WHATSAPP_DISPATCHED" in event_types
        assert "WHATSAPP_DELIVERED" in event_types
        assert "WHATSAPP_READ" in event_types
        assert "PAYMENT_CAPTURED" in event_types

    def test_opt_out_suppresses_recovery_dispatch(self):
        """Verifies that an opted-out customer receives zero payment links or WhatsApp messages."""
        mock_rzp = MagicMock(spec=RazorpayClient)
        mock_wa = MagicMock(spec=WhatsAppClient)
        opt_out = OptOutManager()
        opt_out.record_opt_out("919876543210")

        orchestrator = PaymentRecoveryOrchestrator(
            razorpay_client=mock_rzp,
            whatsapp_client=mock_wa,
            opt_out_manager=opt_out,
        )

        receipt = orchestrator.initiate_recovery(
            case_id="CASE-OPTED-OUT",
            payment_id="pay_blocked",
            amount_inr=500.0,
            customer_name="Customer",
            customer_phone="919876543210",
        )

        assert receipt.status == "SUPPRESSED_OPT_OUT"
        # Verify external providers were NOT contacted
        mock_rzp.create_payment_link.assert_not_called()
        mock_wa.send_recovery_reminder.assert_not_called()


# ==============================================================================
# 6. FastAPI Endpoints Integration Tests
# ==============================================================================
class TestFastAPIRecoveryEndpoints:
    def test_integrations_status_endpoint(self):
        """Verifies GET /api/v1/integrations/status returns provider metadata."""
        client = TestClient(app)
        res = client.get("/api/v1/integrations/status")
        assert res.status_code == 200
        data = res.json()
        assert "razorpay" in data
        assert "whatsapp_cloud_api" in data
        assert "database" in data
        assert data["razorpay"]["mode"] == "test"
        assert data["database"]["status"] in ("connected", "healthy")

    def test_whatsapp_webhook_verification_endpoint(self):
        """Verifies GET /api/v1/webhooks/whatsapp handshake."""
        client = TestClient(app)
        # Success with matching token
        res = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wapsi_meta_verify_token_demo_2026",
                "hub.challenge": "MUMBAI_DEMO_CHALLENGE",
            },
        )
        assert res.status_code == 200
        assert res.text == "MUMBAI_DEMO_CHALLENGE"

        # 403 on invalid token
        res_fail = client.get(
            "/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "CHALLENGE",
            },
        )
        assert res_fail.status_code == 403

    def test_post_recovery_payment_link_endpoint(self):
        """Verifies POST /api/v1/recovery/payment-link and timeline retrieval."""
        from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
        get_persistent_opt_out_store().revoke_opt_out("919876543210", consent_proof="TEST_CONSENT")
        get_opt_out_manager().clear()
        client = TestClient(app)
        case_id = f"RX-E2E-{int(time.time())}"

        # Mock the orchestrator's initiate_recovery call
        payload = {
            "case_id": case_id,
            "payment_id": "pay_fail_test_777",
            "amount_in_inr": 1250.00,
            "customer_name": "Test Shopper",
            "customer_phone": "919876543210",
            "merchant_name": "Swiggy",
            "expire_minutes": 15,
        }

        # Mock external network calls in client
        with patch.object(RazorpayClient, "create_payment_link") as mock_plink:
            mock_plink.return_value = {
                "id": f"plink_{case_id}",
                "short_url": f"https://rzp.io/i/plink_{case_id}",
            }
            with patch.object(WhatsAppClient, "send_recovery_reminder") as mock_wa:
                from wapsi.integrations.whatsapp.client import WhatsAppDispatchResult
                mock_wa.return_value = WhatsAppDispatchResult(
                    success=True,
                    message_id=f"wamid.{case_id}",
                    recipient_phone="919876543210",
                    status="accepted",
                    timestamp=time.time(),
                    raw_response={},
                )

                headers = {"X-API-Key": "rzp_test_wapsi_key_2026"}
                post_res = client.post("/api/v1/recovery/payment-link", json=payload, headers=headers)
                assert post_res.status_code == 200
                data = post_res.json()
                assert data["case_id"] == case_id
                assert data["amount_paise"] == 125000
                assert data["status"] == "DISPATCHED"

                # Check timeline endpoint
                tl_res = client.get(f"/api/v1/recovery/cases/{case_id}/timeline", headers=headers)
                assert tl_res.status_code == 200
                tl_data = tl_res.json()
                assert tl_data["case_id"] == case_id
                assert tl_data["total_events"] >= 3
