"""
Razorpay Webhook Verification and Event Normalization Handler.
Target: Razorpay Real-Time Webhook Notifications

Provides:
- Constant-time HMAC-SHA256 signature verification over raw request body bytes
- Structured webhook event parsing (payment.captured, payment_link.paid, payment.failed)
- Deterministic idempotency key calculation
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from wapsi.core.config import get_settings
from wapsi.integrations.razorpay.client import (
    RazorpayAuthError,
    RazorpayClient,
    RazorpayValidationError,
)

logger = logging.getLogger("wapsi.integrations.razorpay.webhook")


@dataclass(frozen=True)
class RazorpayWebhookEvent:
    """Normalized Razorpay Webhook Event."""
    event_id: str
    event: str
    account_id: str
    entity_id: str  # payment_id or payment_link_id
    payment_id: Optional[str]
    payment_link_id: Optional[str]
    amount_paise: int
    currency: str
    status: str
    normalized_status: str  # RECOVERED, PENDING, FAILED, etc.
    merchant_id: Optional[str]
    case_id: Optional[str]
    notes: Dict[str, Any]
    idempotency_key: str
    raw_payload: Dict[str, Any]


class RazorpayWebhookHandler:
    """
    Validates and normalizes Razorpay Webhook payloads.
    Guarantees raw-body verification and constant-time digest comparison.
    """

    @staticmethod
    def verify_signature(raw_body: bytes, signature: Optional[str], secret: Optional[Union[str, bytes]] = None) -> bool:
        """
        Verifies Razorpay HMAC-SHA256 signature over raw payload bytes.
        
        Args:
            raw_body: Exact raw request body bytes received on the HTTP socket.
            signature: X-Razorpay-Signature header value.
            secret: Webhook secret configured in Razorpay dashboard.
        """
        if not signature or not raw_body:
            return False

        sec_bytes = None
        if secret:
            sec_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
        else:
            try:
                sec_bytes = get_settings().get_webhook_secret_bytes()
            except Exception as e:
                logger.error(f"Webhook secret unavailable for signature verification: {e}")
                return False

        if not sec_bytes:
            return False

        expected_sig = hmac.new(sec_bytes, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature.strip())

    @classmethod
    def parse_event(
        cls,
        raw_body: bytes,
        signature: Optional[str] = None,
        event_id_header: Optional[str] = None,
        secret: Optional[Union[str, bytes]] = None,
        verify: bool = True,
    ) -> RazorpayWebhookEvent:
        """
        Validates signature (if verify=True) and extracts normalized payment event.
        Supports x-razorpay-event-id header for event-level idempotency and deduplication.
        
        Raises:
            RazorpayAuthError: If signature verification fails.
            RazorpayValidationError: If body is not valid JSON or lacks required fields.
        """
        if verify:
            if not signature:
                raise RazorpayAuthError("Missing X-Razorpay-Signature header on webhook request.")
            if not cls.verify_signature(raw_body, signature, secret=secret):
                raise RazorpayAuthError("Invalid X-Razorpay-Signature: cryptographic HMAC-SHA256 verification failed.")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            raise RazorpayValidationError(f"Invalid JSON webhook body: {e}")

        if not isinstance(payload, dict):
            raise RazorpayValidationError("Webhook payload must be a JSON object.")

        event_name = payload.get("event")
        if not event_name:
            raise RazorpayValidationError("Webhook payload is missing required 'event' field.")

        account_id = str(payload.get("account_id") or "")
        
        # Priority for event_id:
        # 1. X-Razorpay-Event-Id HTTP header
        # 2. payload.event_id or payload.id
        # 3. Deterministic SHA256 of raw body
        event_id = (
            (event_id_header.strip() if event_id_header else None)
            or payload.get("event_id")
            or payload.get("id")
            or f"evt_{hashlib.sha256(raw_body).hexdigest()[:16]}"
        )

        # Razorpay payload entities are structured under payload[entity_type][entity]
        payload_container = payload.get("payload", {})
        if not isinstance(payload_container, dict):
            payload_container = {}
        
        payment_dict = payload_container.get("payment", {})
        payment_entity = payment_dict.get("entity", {}) if isinstance(payment_dict, dict) else {}
        if not isinstance(payment_entity, dict):
            payment_entity = {}

        link_dict = payload_container.get("payment_link", {})
        payment_link_entity = link_dict.get("entity", {}) if isinstance(link_dict, dict) else {}
        if not isinstance(payment_link_entity, dict):
            payment_link_entity = {}

        # Extract primary entity
        primary_entity = payment_entity or payment_link_entity
        entity_id = primary_entity.get("id", "")
        
        payment_id = payment_entity.get("id")
        payment_link_id = payment_link_entity.get("id") or payment_entity.get("payment_link_id")

        if payment_entity:
            amount_paise = int(payment_entity.get("amount", 0))
            currency = payment_entity.get("currency", "INR")
            status = payment_entity.get("status", "")
        else:
            amount_paise = int(payment_link_entity.get("amount_paid") or payment_link_entity.get("amount", 0))
            currency = payment_link_entity.get("currency", "INR")
            status = payment_link_entity.get("status", "")
        
        # If it's payment_link.paid event, status is paid
        if event_name == "payment_link.paid" and not status:
            status = "paid"

        plink_notes = payment_link_entity.get("notes") if isinstance(payment_link_entity.get("notes"), dict) else {}
        pay_notes = payment_entity.get("notes") if isinstance(payment_entity.get("notes"), dict) else {}
        notes = {**plink_notes, **pay_notes}

        merchant_id = notes.get("merchant_id") or notes.get("merchant_code")
        case_id = (
            notes.get("case_id")
            or notes.get("recovery_case_id")
            or payment_link_entity.get("reference_id")
            or payment_entity.get("description")
        )

        normalized_status = RazorpayClient.normalize_payment_status(status)

        # Unique event-level idempotency key
        if event_id_header:
            idempotency_key = f"rzp_{event_id}"
        elif account_id:
            idempotency_key = f"rzp_{account_id}_{event_name}_{entity_id or event_id}"
        else:
            idempotency_key = f"rzp_{event_name}_{entity_id or event_id}"

        return RazorpayWebhookEvent(
            event_id=event_id,
            event=event_name,
            account_id=account_id,
            entity_id=entity_id,
            payment_id=payment_id,
            payment_link_id=payment_link_id,
            amount_paise=amount_paise,
            currency=currency,
            status=status,
            normalized_status=normalized_status,
            merchant_id=merchant_id,
            case_id=case_id,
            notes=notes,
            idempotency_key=idempotency_key,
            raw_payload=payload,
        )

