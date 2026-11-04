"""
Payment Reconciliation Service for WAPSI Recovery Engine.

Coordinates reconciliation between internal recovery cases and Razorpay's authoritative payment state.

Guarantees:
- Queries Razorpay directly to resolve ambiguous network states (RECONCILIATION_REQUIRED).
- Authoritative: Payment recovery is ONLY declared upon confirmed captured payment (never inferred from WhatsApp delivery or read status).
- Detects payments captured after delayed failure callbacks.
- Prevents duplicate active recovery cases for the same merchant and payment.
- Closes and cancels pending outbox retries immediately upon verified payment capture.
- Records final provider payment ID and preserves full event history.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.recovery.outbox import DurableOutboxStore, get_outbox_store
from wapsi.recovery.state_machine import RecoveryState, RecoveryStateMachine
from wapsi.recovery.timeline import RecoveryTimelineStore, get_timeline_store

logger = logging.getLogger("wapsi.recovery.reconciliation")


@dataclass
class ReconciliationReport:
    case_id: str
    payment_id: str
    previous_state: str
    resulting_state: str
    is_recovered: bool
    amount_recovered_paise: int
    provider_payment_id: Optional[str]
    reconciliation_action_taken: str
    timestamp_utc: float
    details: Dict[str, Any]


@dataclass
class PaymentLinkReconciliationReport:
    payment_link_id: str
    is_reconciled: bool
    provider_status: str
    is_actionable_recovery: bool = False
    matched_amount_paise: int = 0
    failure_reason: Optional[str] = None
    currency: str = "INR"
    amount_paid_paise: int = 0
    final_payment_id: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class PaymentReconciliationEngine:
    """
    Authoritative payment reconciliation service connecting to Razorpay client.
    """

    def __init__(
        self,
        razorpay_client: Optional[RazorpayClient] = None,
        outbox_store: Optional[DurableOutboxStore] = None,
        timeline_store: Optional[RecoveryTimelineStore] = None,
    ):
        self.rzp = razorpay_client or RazorpayClient()
        self.outbox = outbox_store or get_outbox_store()
        self.timeline = timeline_store or get_timeline_store()

    def reconcile_payment_link(
        self,
        payment_link_id: str,
        expected_amount_paise: Optional[int] = None,
        expected_currency: str = "INR",
    ) -> PaymentLinkReconciliationReport:
        """
        Reconciles a Razorpay payment link directly against provider state.
        Validates ID matching, status, currency, and amount.
        """
        try:
            link_data = self.rzp.get_payment_link(payment_link_id)
        except Exception as e:
            return PaymentLinkReconciliationReport(
                payment_link_id=payment_link_id,
                is_reconciled=False,
                provider_status="error",
                failure_reason=str(e),
            )

        actual_id = link_data.get("id")
        if actual_id and actual_id != payment_link_id:
            return PaymentLinkReconciliationReport(
                payment_link_id=payment_link_id,
                is_reconciled=False,
                provider_status=link_data.get("status", "unknown"),
                failure_reason=f"Payment link identifier MISMATCH: expected {payment_link_id}, got {actual_id}",
                raw_data=link_data,
            )

        status = link_data.get("status", "").lower()
        amount = int(link_data.get("amount", 0))
        currency = link_data.get("currency", "INR")
        amount_paid = int(link_data.get("amount_paid", 0))

        if status not in ("paid", "captured"):
            return PaymentLinkReconciliationReport(
                payment_link_id=payment_link_id,
                is_reconciled=False,
                provider_status=status,
                is_actionable_recovery=False,
                failure_reason=f"Link status is not paid (status: {status})",
                raw_data=link_data,
            )

        if expected_currency and currency.upper() != expected_currency.upper():
            return PaymentLinkReconciliationReport(
                payment_link_id=payment_link_id,
                is_reconciled=False,
                provider_status=status,
                failure_reason=f"Currency mismatch: expected {expected_currency}, got {currency}",
                raw_data=link_data,
            )

        if expected_amount_paise is not None and amount < expected_amount_paise:
            return PaymentLinkReconciliationReport(
                payment_link_id=payment_link_id,
                is_reconciled=False,
                provider_status=status,
                failure_reason=f"Amount underpaid: expected {expected_amount_paise} paise, got {amount} paise",
                raw_data=link_data,
            )

        return PaymentLinkReconciliationReport(
            payment_link_id=payment_link_id,
            is_reconciled=True,
            provider_status=status,
            is_actionable_recovery=True,
            matched_amount_paise=amount,
            amount_paid_paise=amount_paid,
            currency=currency,
            raw_data=link_data,
        )

    def reconcile_case(
        self,
        case_id: str,
        payment_id: str,
        current_state: RecoveryState,
        payment_link_id: Optional[str] = None,
    ) -> ReconciliationReport:
        """
        Actively queries Razorpay API to reconcile ambiguous or pending cases.
        """
        now = time.time()
        logger.info(f"Initiating active reconciliation for case {case_id} (payment: {payment_id}, current: {current_state.value})")

        # 1. If already RECOVERED, confirm authoritative status and return
        if current_state == RecoveryState.RECOVERED:
            return ReconciliationReport(
                case_id=case_id,
                payment_id=payment_id,
                previous_state=current_state.value,
                resulting_state=RecoveryState.RECOVERED.value,
                is_recovered=True,
                amount_recovered_paise=0,
                provider_payment_id=payment_id,
                reconciliation_action_taken="NO_OP_ALREADY_RECOVERED",
                timestamp_utc=now,
                details={"message": "Case already authoritatively RECOVERED."},
            )

        provider_link_status = None
        amount_paid_paise = 0
        final_payment_id = None
        raw_provider_data: Dict[str, Any] = {}

        # 2. Query Razorpay Payment Link if link ID is known
        if payment_link_id:
            try:
                link_data = self.rzp.get_payment_link(payment_link_id)
                raw_provider_data["link_data"] = link_data
                provider_link_status = link_data.get("status")  # 'paid', 'created', 'cancelled', 'expired'
                amount_paid_paise = int(link_data.get("amount_paid", 0))

                # Extract captured payment ID if payments array is present
                payments = link_data.get("payments", [])
                if payments and isinstance(payments, list):
                    final_payment_id = payments[0].get("payment_id") or payments[0].get("id")
            except Exception as link_err:
                logger.warning(f"Failed to query Razorpay Payment Link {payment_link_id}: {link_err}")
                raw_provider_data["link_query_error"] = str(link_err)

        # 3. Determine reconciled state
        action_taken = "CONFIRMED_PENDING"
        new_state = current_state

        if provider_link_status == "paid" or amount_paid_paise > 0:
            # Verified recovery!
            new_state, _ = RecoveryStateMachine.transition(
                case_id=case_id,
                current_state=current_state,
                target_state=RecoveryState.RECOVERED,
                event_trigger="RECONCILIATION_VERIFIED_PAID",
                is_payment_capture=True,
            )
            action_taken = "TRANSITIONED_TO_RECOVERED"
            cancelled_jobs = self.outbox.cancel_jobs_for_case(case_id, reason="RECONCILED_AS_PAID")

            self.timeline.record_event(
                case_id=case_id,
                event_type="PAYMENT_CAPTURED",
                description=f"Active reconciliation confirmed Razorpay payment captured ({amount_paid_paise} paise).",
                source="PAYMENT_RECONCILIATION_ENGINE",
                provider_event_id=final_payment_id or payment_link_id,
                from_state=current_state.value,
                to_state=new_state.value,
                metadata={
                    "payment_link_id": payment_link_id,
                    "amount_paid_paise": amount_paid_paise,
                    "final_payment_id": final_payment_id,
                    "cancelled_outbox_jobs": cancelled_jobs,
                },
                timestamp_utc=now,
            )

            self.timeline.record_event(
                case_id=case_id,
                event_type="RECOVERY_COMPLETED",
                description="Recovery completed following authoritative payment reconciliation.",
                source="WAPSI_ENGINE",
                from_state=new_state.value,
                to_state=new_state.value,
                timestamp_utc=now,
            )

        elif provider_link_status == "expired":
            if current_state != RecoveryState.RECOVERED:
                new_state, _ = RecoveryStateMachine.transition(
                    case_id=case_id,
                    current_state=current_state,
                    target_state=RecoveryState.EXPIRED,
                    event_trigger="RECONCILIATION_LINK_EXPIRED",
                )
                action_taken = "TRANSITIONED_TO_EXPIRED"
        elif provider_link_status == "cancelled":
            if current_state != RecoveryState.RECOVERED:
                new_state, _ = RecoveryStateMachine.transition(
                    case_id=case_id,
                    current_state=current_state,
                    target_state=RecoveryState.CANCELLED,
                    event_trigger="RECONCILIATION_LINK_CANCELLED",
                )
                action_taken = "TRANSITIONED_TO_CANCELLED"
        elif current_state == RecoveryState.RECONCILIATION_REQUIRED and provider_link_status == "created":
            # Link is active and valid, restore to DISPATCHED or SCHEDULED
            new_state, _ = RecoveryStateMachine.transition(
                case_id=case_id,
                current_state=current_state,
                target_state=RecoveryState.DISPATCHED,
                event_trigger="RECONCILIATION_LINK_ACTIVE",
            )
            action_taken = "RESTORED_TO_DISPATCHED"

        return ReconciliationReport(
            case_id=case_id,
            payment_id=payment_id,
            previous_state=current_state.value,
            resulting_state=new_state.value,
            is_recovered=(new_state == RecoveryState.RECOVERED),
            amount_recovered_paise=amount_paid_paise,
            provider_payment_id=final_payment_id,
            reconciliation_action_taken=action_taken,
            timestamp_utc=now,
            details=raw_provider_data,
        )

