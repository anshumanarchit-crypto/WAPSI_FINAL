"""
Autonomous Background Recovery Worker for WAPSI Recovery Engine.

Coordinates outbox job execution, provider dispatches, and lease lifecycle:
1. Atomically claims pending or abandoned outbox jobs.
2. Rechecks customer opt-out status immediately before every dispatch.
3. Rechecks payment capture status to prevent sending messages for already-paid transactions.
4. Generates Razorpay payment links in integer paise (Mode A: Action Specification payloads).
5. Dispatches pre-formed Meta WhatsApp Cloud API payloads verbatim (Mode B: Direct Payload).
6. Dispatches WhatsApp recovery nudges using Meta Cloud API.
7. Handles ambiguous network timeouts via RECONCILIATION_REQUIRED.
8. Distinguishes permanent errors (DEAD_LETTER) from transient retryable errors.
9. Supports graceful shutdown and single-batch testing mode.

Payload Mode Detection:
- Mode B (Pre-Formed Direct Dispatch): payload contains 'messaging_product'=='whatsapp',
  'recipient_type'=='individual', 'to', and 'text' or 'template'. Dispatched verbatim.
- Mode A (Action Specification): all other payloads — JIT Razorpay link generation.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import (
    WhatsAppAuthError,
    WhatsAppClient,
    WhatsAppDeliveryError,
    WhatsAppError,
    WhatsAppRateLimitError,
)
from wapsi.recovery.opt_out_store import PersistentOptOutStore, get_persistent_opt_out_store
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, get_outbox_store
from wapsi.recovery.state_machine import RecoveryState, RecoveryStateMachine
from wapsi.recovery.timeline import RecoveryTimelineStore, get_timeline_store

logger = logging.getLogger("wapsi.recovery.worker")


@dataclass
class JobExecutionResult:
    job_id: str
    case_id: str
    status: str  # 'COMPLETED', 'RETRIED', 'DEAD_LETTER', 'RECONCILIATION_REQUIRED', 'SUPPRESSED'
    payment_link_id: Optional[str] = None
    payment_link_url: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    error_message: Optional[str] = None


class RecoveryBackgroundWorker:
    """
    Background worker that leases and executes outbox recovery dispatches.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        outbox_store: Optional[DurableOutboxStore] = None,
        opt_out_store: Optional[PersistentOptOutStore] = None,
        timeline_store: Optional[RecoveryTimelineStore] = None,
        razorpay_client: Optional[RazorpayClient] = None,
        whatsapp_client: Optional[WhatsAppClient] = None,
        lease_duration_seconds: int = 60,
    ):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.outbox = outbox_store or get_outbox_store()
        self.opt_out = opt_out_store or get_persistent_opt_out_store()
        self.timeline = timeline_store or get_timeline_store()
        self.rzp = razorpay_client or RazorpayClient()
        self.wa = whatsapp_client or WhatsAppClient()
        self.lease_duration_seconds = lease_duration_seconds
        self._is_running: bool = False

    # ------------------------------------------------------------------
    # Internal helpers: payload mode detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_direct_meta_payload(payload: Dict[str, Any]) -> bool:
        """
        Returns True when the payload is a pre-formed Meta WhatsApp Cloud API message object
        (Mode B: Direct Payload).  Detection criteria (all must be true):
          - payload is a dict
          - 'messaging_product' == 'whatsapp'
          - 'recipient_type' == 'individual'
          - 'to' is a non-empty string
          - at least one of 'text' or 'template' is present
        """
        return (
            isinstance(payload, dict)
            and payload.get("messaging_product") == "whatsapp"
            and payload.get("recipient_type") == "individual"
            and bool(payload.get("to"))
            and ("text" in payload or "template" in payload)
        )

    # ------------------------------------------------------------------
    # Public dispatch entry-point
    # ------------------------------------------------------------------

    def process_single_job(self, job: OutboxJob) -> JobExecutionResult:
        """
        Executes a claimed outbox recovery job with strict pre-dispatch verification.

        Supports two payload modes:

        Mode B — Pre-Formed Direct Dispatch:
            The outbox payload is a complete Meta WhatsApp Cloud API message object
            (messaging_product='whatsapp', recipient_type='individual', 'to', 'text'/'template').
            Dispatched verbatim via send_prepared_payload(); NO Razorpay link is created.

        Mode A — Action Specification:
            The outbox payload is an internal spec (customer_phone, amount_paise, etc.).
            A Razorpay payment link is created JIT and the reminder is sent via
            send_recovery_reminder().

        The authorization gate and timeline recording apply to BOTH modes without exception.
        """
        case_id = job.case_id
        payload = job.message_payload

        logger.info(f"Worker {self.worker_id} executing outbox job {job.id} for case {case_id}")

        # --- Authorization Gate (applies to BOTH modes — no bypass) ---
        is_auth, auth_err = self.outbox.verify_dispatch_authorization(job, opt_out_store=self.opt_out)
        if not is_auth:
            logger.error(f"Pre-dispatch authorization verification failed for job {job.id}: {auth_err}")
            self.outbox.fail_job(
                job.id, self.worker_id,
                f"AUTHORIZATION_REJECTED: {auth_err}",
                is_retryable=False, merchant_id=job.merchant_id,
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="DISPATCH_AUTHORIZATION_FAILED",
                description=f"Outbox dispatch rejected: {auth_err}",
                source="RECOVERY_WORKER",
                from_state="DISPATCHING",
                to_state="BLOCKED_APPROVAL",
                metadata={"reason": auth_err, "job_id": job.id},
            )
            return JobExecutionResult(
                job_id=job.id,
                case_id=case_id,
                status="DEAD_LETTER",
                error_message=f"Authorization rejected: {auth_err}",
            )

        # Record timeline: claimed
        self.timeline.record_event(
            case_id=case_id,
            event_type="RECOVERY_CLAIMED",
            description=f"Worker {self.worker_id} acquired lease on recovery outbox job.",
            source="RECOVERY_WORKER",
            attempt_number=job.retry_count + 1,
            from_state="SCHEDULED",
            to_state="DISPATCHING",
            metadata={"worker_id": self.worker_id, "job_id": job.id},
        )

        # --- Mode Detection ---
        if self._is_direct_meta_payload(payload):
            logger.info(f"Job {job.id}: Mode B detected — pre-formed Meta WhatsApp Cloud API payload.")
            return self._execute_direct_payload_job(job, payload)
        else:
            logger.info(f"Job {job.id}: Mode A detected — Action Specification payload.")
            return self._execute_action_spec_job(job, payload)

    # ------------------------------------------------------------------
    # Mode B: Pre-Formed Direct Payload
    # ------------------------------------------------------------------

    def _execute_direct_payload_job(self, job: OutboxJob, payload: Dict[str, Any]) -> JobExecutionResult:
        """
        MODE B — Dispatches a pre-formed, operator-approved Meta WhatsApp Cloud API payload verbatim.

        Does NOT create any Razorpay payment link.  If the idempotency key encodes an existing
        payment link ID (plink_...), validates that link via a read-only GET before dispatch.
        Dispatches exactly the approved payload content with no modifications other than phone
        number normalization.
        """
        case_id = job.case_id
        payment_id = job.payment_id
        raw_recipient = payload.get("to", "")

        # 1. Validate and normalize recipient phone
        try:
            normalized_recipient = WhatsAppClient.sanitize_phone_number(raw_recipient)
        except Exception as phone_err:
            logger.error(f"Direct payload job {job.id}: invalid recipient phone: {phone_err}")
            self.outbox.fail_job(
                job.id, self.worker_id,
                f"INVALID_RECIPIENT: {phone_err}",
                is_retryable=False, merchant_id=job.merchant_id,
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="DEAD_LETTER",
                error_message=f"Invalid recipient: {phone_err}",
            )

        # 2. Pre-dispatch opt-out check on normalized recipient
        if self.opt_out.is_opted_out(normalized_recipient):
            logger.warning(f"Direct payload job {job.id}: recipient opted out pre-dispatch.")
            self.outbox.cancel_jobs_for_case(
                case_id, reason="CUSTOMER_OPTED_OUT_PRE_DISPATCH", merchant_id=job.merchant_id,
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="CUSTOMER_OPTED_OUT",
                description="Recipient opted out prior to direct payload dispatch. Suppressed.",
                source="RECOVERY_WORKER",
                from_state="DISPATCHING",
                to_state="SUPPRESSED_OPT_OUT",
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="SUPPRESSED",
                error_message="Customer opted out prior to dispatch.",
            )

        # 3. Resolve existing payment link ID from idempotency key (read-only, no creation)
        payment_link_id: Optional[str] = None
        payment_link_url: Optional[str] = None
        idemp_key = job.idempotency_key or ""
        plink_match = re.search(r"(plink_[A-Za-z0-9]+)", idemp_key)

        if plink_match:
            payment_link_id = plink_match.group(1)
            logger.info(
                f"Direct payload job {job.id}: resolved existing payment link "
                f"{payment_link_id} from idempotency key."
            )

            # 4. Validate existing link via read-only GET — no mutations allowed
            try:
                link_data = self.rzp.get_payment_link(payment_link_id)
                link_amount = link_data.get("amount", 0)
                link_currency = (link_data.get("currency") or "").upper()
                link_status = link_data.get("status", "")
                link_amount_paid = link_data.get("amount_paid", -1)
                link_short_url = link_data.get("short_url", "")
                link_expired = link_data.get("expired", False)

                validation_errors: List[str] = []
                if link_currency != "INR":
                    validation_errors.append(f"Expected INR currency, got {link_currency!r}")
                if link_status != "created":
                    validation_errors.append(f"Expected status 'created', got {link_status!r}")
                if link_amount_paid != 0:
                    validation_errors.append(f"Link already has payments: {link_amount_paid} paise")
                if link_expired:
                    validation_errors.append("Payment link is expired")
                if link_amount <= 0:
                    validation_errors.append(f"Payment link amount invalid: {link_amount}")

                # Verify the approved message text contains the verified short URL (prevents URL swap)
                if payload.get("type") == "text":
                    approved_text = (payload.get("text") or {}).get("body", "")
                    if link_short_url and approved_text and link_short_url not in approved_text:
                        validation_errors.append(
                            f"Approved message body does not contain verified link URL {link_short_url!r}"
                        )

                if validation_errors:
                    err_msg = (
                        f"Payment link {payment_link_id} validation failed: "
                        + "; ".join(validation_errors)
                    )
                    logger.error(f"Direct payload job {job.id}: {err_msg}")
                    self.outbox.fail_job(
                        job.id, self.worker_id, err_msg,
                        is_retryable=False, merchant_id=job.merchant_id,
                    )
                    self.timeline.record_event(
                        case_id=case_id,
                        event_type="PAYMENT_LINK_VALIDATION_FAILED",
                        description=err_msg,
                        source="RECOVERY_WORKER",
                        from_state="DISPATCHING",
                        to_state="BLOCKED_APPROVAL",
                    )
                    return JobExecutionResult(
                        job_id=job.id, case_id=case_id,
                        status="DEAD_LETTER",
                        error_message=err_msg,
                    )

                payment_link_url = link_short_url
                logger.info(
                    f"Direct payload job {job.id}: payment link {payment_link_id} validated OK "
                    f"({link_amount} paise, status={link_status!r})."
                )

            except httpx.TimeoutException as link_timeout:
                logger.error(
                    f"Direct payload job {job.id}: timeout validating payment link "
                    f"{payment_link_id}: {link_timeout}"
                )
                self.outbox.mark_reconciliation_required(
                    job.id, self.worker_id, str(link_timeout), merchant_id=job.merchant_id,
                )
                return JobExecutionResult(
                    job_id=job.id, case_id=case_id,
                    status="RECONCILIATION_REQUIRED",
                    payment_link_id=payment_link_id,
                    error_message=str(link_timeout),
                )
            except Exception as link_err:
                logger.error(
                    f"Direct payload job {job.id}: error validating payment link: {link_err}"
                )
                self.outbox.fail_job(
                    job.id, self.worker_id,
                    f"PAYMENT_LINK_VALIDATION_ERROR: {link_err}",
                    is_retryable=True, backoff_seconds=120, merchant_id=job.merchant_id,
                )
                return JobExecutionResult(
                    job_id=job.id, case_id=case_id,
                    status="RETRIED",
                    payment_link_id=payment_link_id,
                    error_message=str(link_err),
                )

        # 5. Dispatch pre-formed payload verbatim (NO content modification)
        try:
            wa_res = self.wa.send_prepared_payload(payload)

            self.timeline.record_event(
                case_id=case_id,
                event_type="WHATSAPP_DISPATCHED",
                description=f"Direct payload dispatched (wamid: {wa_res.message_id}).",
                source="RECOVERY_WORKER",
                provider_event_id=wa_res.message_id,
                attempt_number=job.retry_count + 1,
                from_state="DISPATCHING",
                to_state="DISPATCHED",
                metadata={
                    "recipient": wa_res.recipient_phone,
                    "wamid": wa_res.message_id,
                    "payment_link_id": payment_link_id,
                    "mode": "direct_payload",
                },
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="WHATSAPP_ACCEPTED",
                description="Direct payload accepted by Meta Cloud API.",
                source="META_CLOUD_API",
                provider_event_id=wa_res.message_id,
                metadata={"status": wa_res.status},
            )

            self.outbox.complete_job(
                job.id, self.worker_id,
                {"wamid": wa_res.message_id, "plink": payment_link_id, "mode": "direct_payload"},
                merchant_id=job.merchant_id,
            )

            return JobExecutionResult(
                job_id=job.id,
                case_id=case_id,
                status="COMPLETED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                whatsapp_message_id=wa_res.message_id,
            )

        except (httpx.TimeoutException, httpx.NetworkError) as net_timeout:
            logger.error(
                f"Ambiguous network timeout during direct payload dispatch for case {case_id}: {net_timeout}"
            )
            self.outbox.mark_reconciliation_required(
                job.id, self.worker_id, str(net_timeout), merchant_id=job.merchant_id,
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="RECONCILIATION_REQUIRED",
                description="Ambiguous network timeout during direct payload dispatch.",
                source="RECOVERY_WORKER",
                from_state="DISPATCHING",
                to_state="RECONCILIATION_REQUIRED",
                metadata={"error": str(net_timeout)},
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="RECONCILIATION_REQUIRED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(net_timeout),
            )

        except WhatsAppRateLimitError as rate_err:
            logger.warning(f"WhatsApp rate limited on direct payload for case {case_id}: {rate_err}")
            self.outbox.fail_job(
                job.id, self.worker_id, str(rate_err),
                is_retryable=True, backoff_seconds=300, merchant_id=job.merchant_id,
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="RETRIED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(rate_err),
            )

        except WhatsAppDeliveryError as deliv_err:
            logger.error(
                f"Permanent WhatsApp delivery rejection on direct payload for case {case_id}: {deliv_err}"
            )
            self.outbox.fail_job(
                job.id, self.worker_id, str(deliv_err),
                is_retryable=False, merchant_id=job.merchant_id,
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="RECOVERY_FAILED",
                description=f"Permanent delivery rejection: {deliv_err}",
                source="RECOVERY_WORKER",
                from_state="DISPATCHING",
                to_state="FAILED",
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="DEAD_LETTER",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(deliv_err),
            )

        except Exception as general_err:
            logger.error(
                f"Unexpected error in direct payload dispatch for job {job.id}: {general_err}"
            )
            self.outbox.fail_job(
                job.id, self.worker_id, str(general_err),
                is_retryable=True, backoff_seconds=180, merchant_id=job.merchant_id,
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="RETRIED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(general_err),
            )

    # ------------------------------------------------------------------
    # Mode A: Action Specification (original flow, preserved exactly)
    # ------------------------------------------------------------------

    def _execute_action_spec_job(self, job: OutboxJob, payload: Dict[str, Any]) -> JobExecutionResult:
        """
        MODE A — Action Specification payload.

        Executes the original JIT Razorpay link generation and send_recovery_reminder() flow.
        Adds one fail-safe: if amount_paise <= 0 AND no existing or idempotency-key-encoded
        link ID exists, the job is immediately DEAD_LETTER rather than entering infinite retry.
        """
        case_id = job.case_id
        payment_id = job.payment_id
        customer_phone = payload.get("customer_phone", "")
        amount_paise = int(payload.get("amount_paise", 0))
        customer_name = payload.get("customer_name", "Valued Customer")
        merchant_name = payload.get("merchant_name", "Merchant")
        merchant_id = payload.get("merchant_id", "default_merchant")
        template_name = payload.get("template_name")
        language_code = payload.get("language_code", "en")
        components = payload.get("components")
        enforce_24h_window = payload.get("enforce_24h_window")
        inbound_timestamp = payload.get("inbound_timestamp")
        expire_minutes = int(payload.get("expire_minutes", 15))

        # Re-check customer opt-out immediately before dispatch
        if customer_phone and self.opt_out.is_opted_out(customer_phone):
            logger.warning(f"Pre-dispatch opt-out check failed for case {case_id}: customer opted out.")
            self.outbox.cancel_jobs_for_case(
                case_id, reason="CUSTOMER_OPTED_OUT_PRE_DISPATCH", merchant_id=job.merchant_id,
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="CUSTOMER_OPTED_OUT",
                description="Worker verified customer opted out prior to dispatch. Action suppressed.",
                source="RECOVERY_WORKER",
                from_state="DISPATCHING",
                to_state="SUPPRESSED_OPT_OUT",
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="SUPPRESSED",
                error_message="Customer opted out prior to dispatch.",
            )

        # Check or create Razorpay Payment Link
        existing_link_id = payload.get("payment_link_id")
        existing_link_url = payload.get("payment_link_url")

        # Fallback: attempt to resolve link ID from idempotency key if not in payload
        if not existing_link_id:
            idemp_key = job.idempotency_key or ""
            plink_match = re.search(r"(plink_[A-Za-z0-9]+)", idemp_key)
            if plink_match:
                existing_link_id = plink_match.group(1)
                logger.info(
                    f"Action spec job {job.id}: resolved existing link "
                    f"{existing_link_id} from idempotency key."
                )

        payment_link_id = existing_link_id
        payment_link_url = existing_link_url

        if not payment_link_id:
            # Fail-safe: refuse to create a link if amount is invalid — prevents infinite retry
            if amount_paise <= 0:
                err_msg = (
                    f"Cannot create payment link: amount_paise is {amount_paise} "
                    "and no existing link ID found."
                )
                logger.error(f"Action spec job {job.id}: {err_msg}")
                self.outbox.fail_job(
                    job.id, self.worker_id, err_msg,
                    is_retryable=False, merchant_id=job.merchant_id,
                )
                return JobExecutionResult(
                    job_id=job.id, case_id=case_id,
                    status="DEAD_LETTER",
                    error_message=err_msg,
                )

            try:
                expire_unix = int(time.time() + (expire_minutes * 60) + 60)
                plink_res = self.rzp.create_payment_link(
                    amount_in_paise=amount_paise,
                    currency="INR",
                    description=f"Payment Recovery for {payment_id} ({merchant_name})",
                    customer={"name": customer_name, "contact": customer_phone},
                    notes={
                        "case_id": case_id,
                        "payment_id": payment_id,
                        "merchant_id": merchant_id,
                        "recovery_engine": "WAPSI",
                    },
                    expire_by=expire_unix,
                    notify_whatsapp=False,
                )
                payment_link_id = plink_res.get("id")
                payment_link_url = plink_res.get("short_url") or f"https://rzp.io/i/{payment_link_id}"

                self.timeline.record_event(
                    case_id=case_id,
                    event_type="PAYMENT_LINK_CREATED",
                    description=f"Created Razorpay Payment Link {payment_link_id} with {expire_minutes}m expiry.",
                    source="RECOVERY_WORKER",
                    provider_event_id=payment_link_id,
                    metadata={"short_url": payment_link_url, "amount_paise": amount_paise},
                )
            except httpx.TimeoutException as timeout_err:
                # Ambiguous network outcome during payment link creation: do not blindly recreate!
                logger.error(f"Network timeout during Razorpay link creation for case {case_id}: {timeout_err}")
                self.outbox.mark_reconciliation_required(
                    job.id, self.worker_id, str(timeout_err), merchant_id=job.merchant_id,
                )
                self.timeline.record_event(
                    case_id=case_id,
                    event_type="RECONCILIATION_REQUIRED",
                    description="Network timeout contacting Razorpay. Flagged for status reconciliation.",
                    source="RECOVERY_WORKER",
                    from_state="DISPATCHING",
                    to_state="RECONCILIATION_REQUIRED",
                    metadata={"error": str(timeout_err)},
                )
                return JobExecutionResult(
                    job_id=job.id, case_id=case_id,
                    status="RECONCILIATION_REQUIRED",
                    error_message=str(timeout_err),
                )
            except Exception as rzp_err:
                logger.error(f"Razorpay link creation failed for case {case_id}: {rzp_err}")
                self.outbox.fail_job(
                    job.id, self.worker_id, str(rzp_err),
                    is_retryable=True, backoff_seconds=120, merchant_id=job.merchant_id,
                )
                return JobExecutionResult(
                    job_id=job.id, case_id=case_id,
                    status="RETRIED",
                    error_message=str(rzp_err),
                )

        # Dispatch WhatsApp Notification
        amount_inr_dec = Decimal(amount_paise) / Decimal(100)
        amount_fmt = f"Rs {amount_inr_dec:,.2f}"

        try:
            wa_res = self.wa.send_recovery_reminder(
                to_phone=customer_phone,
                customer_name=customer_name,
                amount_str=amount_fmt,
                payment_link=payment_link_url or "",
                merchant_name=merchant_name,
                template_name=template_name,
                language_code=language_code,
                components=components,
                enforce_24h_window=enforce_24h_window,
                inbound_timestamp=inbound_timestamp,
            )

            # Record timeline: dispatched & accepted
            self.timeline.record_event(
                case_id=case_id,
                event_type="WHATSAPP_DISPATCHED",
                description=f"Outbound WhatsApp reminder dispatched (Message ID: {wa_res.message_id}).",
                source="RECOVERY_WORKER",
                provider_event_id=wa_res.message_id,
                attempt_number=job.retry_count + 1,
                from_state="DISPATCHING",
                to_state="DISPATCHED",
                metadata={"recipient": wa_res.recipient_phone, "wamid": wa_res.message_id},
            )

            self.timeline.record_event(
                case_id=case_id,
                event_type="WHATSAPP_ACCEPTED",
                description="Message accepted into Meta Cloud API delivery pipeline.",
                source="META_CLOUD_API",
                provider_event_id=wa_res.message_id,
                metadata={"status": wa_res.status},
            )

            # Mark outbox job completed under merchant tenant context
            self.outbox.complete_job(
                job.id,
                self.worker_id,
                {"wamid": wa_res.message_id, "plink": payment_link_id},
                merchant_id=job.merchant_id,
            )

            return JobExecutionResult(
                job_id=job.id,
                case_id=case_id,
                status="COMPLETED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                whatsapp_message_id=wa_res.message_id,
            )

        except (httpx.TimeoutException, httpx.NetworkError) as net_timeout:
            # Ambiguous delivery outcome: Meta may or may not have sent the message
            logger.error(f"Ambiguous network timeout during WhatsApp dispatch for case {case_id}: {net_timeout}")
            self.outbox.mark_reconciliation_required(
                job.id, self.worker_id, str(net_timeout), merchant_id=job.merchant_id,
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="RECONCILIATION_REQUIRED",
                description="Network timeout during WhatsApp dispatch. Flagged for status reconciliation.",
                source="RECOVERY_WORKER",
                from_state="DISPATCHING",
                to_state="RECONCILIATION_REQUIRED",
                metadata={"error": str(net_timeout)},
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="RECONCILIATION_REQUIRED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(net_timeout),
            )

        except WhatsAppRateLimitError as rate_err:
            # Rate limited: retry with backoff
            logger.warning(f"WhatsApp rate limited for case {case_id}: {rate_err}")
            self.outbox.fail_job(
                job.id, self.worker_id, str(rate_err),
                is_retryable=True, backoff_seconds=300, merchant_id=job.merchant_id,
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="RETRIED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(rate_err),
            )

        except WhatsAppDeliveryError as deliv_err:
            # Permanent delivery rejection (e.g. invalid phone number): do not retry endlessly -> DEAD_LETTER
            logger.error(f"WhatsApp delivery rejection for case {case_id}: {deliv_err}")
            self.outbox.fail_job(
                job.id, self.worker_id, str(deliv_err),
                is_retryable=False, merchant_id=job.merchant_id,
            )
            self.timeline.record_event(
                case_id=case_id,
                event_type="RECOVERY_FAILED",
                description=f"Permanent WhatsApp delivery error: {deliv_err}",
                source="RECOVERY_WORKER",
                from_state="DISPATCHING",
                to_state="FAILED",
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="DEAD_LETTER",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(deliv_err),
            )

        except Exception as general_err:
            logger.error(f"Unexpected error executing outbox job {job.id}: {general_err}")
            self.outbox.fail_job(
                job.id, self.worker_id, str(general_err),
                is_retryable=True, backoff_seconds=180, merchant_id=job.merchant_id,
            )
            return JobExecutionResult(
                job_id=job.id, case_id=case_id,
                status="RETRIED",
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                error_message=str(general_err),
            )

    def process_single_job_by_id(
        self,
        job_id: str,
        merchant_id: Optional[str] = None,
    ) -> JobExecutionResult:
        """
        Atomically claims ONLY the specified job_id and executes it with pre-dispatch verification.
        Guarantees exact-job dispatch isolation: will NEVER claim or dispatch any other job.
        """
        job = self.outbox.claim_job_by_id(
            job_id=job_id,
            worker_id=self.worker_id,
            lease_duration_seconds=self.lease_duration_seconds,
            merchant_id=merchant_id,
        )
        if not job:
            logger.warning(
                f"Worker {self.worker_id} could not claim exact job {job_id} "
                "(job not eligible, unapproved, non-existent, or locked by another worker)."
            )
            return JobExecutionResult(
                job_id=job_id,
                case_id="",
                status="UNCLAIMED",
                error_message="Job not eligible for claim (unapproved, non-existent, or active lease held).",
            )

        return self.process_single_job(job)

    def process_batch(self, batch_size: int = 10) -> List[JobExecutionResult]:
        """Claims and executes a single batch of available jobs."""
        claimed = self.outbox.claim_jobs(
            worker_id=self.worker_id,
            limit=batch_size,
            lease_duration_seconds=self.lease_duration_seconds,
        )
        results: List[JobExecutionResult] = []
        for job in claimed:
            res = self.process_single_job(job)
            results.append(res)
        return results

    def stop(self) -> None:
        """Signals worker to gracefully stop."""
        self._is_running = False
        logger.info(f"Worker {self.worker_id} received stop signal.")

    def release_lease(self, job_id: str, merchant_id: Optional[str] = None) -> bool:
        """Releases an undispatched lease held by this worker."""
        return self.outbox.release_lease(job_id, self.worker_id, merchant_id=merchant_id)

    def release_leases(
        self,
        merchant_id: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
    ) -> int:
        """Releases all undispatched leases held by this worker, optionally excluding in-flight IDs."""
        return self.outbox.release_leases_for_worker(
            self.worker_id,
            merchant_id=merchant_id,
            exclude_job_ids=exclude_job_ids,
        )

    def reclaim_expired_leases(
        self,
        max_reclaim: int = 50,
        current_time: Optional[float] = None,
        merchant_id: Optional[str] = None,
    ) -> int:
        """Reclaims expired leases from crashed/abandoned workers."""
        return self.outbox.reclaim_expired_leases(
            current_time=current_time,
            max_reclaim=max_reclaim,
            merchant_id=merchant_id,
        )

    def count_active_leases(
        self,
        current_time: Optional[float] = None,
        merchant_id: Optional[str] = None,
    ) -> int:
        """Counts active leases currently held by this worker."""
        return self.outbox.count_active_leases(
            worker_id=self.worker_id,
            current_time=current_time,
            merchant_id=merchant_id,
        )

