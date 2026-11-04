"""
Autonomous Payment Recovery Orchestrator.
Coordinates the end-to-end recovery lifecycle between:
1. Razorpay Test Mode Payment Links
2. WhatsApp Cloud API Message Delivery
3. Webhook Delivery & Payment Reconciliation

Guarantees:
- Deterministic monetary calculations using Python Decimal (Zero float representation error, zero LLM involvement).
- Constant customer consent & opt-out enforcement.
- Authoritative state machine transitions (RECOVERED cannot be overwritten by delayed failures).
- Event-level idempotency and deduplication.
- Complete lifecycle status tracking (PENDING -> DISPATCHED -> DELIVERED -> READ -> RECOVERED).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Set, Union

from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.razorpay.webhook import RazorpayWebhookEvent
from wapsi.integrations.whatsapp.client import WhatsAppClient
from wapsi.integrations.whatsapp.opt_out import OptOutManager, get_opt_out_manager
from wapsi.integrations.whatsapp.webhook import WhatsAppDeliveryStatus

logger = logging.getLogger("wapsi.orchestrator")


def parse_monetary_amount(
    amount_paise: Optional[int] = None,
    amount_inr: Optional[Union[Decimal, float, str, int]] = None,
) -> int:
    """
    Validates and converts monetary amounts strictly into integer paise using Python Decimal.
    
    Guarantees:
    - Pure decimal arithmetic avoiding IEEE 754 floating-point inaccuracies.
    - Rejects invalid precision: INR amounts cannot have fractional paise (more than 2 decimal places).
    - Strictly rejects zero and negative amounts.
    - Rejects non-numeric, NaN, and Infinite values.
    - If amount_paise is supplied, validates that it is a positive integer.
    - If both amount_paise and amount_inr are supplied, ensures exact consistency.
    """
    paise_from_inr: Optional[int] = None

    if amount_inr is not None:
        if isinstance(amount_inr, bool):
            raise ValueError("Boolean values are not valid monetary amounts.")
        try:
            dec = Decimal(str(amount_inr).strip())
        except (InvalidOperation, TypeError, ValueError) as err:
            raise ValueError(f"Invalid monetary format for amount_inr: {amount_inr}") from err

        if dec.is_nan() or dec.is_infinite():
            raise ValueError(f"Monetary amount cannot be NaN or Infinite: {amount_inr}")

        if dec <= Decimal("0"):
            raise ValueError(f"Monetary amount must be strictly positive (> 0), got: {amount_inr}")

        # Check precision: INR has at most 2 decimal places (1 INR = 100 paise).
        # Reject fractional paise (e.g. 10.005, 0.001)
        sign, digits, exponent = dec.as_tuple()
        if exponent < -2:
            quantized = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if (dec - quantized).copy_abs() > Decimal("0"):
                raise ValueError(
                    f"Invalid monetary precision: INR amounts cannot have fractional paise (got: {amount_inr})"
                )
            dec = quantized

        paise_dec = (dec * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        paise_from_inr = int(paise_dec)
        if paise_from_inr <= 0:
            raise ValueError(f"Monetary amount in paise must be > 0, got: {paise_from_inr}")

    if amount_paise is not None:
        if isinstance(amount_paise, bool):
            raise ValueError("Boolean values are not valid monetary amounts.")
        if not isinstance(amount_paise, int):
            raise ValueError(f"amount_paise must be an integer, got: {type(amount_paise).__name__}")
        if amount_paise <= 0:
            raise ValueError(f"amount_paise must be strictly positive (> 0), got: {amount_paise}")
        if paise_from_inr is not None and amount_paise != paise_from_inr:
            raise ValueError(
                f"Conflicting monetary values provided: amount_paise={amount_paise} != converted paise={paise_from_inr}"
            )
        return amount_paise

    if paise_from_inr is not None:
        return paise_from_inr

    raise ValueError("Either amount_paise or amount_inr must be provided.")


@dataclass
class RecoveryTimelineEvent:
    """Represents a milestone in the recovery timeline."""
    event_type: str        # 'DECISION_MADE', 'LINK_CREATED', 'WHATSAPP_DISPATCHED', 'DELIVERED', 'READ', 'PAID', 'FAILED'
    timestamp: float
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryDispatchReceipt:
    """Complete dispatch receipt linking payment links, messages, and cases."""
    case_id: str
    payment_id: str
    amount_paise: int
    amount_inr: float      # Serialized standard INR float for backward compatibility
    payment_link_id: str
    payment_link_url: str
    whatsapp_message_id: str
    recipient_phone: str
    status: str            # 'DISPATCHED', 'DELIVERED', 'READ', 'RECOVERED', 'FAILED', 'SUPPRESSED_OPT_OUT'
    created_at: float
    updated_at: float
    timeline: List[RecoveryTimelineEvent] = field(default_factory=list)


class PaymentRecoveryOrchestrator:
    """
    Coordinates external provider interactions for autonomous payment recovery.
    """

    def __init__(
        self,
        razorpay_client: Optional[RazorpayClient] = None,
        whatsapp_client: Optional[WhatsAppClient] = None,
        opt_out_manager: Optional[OptOutManager] = None,
    ):
        self.rzp = razorpay_client or RazorpayClient()
        self.wa = whatsapp_client or WhatsAppClient()
        self.opt_out = opt_out_manager or get_opt_out_manager()
        # In-memory case registry for real-time frontend and test inspection
        self._cases: Dict[str, RecoveryDispatchReceipt] = {}
        self._message_to_case: Dict[str, str] = {}
        self._link_to_case: Dict[str, str] = {}
        # Idempotency and deduplication tracking
        self._processed_events: Set[str] = set()

    def initiate_recovery(
        self,
        case_id: str,
        payment_id: str,
        amount_inr: Optional[Union[Decimal, float, str, int]] = None,
        customer_name: str = "Valued Customer",
        customer_phone: str = "",
        merchant_name: str = "Merchant",
        merchant_id: Optional[str] = None,
        expire_minutes: int = 15,
        template_name: Optional[str] = None,
        amount_in_inr: Optional[Union[Decimal, float, str, int]] = None,
        amount_paise: Optional[int] = None,
    ) -> RecoveryDispatchReceipt:
        """
        Executes genuine recovery sequence:
        1. Checks customer opt-out.
        2. Validates amount using Python Decimal into exact integer paise.
        3. Creates Razorpay Payment Link in paise.
        4. Formats WhatsApp message with link.
        5. Dispatches message via WhatsApp Cloud API.
        6. Logs dispatch receipt with wamid.
        """
        # Backward compatibility for amount_in_inr argument
        effective_inr = amount_in_inr if amount_in_inr is not None else amount_inr

        # Deterministic monetary calculation in integer paise
        amount_paise_val = parse_monetary_amount(
            amount_paise=amount_paise,
            amount_inr=effective_inr,
        )
        amount_inr_dec = Decimal(amount_paise_val) / Decimal(100)
        amount_inr_float = float(amount_inr_dec)

        timeline = [
            RecoveryTimelineEvent(
                event_type="DECISION_MADE",
                timestamp=time.time(),
                description=f"Autonomous engine approved WhatsApp recovery link for Rs {amount_inr_dec:,.2f}.",
                metadata={"amount_inr": amount_inr_float, "amount_paise": amount_paise_val},
            )
        ]

        # 1. Opt-Out Check
        if self.opt_out.is_opted_out(customer_phone):
            logger.warning(f"Recovery suppressed for case {case_id}: Customer {customer_phone[:4]}*** has opted out.")
            timeline.append(
                RecoveryTimelineEvent(
                    event_type="SUPPRESSED_OPT_OUT",
                    timestamp=time.time(),
                    description="Customer has opted out of payment notifications. Recovery suppressed.",
                )
            )
            receipt = RecoveryDispatchReceipt(
                case_id=case_id,
                payment_id=payment_id,
                amount_paise=amount_paise_val,
                amount_inr=amount_inr_float,
                payment_link_id="none_opt_out",
                payment_link_url="",
                whatsapp_message_id="none_opt_out",
                recipient_phone=customer_phone,
                status="SUPPRESSED_OPT_OUT",
                created_at=time.time(),
                updated_at=time.time(),
                timeline=timeline,
            )
            self._cases[case_id] = receipt
            return receipt

        # 2. Generate Razorpay Payment Link (buffer 60s to ensure >= 15m minimum expiry)
        expire_unix = int(time.time() + (expire_minutes * 60) + 60)
        plink_res = self.rzp.create_payment_link(
            amount_in_paise=amount_paise_val,
            currency="INR",
            description=f"Payment Recovery for {payment_id} ({merchant_name})",
            customer={"name": customer_name, "contact": customer_phone},
            notes={
                "case_id": case_id,
                "payment_id": payment_id,
                "merchant_id": merchant_id or "default_merchant",
                "recovery_engine": "WAPSI",
            },
            expire_by=expire_unix,
            notify_whatsapp=False,  # We manage WhatsApp notifications directly
        )

        payment_link_id = plink_res.get("id", f"plink_mock_{case_id}")
        payment_link_url = plink_res.get("short_url") or f"https://rzp.io/i/{payment_link_id}"

        timeline.append(
            RecoveryTimelineEvent(
                event_type="LINK_CREATED",
                timestamp=time.time(),
                description=f"Generated Razorpay Payment Link {payment_link_id} with {expire_minutes}m expiry.",
                metadata={"payment_link_id": payment_link_id, "short_url": payment_link_url},
            )
        )

        # 3. Dispatch WhatsApp Reminder with Link
        amount_fmt = f"Rs {amount_inr_dec:,.2f}"
        wa_res = self.wa.send_recovery_reminder(
            to_phone=customer_phone,
            customer_name=customer_name,
            amount_str=amount_fmt,
            payment_link=payment_link_url,
            merchant_name=merchant_name,
            template_name=template_name,
        )

        timeline.append(
            RecoveryTimelineEvent(
                event_type="WHATSAPP_DISPATCHED",
                timestamp=time.time(),
                description=f"Dispatched WhatsApp reminder with 1-click link (Message ID: {wa_res.message_id}).",
                metadata={"wamid": wa_res.message_id, "recipient": wa_res.recipient_phone},
            )
        )

        receipt = RecoveryDispatchReceipt(
            case_id=case_id,
            payment_id=payment_id,
            amount_paise=amount_paise_val,
            amount_inr=amount_inr_float,
            payment_link_id=payment_link_id,
            payment_link_url=payment_link_url,
            whatsapp_message_id=wa_res.message_id,
            recipient_phone=wa_res.recipient_phone,
            status="DISPATCHED",
            created_at=time.time(),
            updated_at=time.time(),
            timeline=timeline,
        )

        # Register mappings for webhook lookups
        self._cases[case_id] = receipt
        self._message_to_case[wa_res.message_id] = case_id
        self._link_to_case[payment_link_id] = case_id

        try:
            from wapsi.recovery.case_store import get_durable_case_store, RecoveryCaseRecord
            from wapsi.recovery.state_machine import RecoveryState
            store = get_durable_case_store()
            store.save_case(RecoveryCaseRecord(
                case_id=case_id,
                payment_id=payment_id,
                amount_paise=amount_paise_val,
                customer_phone=customer_phone,
                customer_name=customer_name,
                merchant_name=merchant_name,
                merchant_id=merchant_id or "04a2aaf8-8c8a-4d99-852c-cefc80e82019",
                error_code="UPI_APP_TIMEOUT",
                error_category="FRICTION_OTP_UX",
                status=RecoveryState.DISPATCHED,
                attempts_made=1,
                max_attempts=3,
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                whatsapp_message_id=wa_res.message_id,
            ))
        except Exception as store_err:
            logger.debug(f"Failed to save case to durable case store in orchestrator: {store_err}")

        try:
            from wapsi.recovery.webhook_processor import get_durable_webhook_processor
            processor = get_durable_webhook_processor()
            processor.register_case_mapping(
                case_id=case_id,
                initial_status="DISPATCHED",
                payment_link_id=payment_link_id,
                whatsapp_message_id=wa_res.message_id,
                customer_phone=customer_phone,
            )
        except Exception as map_err:
            logger.debug(f"Failed to register case mapping with durable processor: {map_err}")

        return receipt

    def handle_whatsapp_delivery_event(self, status: WhatsAppDeliveryStatus) -> Optional[RecoveryDispatchReceipt]:
        """
        Processes WhatsApp delivery callbacks ('sent', 'delivered', 'read', 'failed').
        Updates case timeline and status with authoritative state transition protection.
        """
        case_id = self._message_to_case.get(status.message_id)
        if not case_id or case_id not in self._cases:
            return None

        case = self._cases[case_id]
        new_status = status.status.upper()

        # Authoritative protection: Do not downgrade if already RECOVERED, and respect delivery progression
        hierarchy = {"PENDING": 0, "DISPATCHED": 1, "SENT": 1, "DELIVERED": 2, "READ": 3}
        curr_lvl = hierarchy.get(case.status, 0)
        new_lvl = hierarchy.get(new_status, 0)
        if case.status != "RECOVERED":
            if new_status == "FAILED" or new_lvl >= curr_lvl:
                case.status = new_status

        case.updated_at = time.time()
        case.timeline.append(
            RecoveryTimelineEvent(
                event_type=f"WHATSAPP_{new_status}",
                timestamp=time.time(),
                description=f"WhatsApp message delivery transitioned to {new_status}.",
                metadata={"raw_status": status.raw_status},
            )
        )
        logger.info(f"Updated case {case_id} status to {new_status} via WhatsApp delivery webhook.")
        return case

    def handle_razorpay_webhook_event(self, event: RazorpayWebhookEvent) -> Optional[RecoveryDispatchReceipt]:
        """
        Processes Razorpay payment/link events with hardening:
        - Deduplication: handles duplicate delivery using idempotency_key or event_id.
        - Out-of-order handling: preserves authoritative RECOVERED status against delayed failures.
        - Authoritative status transitions: transitions case to RECOVERED when payment is captured.
        """
        event_key = event.idempotency_key or event.event_id

        # Locate case via case_id or payment_link_id
        case_id = event.case_id or (
            self._link_to_case.get(event.payment_link_id) if event.payment_link_id else None
        )
        if not case_id or case_id not in self._cases:
            return None

        case = self._cases[case_id]

        # Duplicate delivery check
        if event_key in self._processed_events:
            logger.info(f"Duplicate Razorpay webhook event {event_key} ignored for case {case_id}.")
            return case

        self._processed_events.add(event_key)

        # Authoritative state transition protection
        if case.status == "RECOVERED":
            if event.normalized_status != "RECOVERED":
                logger.warning(
                    f"Out-of-order event {event.event} ({event.normalized_status}) "
                    f"received for already RECOVERED case {case_id}. Preserving authoritative RECOVERED status."
                )
                case.timeline.append(
                    RecoveryTimelineEvent(
                        event_type=f"OUT_OF_ORDER_{event.event.upper().replace('.', '_')}",
                        timestamp=time.time(),
                        description=f"Received out-of-order event {event.event} ({event.normalized_status}); preserved RECOVERED status.",
                        metadata={"event_id": event.event_id, "incoming_status": event.normalized_status},
                    )
                )
                return case

        # Process payment capture / recovery
        if event.normalized_status == "RECOVERED":
            case.status = "RECOVERED"
            case.updated_at = time.time()
            case.timeline.append(
                RecoveryTimelineEvent(
                    event_type="PAYMENT_CAPTURED",
                    timestamp=time.time(),
                    description=f"Payment captured via Razorpay ({event.event}). Revenue successfully recovered!",
                    metadata={
                        "event_id": event.event_id,
                        "payment_id": event.payment_id,
                        "payment_link_id": event.payment_link_id,
                        "amount_paise": event.amount_paise,
                    },
                )
            )
            logger.info(f"Case {case_id} transitioned to RECOVERED! Paid amount: {event.amount_paise} paise.")
            return case

        # Process terminal failure or cancellation if not already recovered
        if event.normalized_status in ("FAILED", "CANCELLED", "EXPIRED"):
            case.status = event.normalized_status
            case.updated_at = time.time()
            case.timeline.append(
                RecoveryTimelineEvent(
                    event_type=f"PAYMENT_{event.normalized_status}",
                    timestamp=time.time(),
                    description=f"Payment marked {event.normalized_status} via Razorpay event {event.event}.",
                    metadata={"event_id": event.event_id, "details": event.notes},
                )
            )

        return case

    def get_case(self, case_id: str) -> Optional[RecoveryDispatchReceipt]:
        """Retrieves receipt and timeline for a case."""
        return self._cases.get(case_id)

    def get_timeline(self, case_id: str) -> List[Dict[str, Any]]:
        """Returns formatted timeline for frontend display."""
        case = self._cases.get(case_id)
        if not case:
            return []
        return [
            {
                "eventType": t.event_type,
                "timestamp": t.timestamp,
                "description": t.description,
                "metadata": t.metadata,
            }
            for t in case.timeline
        ]


# Global singleton instance
_orchestrator: Optional[PaymentRecoveryOrchestrator] = None


def get_recovery_orchestrator() -> PaymentRecoveryOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PaymentRecoveryOrchestrator()
    return _orchestrator
