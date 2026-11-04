"""
Unified Event-Driven Autonomous Payment Recovery Engine for WAPSI.

Coordinates the end-to-end payment recovery lifecycle:
1. Candidate ingestion & deterministic eligibility evaluation.
2. Intelligent timezone-aware scheduling and bounded retry policies.
3. Durable outbox queueing with atomic worker leases.
4. Background outbound execution (Razorpay Payment Links + WhatsApp Meta Cloud API).
5. Durable multi-provider webhook ingestion and deduplication.
6. Authoritative payment reconciliation.
7. Persistent opt-out governance and regulatory compliance.
8. Tamper-evident 16-milestone timeline audit trail.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Union

from wapsi.integrations.orchestration.recovery_orchestrator import parse_monetary_amount
from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import WhatsAppClient
from wapsi.recovery.eligibility import (
    EligibilityEvaluationContext,
    EligibilityStatus,
    RecoveryEligibilityEngine,
    RecoveryEligibilityResult,
)
from wapsi.recovery.opt_out_store import PersistentOptOutStore, get_persistent_opt_out_store
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, get_outbox_store
from wapsi.recovery.reconciliation import PaymentReconciliationEngine, ReconciliationReport
from wapsi.recovery.scheduler import RecoverySchedulePolicy, RecoveryScheduler, ScheduledRecoveryAction
from wapsi.recovery.state_machine import RecoveryState, RecoveryStateMachine
from wapsi.recovery.timeline import RecoveryTimelineStore, TimelineEvent, get_timeline_store
from wapsi.recovery.webhook_processor import (
    DurableWebhookEventProcessor,
    DurableWebhookInbox,
    WebhookProcessingResult,
    get_durable_webhook_processor,
)
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker

logger = logging.getLogger("wapsi.recovery.engine")


@dataclass
class RecoveryCaseRecord:
    case_id: str
    payment_id: str
    amount_paise: int
    customer_phone: str
    customer_name: str
    merchant_name: str
    merchant_id: str
    error_code: str
    error_category: str
    status: RecoveryState
    attempts_made: int
    max_attempts: int
    payment_link_id: Optional[str] = None
    payment_link_url: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    created_at_utc: float = field(default_factory=time.time)
    updated_at_utc: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "payment_id": self.payment_id,
            "amount_paise": self.amount_paise,
            "amount_inr": float(Decimal(self.amount_paise) / Decimal(100)),
            "customer_phone": f"{self.customer_phone[:4]}***{self.customer_phone[-2:]}" if len(self.customer_phone) >= 6 else "***",
            "customer_name": self.customer_name,
            "merchant_name": self.merchant_name,
            "merchant_id": self.merchant_id,
            "error_code": self.error_code,
            "error_category": self.error_category,
            "status": self.status.value,
            "attempts_made": self.attempts_made,
            "max_attempts": self.max_attempts,
            "payment_link_id": self.payment_link_id,
            "payment_link_url": self.payment_link_url,
            "whatsapp_message_id": self.whatsapp_message_id,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
        }


class PaymentRecoveryEngine:
    """
    Central orchestration engine for event-driven payment recovery.
    """

    def __init__(
        self,
        razorpay_client: Optional[RazorpayClient] = None,
        whatsapp_client: Optional[WhatsAppClient] = None,
        outbox_store: Optional[DurableOutboxStore] = None,
        timeline_store: Optional[RecoveryTimelineStore] = None,
        opt_out_store: Optional[PersistentOptOutStore] = None,
        scheduler_policy: Optional[RecoverySchedulePolicy] = None,
        database_manager: Optional[Any] = None,
        webhook_processor: Optional[DurableWebhookEventProcessor] = None,
    ):
        mgr = database_manager
        if mgr is None:
            from wapsi.db.session import get_db_manager
            try:
                mgr = get_db_manager()
            except Exception:
                mgr = None
        self.db_manager = mgr
        self.rzp = razorpay_client or RazorpayClient()
        self.wa = whatsapp_client or WhatsAppClient()
        self.outbox = outbox_store or get_outbox_store(database_manager=mgr)
        self.timeline = timeline_store or get_timeline_store()
        self.opt_out = opt_out_store or get_persistent_opt_out_store(database_manager=mgr)
        self.scheduler = RecoveryScheduler(policy=scheduler_policy)
        self.reconciliation = PaymentReconciliationEngine(
            razorpay_client=self.rzp,
            outbox_store=self.outbox,
            timeline_store=self.timeline,
        )
        self.webhook_processor = webhook_processor or get_durable_webhook_processor(
            timeline_store=self.timeline,
            outbox_store=self.outbox,
            opt_out_store=self.opt_out,
            database_manager=database_manager,
        )
        self.worker = RecoveryBackgroundWorker(
            outbox_store=self.outbox,
            opt_out_store=self.opt_out,
            timeline_store=self.timeline,
            razorpay_client=self.rzp,
            whatsapp_client=self.wa,
        )
        self._cases: Dict[str, RecoveryCaseRecord] = {}

    def create_case(
        self,
        case_id: str,
        payment_id: str,
        amount_paise: Optional[int] = None,
        amount_inr: Optional[Union[Decimal, float, str, int]] = None,
        customer_phone: str = "",
        customer_name: str = "Valued Customer",
        merchant_name: str = "Merchant",
        merchant_id: str = "default_merchant",
        error_code: str = "GATEWAY_TIMEOUT",
        error_category: str = "TECHNICAL_GATEWAY",
        max_attempts: int = 3,
    ) -> RecoveryCaseRecord:
        """Initializes a new recovery case record in PENDING state."""
        amount_paise_val = parse_monetary_amount(amount_paise=amount_paise, amount_inr=amount_inr)

        record = RecoveryCaseRecord(
            case_id=case_id,
            payment_id=payment_id,
            amount_paise=amount_paise_val,
            customer_phone=customer_phone,
            customer_name=customer_name,
            merchant_name=merchant_name,
            merchant_id=merchant_id,
            error_code=error_code,
            error_category=error_category,
            status=RecoveryState.PENDING,
            attempts_made=0,
            max_attempts=max_attempts,
        )
        self._cases[case_id] = record

        # Register mapping for webhooks
        self.webhook_processor.register_case_mapping(
            case_id=case_id,
            initial_status=RecoveryState.PENDING,
            customer_phone=customer_phone,
        )

        logger.info(f"Created recovery case {case_id} for payment {payment_id} ({amount_paise_val} paise).")
        return record

    def evaluate_and_schedule(
        self,
        case_id: str,
        customer_timezone: Optional[str] = None,
        delay_seconds: Optional[int] = None,
        template_name: Optional[str] = None,
    ) -> Tuple[RecoveryEligibilityResult, Optional[ScheduledRecoveryAction]]:
        """
        Runs deterministic eligibility engine and schedules the recovery action if eligible.
        """
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Recovery case '{case_id}' not found.")

        # 1. Eligibility Evaluation
        is_opted_out = self.opt_out.is_opted_out(case.customer_phone)
        is_24h = self.opt_out.is_within_24h_window(case.customer_phone)

        eval_ctx = EligibilityEvaluationContext(
            case_id=case.case_id,
            payment_id=case.payment_id,
            amount_paise=case.amount_paise,
            customer_phone=case.customer_phone,
            error_code=case.error_code,
            error_category=case.error_category,
            current_case_status=case.status,
            customer_opted_out=is_opted_out,
            attempts_already_made=case.attempts_made,
            max_allowed_attempts=case.max_attempts,
            is_within_24h_meta_window=is_24h,
            has_approved_template=True,
        )

        eligibility = RecoveryEligibilityEngine.evaluate(eval_ctx)

        self.timeline.record_event(
            case_id=case_id,
            event_type="RECOVERY_ELIGIBILITY_EVALUATED",
            description=f"Eligibility evaluated as {eligibility.status.value}: {eligibility.reason_code}",
            source="ELIGIBILITY_ENGINE",
            metadata=eligibility.to_dict(),
        )

        if not eligibility.is_eligible:
            if eligibility.status == EligibilityStatus.SUPPRESSED:
                case.status = RecoveryState.SUPPRESSED_OPT_OUT
            elif eligibility.status == EligibilityStatus.INELIGIBLE:
                case.status = RecoveryState.FAILED
            case.updated_at_utc = time.time()
            return eligibility, None

        # 2. Transition state machine to ELIGIBLE then SCHEDULED
        case.status, _ = RecoveryStateMachine.transition(
            case_id=case_id,
            current_state=case.status,
            target_state=RecoveryState.ELIGIBLE,
            event_trigger="ELIGIBILITY_CONFIRMED",
        )

        scheduled_action = self.scheduler.schedule_initial_action(
            case_id=case_id,
            payment_id=case.payment_id,
            customer_timezone=customer_timezone,
            delay_seconds=delay_seconds,
        )

        case.status, _ = RecoveryStateMachine.transition(
            case_id=case_id,
            current_state=case.status,
            target_state=RecoveryState.SCHEDULED,
            event_trigger="RECOVERY_SCHEDULED",
        )
        case.updated_at_utc = time.time()

        # 3. Enqueue to Durable Outbox
        idemp_key = f"rec_{case_id}_{scheduled_action.attempt_number}"
        delay_calc = max(0, int((scheduled_action.scheduled_at_utc - self.scheduler.now_utc()).total_seconds()))

        self.outbox.enqueue(
            case_id=case.case_id,
            payment_id=case.payment_id,
            idempotency_key=idemp_key,
            action="DISPATCH_RECOVERY_NUDGE",
            channel="WHATSAPP",
            recipient_masked=f"{case.customer_phone[:4]}***{case.customer_phone[-2:]}",
            message_payload={
                "customer_phone": case.customer_phone,
                "amount_paise": case.amount_paise,
                "customer_name": case.customer_name,
                "merchant_name": case.merchant_name,
                "merchant_id": case.merchant_id,
                "template_name": template_name,
            },
            delay_seconds=delay_calc,
        )

        self.timeline.record_event(
            case_id=case_id,
            event_type="RECOVERY_SCHEDULED",
            description=(
                f"Recovery attempt {scheduled_action.attempt_number} scheduled for "
                f"{scheduled_action.scheduled_at_utc.isoformat()} (timezone: {scheduled_action.target_timezone})."
            ),
            source="RECOVERY_SCHEDULER",
            attempt_number=scheduled_action.attempt_number,
            from_state="ELIGIBLE",
            to_state="SCHEDULED",
            metadata={
                "is_rescheduled_for_dnd": scheduled_action.is_rescheduled_for_dnd,
                "scheduled_at_utc": scheduled_action.scheduled_at_utc.isoformat(),
            },
        )

        return eligibility, scheduled_action

    def execute_worker_batch(self, batch_size: int = 10) -> List[JobExecutionResult]:
        """Runs a batch of claimed background recovery jobs."""
        results = self.worker.process_batch(batch_size=batch_size)
        # Update case records with generated links and message IDs
        for res in results:
            case = self._cases.get(res.case_id)
            if case:
                if res.payment_link_id:
                    case.payment_link_id = res.payment_link_id
                    case.payment_link_url = res.payment_link_url
                if res.whatsapp_message_id:
                    case.whatsapp_message_id = res.whatsapp_message_id

                if res.status == "COMPLETED":
                    case.status = RecoveryState.DISPATCHED
                    case.attempts_made += 1
                elif res.status == "RECONCILIATION_REQUIRED":
                    case.status = RecoveryState.RECONCILIATION_REQUIRED
                elif res.status == "DEAD_LETTER":
                    case.status = RecoveryState.FAILED
                elif res.status == "SUPPRESSED":
                    case.status = RecoveryState.SUPPRESSED_OPT_OUT
                case.updated_at_utc = time.time()

                # Register mappings for webhook lookups
                self.webhook_processor.register_case_mapping(
                    case_id=case.case_id,
                    initial_status=case.status,
                    payment_link_id=case.payment_link_id,
                    whatsapp_message_id=case.whatsapp_message_id,
                    customer_phone=case.customer_phone,
                )

        return results

    def reconcile_case(self, case_id: str) -> ReconciliationReport:
        """Active reconciliation of payment status via Razorpay client."""
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case '{case_id}' not found.")

        report = self.reconciliation.reconcile_case(
            case_id=case.case_id,
            payment_id=case.payment_id,
            current_state=case.status,
            payment_link_id=case.payment_link_id,
        )

        # Update case record
        case.status = RecoveryState(report.resulting_state)
        case.updated_at_utc = time.time()
        return report

    def cancel_case(self, case_id: str, reason: str = "MANUAL_CANCEL") -> bool:
        """Explicitly cancels a recovery case and all associated pending outbox jobs."""
        case = self._cases.get(case_id)
        if not case:
            return False

        if case.status == RecoveryState.RECOVERED:
            logger.warning(f"Cannot cancel case {case_id}: already authoritatively RECOVERED.")
            return False

        old_state = case.status
        case.status, _ = RecoveryStateMachine.transition(
            case_id=case_id,
            current_state=case.status,
            target_state=RecoveryState.CANCELLED,
            event_trigger=f"CANCEL_{reason}",
        )
        case.updated_at_utc = time.time()

        cancelled_jobs = self.outbox.cancel_jobs_for_case(case_id, reason=reason)

        self.timeline.record_event(
            case_id=case_id,
            event_type="RECOVERY_FAILED",
            description=f"Recovery case cancelled: {reason}",
            source="USER_ACTION",
            from_state=old_state.value,
            to_state="CANCELLED",
            metadata={"cancelled_jobs": cancelled_jobs, "reason": reason},
        )
        return True

    def get_case(self, case_id: str) -> Optional[RecoveryCaseRecord]:
        return self._cases.get(case_id)

    def get_outbox_job(self, job_id: str, merchant_id: Optional[str] = None) -> Optional[OutboxJob]:
        """Retrieves an outbox job by ID with optional tenant scope."""
        return self.outbox.get_job(job_id=job_id, merchant_id=merchant_id)

    def approve_outbox_job(
        self,
        job_id: str,
        operator_id: str,
        merchant_id: Optional[str] = None,
    ) -> bool:
        """
        Explicitly approves an outbox job in PENDING_APPROVAL status.
        Transitions the status to QUEUED and registers operator ID, timestamp, and payload snapshot hash.
        """
        success = self.outbox.approve_job(
            job_id=job_id,
            operator_id=operator_id,
            merchant_id=merchant_id,
        )
        if success:
            job = self.outbox.get_job(job_id=job_id, merchant_id=merchant_id)
            if job:
                self.timeline.record_event(
                    case_id=job.case_id,
                    event_type="OPERATOR_APPROVAL_GRANTED",
                    description=f"Operator '{operator_id}' approved recovery outbox dispatch.",
                    source="OPERATOR_PORTAL",
                    from_state="PENDING_APPROVAL",
                    to_state="QUEUED",
                    metadata={
                        "job_id": job.id,
                        "operator_id": operator_id,
                        "approval_snapshot_hash": job.approval_snapshot_hash,
                    },
                )
        return success

    def reject_outbox_job(
        self,
        job_id: str,
        operator_id: str,
        reason: str = "Rejected by operator",
        merchant_id: Optional[str] = None,
    ) -> bool:
        """Explicitly rejects an outbox job in PENDING_APPROVAL status."""
        success = self.outbox.reject_job(
            job_id=job_id,
            operator_id=operator_id,
            reason=reason,
            merchant_id=merchant_id,
        )
        if success:
            job = self.outbox.get_job(job_id=job_id, merchant_id=merchant_id)
            if job:
                self.timeline.record_event(
                    case_id=job.case_id,
                    event_type="OPERATOR_REJECTION_RECORDED",
                    description=f"Operator '{operator_id}' rejected recovery outbox dispatch: {reason}",
                    source="OPERATOR_PORTAL",
                    from_state="PENDING_APPROVAL",
                    to_state="REJECTED",
                    metadata={
                        "job_id": job.id,
                        "operator_id": operator_id,
                        "reason": reason,
                    },
                )
        return success

    def get_timeline(self, case_id: str) -> List[TimelineEvent]:
        return self.timeline.get_timeline(case_id)

    def get_metrics(self) -> Dict[str, Any]:
        """Aggregates metrics across cases, outbox, and delivery."""
        outbox_metrics = self.outbox.get_metrics()
        case_counts: Dict[str, int] = {}
        total_recovered_paise = 0

        for c in self._cases.values():
            st = c.status.value
            case_counts[st] = case_counts.get(st, 0) + 1
            if c.status == RecoveryState.RECOVERED:
                total_recovered_paise += c.amount_paise

        return {
            "cases": {
                "total": len(self._cases),
                "by_status": case_counts,
                "total_recovered_paise": total_recovered_paise,
                "total_recovered_inr": float(Decimal(total_recovered_paise) / Decimal(100)),
            },
            "outbox": outbox_metrics,
            "worker_health": {
                "status": "HEALTHY",
                "worker_id": self.worker.worker_id,
                "lease_duration_seconds": self.worker.lease_duration_seconds,
            },
        }


# Global singleton instance
_recovery_engine: Optional[PaymentRecoveryEngine] = None


def get_recovery_engine() -> PaymentRecoveryEngine:
    global _recovery_engine
    if _recovery_engine is None:
        _recovery_engine = PaymentRecoveryEngine()
    return _recovery_engine

