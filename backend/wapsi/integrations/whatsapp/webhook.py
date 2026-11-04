"""
WhatsApp Cloud API Webhook Verification and Event Processor.
Handles Meta Webhook Subscription Handshake (GET) and Inbound Event Notifications (POST).

Features:
- Constant-time X-Hub-Signature-256 HMAC verification over raw request body
- Delivery status normalization (sent, delivered, read, failed)
- Inbound customer reply extraction and automatic opt-out keyword routing
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from wapsi.core.config import get_settings
from wapsi.integrations.whatsapp.client import WhatsAppAuthError, WhatsAppValidationError
from wapsi.integrations.whatsapp.opt_out import get_opt_out_manager

logger = logging.getLogger("wapsi.integrations.whatsapp.webhook")


@dataclass(frozen=True)
class WhatsAppDeliveryStatus:
    """Represents a delivery status receipt for an outbound message."""
    message_id: str        # wamid.HBg...
    recipient_phone: str   # 919876543210
    status: str            # 'sent', 'delivered', 'read', 'failed'
    timestamp: str
    error_code: Optional[int]
    error_title: Optional[str]
    raw_status: Dict[str, Any]


@dataclass(frozen=True)
class WhatsAppInboundMessage:
    """Represents an inbound customer reply."""
    message_id: str
    from_phone: str
    timestamp: str
    body_text: str
    is_opt_out: bool
    raw_message: Dict[str, Any]


@dataclass(frozen=True)
class WhatsAppEvent:
    """Normalized WhatsApp Webhook Event."""
    event_type: str        # 'delivery_status', 'inbound_message', 'unknown'
    statuses: List[WhatsAppDeliveryStatus]
    inbound_messages: List[WhatsAppInboundMessage]
    raw_payload: Dict[str, Any]


class WhatsAppWebhookHandler:
    """
    Manages Meta Webhook handshakes, signature verification, and event parsing.
    """

    @staticmethod
    def verify_subscription_challenge(
        mode: Optional[str],
        token: Optional[str],
        challenge: Optional[str],
        expected_token: Optional[str] = None,
    ) -> Optional[str]:
        """
        Validates the Meta Webhook Verification handshake (GET request).
        Returns challenge string on success; None on failure.
        """
        if mode != "subscribe" or not token or not challenge:
            return None

        exp = expected_token or get_settings().get_whatsapp_verify_token_str()
        if not exp:
            # Fallback for dev mode
            if get_settings().wapsi_env.lower() != "production":
                exp = "wapsi_meta_verify_token_demo_2026"

        is_dev = get_settings().wapsi_env.lower() != "production"
        if not (exp and (token == exp or (is_dev and token == "wapsi_meta_verify_token_demo_2026"))):
            logger.warning("WhatsApp webhook subscription verify_token mismatch.")
            return None

        logger.info("Meta WhatsApp webhook subscription handshake verified successfully.")
        return challenge

    @staticmethod
    def verify_signature(raw_body: bytes, signature_header: Optional[str], app_secret: Optional[str] = None) -> bool:
        """
        Verifies X-Hub-Signature-256 header (sha256={hmac}) against Meta App Secret.
        Uses constant-time comparison to prevent timing attacks.
        """
        if not signature_header or not raw_body:
            return False

        if not signature_header.startswith("sha256="):
            return False

        provided_sig = signature_header.split("sha256=", 1)[1].strip()
        if not provided_sig:
            return False

        sec_bytes = None
        if app_secret:
            sec_bytes = app_secret.encode("utf-8")
        else:
            try:
                sec_bytes = get_settings().get_meta_app_secret_bytes()
            except Exception:
                sec_bytes = None

        if not sec_bytes:
            return False

        expected_sig = hmac.new(sec_bytes, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, provided_sig)

    @classmethod
    def parse_event(
        cls,
        raw_body: bytes,
        signature: Optional[str] = None,
        app_secret: Optional[str] = None,
        verify: bool = True,
    ) -> WhatsAppEvent:
        """
        Validates signature (if verify=True) and parses statuses and messages.
        """
        if verify:
            if not signature:
                raise WhatsAppAuthError("Missing X-Hub-Signature-256 header.")
            if not signature.startswith("sha256="):
                raise WhatsAppAuthError("Malformed X-Hub-Signature-256 header: must start with 'sha256='.")

            sec_bytes = None
            if app_secret:
                sec_bytes = app_secret.encode("utf-8")
            else:
                try:
                    sec_bytes = get_settings().get_meta_app_secret_bytes()
                except Exception as exc:
                    raise ValueError(f"META_APP_SECRET configuration error: {exc}")

            if not sec_bytes:
                raise ValueError("META_APP_SECRET configuration error: key is unconfigured.")

            provided_sig = signature.split("sha256=", 1)[1].strip()
            if not provided_sig:
                raise WhatsAppAuthError("Malformed X-Hub-Signature-256 header: signature hash is empty.")

            expected_sig = hmac.new(sec_bytes, raw_body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_sig, provided_sig):
                raise WhatsAppAuthError("Invalid X-Hub-Signature-256: Meta cryptographic verification failed.")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            raise WhatsAppValidationError(f"Invalid JSON webhook payload: {e}")

        statuses: List[WhatsAppDeliveryStatus] = []
        messages: List[WhatsAppInboundMessage] = []
        opt_out_manager = get_opt_out_manager()

        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # 1. Parse Status Updates (sent, delivered, read, failed)
                for st in value.get("statuses", []):
                    status_name = st.get("status", "unknown").lower()
                    errors = st.get("errors", [])
                    err_code = errors[0].get("code") if errors else None
                    err_title = errors[0].get("title") if errors else None

                    statuses.append(
                        WhatsAppDeliveryStatus(
                            message_id=st.get("id", ""),
                            recipient_phone=st.get("recipient_id", ""),
                            status=status_name,
                            timestamp=str(st.get("timestamp", "")),
                            error_code=err_code,
                            error_title=err_title,
                            raw_status=st,
                        )
                    )

                # 2. Parse Inbound Customer Messages & Detect Opt-Outs
                for msg in value.get("messages", []):
                    msg_type = msg.get("type", "")
                    from_phone = msg.get("from", "")
                    body_text = ""
                    if msg_type == "text":
                        body_text = msg.get("text", {}).get("body", "")

                    msg_ts_raw = msg.get("timestamp", "")
                    try:
                        msg_ts = float(msg_ts_raw) if msg_ts_raw else time.time()
                    except (ValueError, TypeError):
                        msg_ts = time.time()

                    # Pure classification without in-memory mutation side effects
                    from wapsi.recovery.opt_out_store import PersistentOptOutStore
                    is_opt_out = (
                        PersistentOptOutStore.is_opt_out_text(body_text)
                        or opt_out_manager.is_opt_out_message(body_text)
                    )

                    messages.append(
                        WhatsAppInboundMessage(
                            message_id=msg.get("id", ""),
                            from_phone=from_phone,
                            timestamp=str(msg.get("timestamp", "")),
                            body_text=body_text,
                            is_opt_out=is_opt_out,
                            raw_message=msg,
                        )
                    )

        if statuses and messages:
            event_type = "mixed"
        elif statuses:
            event_type = "status_update"
        elif messages:
            event_type = "inbound_message"
        else:
            event_type = "unknown"

        return WhatsAppEvent(
            event_type=event_type,
            statuses=statuses,
            inbound_messages=messages,
            raw_payload=payload,
        )

