"""
WAPSI Event-Driven Autonomous Payment Recovery Workflow Engine.
Phase 3 Core Architecture.
"""

from wapsi.recovery.eligibility import (
    EligibilityEvaluationContext,
    EligibilityStatus,
    RecoveryEligibilityEngine,
    RecoveryEligibilityResult,
)
from wapsi.recovery.engine import PaymentRecoveryEngine, RecoveryCaseRecord, get_recovery_engine
from wapsi.recovery.opt_out_store import (
    PersistentOptOutStore,
    get_persistent_opt_out_store,
    set_persistent_opt_out_store,
)
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob, get_outbox_store
from wapsi.recovery.reconciliation import PaymentReconciliationEngine, ReconciliationReport
from wapsi.recovery.scheduler import RecoverySchedulePolicy, RecoveryScheduler, ScheduledRecoveryAction
from wapsi.recovery.state_machine import (
    InvalidStateTransitionError,
    RecoveryState,
    RecoveryStateMachine,
)
from wapsi.recovery.timeline import RecoveryTimelineStore, TimelineEvent, get_timeline_store
from wapsi.recovery.webhook_processor import (
    DurableWebhookEventProcessor,
    DurableWebhookInbox,
    WebhookProcessingResult,
    get_durable_webhook_processor,
    set_durable_webhook_processor,
)
from wapsi.recovery.worker import JobExecutionResult, RecoveryBackgroundWorker
from wapsi.recovery.worker_daemon import (
    RecoveryWorkerDaemon,
    WorkerDaemonConfig,
    WorkerHeartbeat,
)
from wapsi.recovery.observational_logger import (
    DecisionObservationRecord,
    ObservationalLogger,
    get_observational_logger,
    set_observational_logger,
)

__all__ = [
    "RecoveryState",
    "RecoveryStateMachine",
    "InvalidStateTransitionError",
    "EligibilityStatus",
    "RecoveryEligibilityResult",
    "EligibilityEvaluationContext",
    "RecoveryEligibilityEngine",
    "RecoverySchedulePolicy",
    "ScheduledRecoveryAction",
    "RecoveryScheduler",
    "OutboxJob",
    "DurableOutboxStore",
    "get_outbox_store",
    "TimelineEvent",
    "RecoveryTimelineStore",
    "get_timeline_store",
    "PersistentOptOutStore",
    "get_persistent_opt_out_store",
    "set_persistent_opt_out_store",
    "WebhookProcessingResult",
    "DurableWebhookInbox",
    "DurableWebhookEventProcessor",
    "get_durable_webhook_processor",
    "set_durable_webhook_processor",
    "ReconciliationReport",
    "PaymentReconciliationEngine",
    "JobExecutionResult",
    "RecoveryBackgroundWorker",
    "WorkerDaemonConfig",
    "WorkerHeartbeat",
    "RecoveryWorkerDaemon",
    "RecoveryCaseRecord",
    "PaymentRecoveryEngine",
    "get_recovery_engine",
    "DecisionObservationRecord",
    "ObservationalLogger",
    "get_observational_logger",
    "set_observational_logger",
]

