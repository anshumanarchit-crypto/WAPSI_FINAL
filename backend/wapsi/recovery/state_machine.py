"""
Recovery State Machine for WAPSI Autonomous Payment Recovery Engine.

Supported States:
- ELIGIBLE: Passed eligibility checks, ready for scheduling.
- PENDING: Newly created or awaiting initial eligibility determination.
- SCHEDULED: Queued for recovery dispatch at a designated timestamp.
- DISPATCHING: Claimed by an active background worker lease.
- DISPATCHED: Successfully accepted by communication provider (e.g. Meta Cloud API).
- DELIVERED: Verified handset delivery receipt received from provider.
- READ: Verified message read receipt received from customer.
- RECOVERED: Authoritative payment captured via Razorpay.
- FAILED: Terminal or retryable execution failure.
- EXPIRED: Payment link or recovery eligibility window expired.
- SUPPRESSED_OPT_OUT: Suppressed due to customer opt-out / DND request.
- CANCELLED: Explicitly cancelled by merchant or system policy.
- RECONCILIATION_REQUIRED: Ambiguous network outcome requiring status reconciliation.

Invariants Enforced:
1. Payment capture is authoritative evidence for RECOVERED.
2. A delayed failure event must NEVER downgrade RECOVERED.
3. A duplicate event must not create duplicate state transitions (idempotent no-op).
4. A cancelled or expired payment link does not imply payment failure if unreconciled.
5. WhatsApp message accepted != delivered.
6. Delivered or read != payment recovery.
7. Invalid state transitions are rejected with InvalidStateTransitionError and logged.
"""

from __future__ import annotations

import enum
import logging
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger("wapsi.recovery.state_machine")


class RecoveryState(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    DISPATCHING = "DISPATCHING"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    READ = "READ"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    SUPPRESSED_OPT_OUT = "SUPPRESSED_OPT_OUT"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal or out-of-order state transition is attempted."""

    def __init__(self, from_state: RecoveryState, to_state: RecoveryState, case_id: str, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.case_id = case_id
        self.reason = reason
        super().__init__(
            f"Invalid state transition for case '{case_id}': "
            f"cannot transition from {from_state.value} to {to_state.value}. {reason}".strip()
        )


class RecoveryStateMachine:
    """
    Formal state transition manager for payment recovery cases.
    Encapsulates all allowed transition paths and invariants.
    """

    # Explicit allowed transition graph: current_state -> set of reachable states
    _ALLOWED_TRANSITIONS: Dict[RecoveryState, Set[RecoveryState]] = {
        RecoveryState.PENDING: {
            RecoveryState.ELIGIBLE,
            RecoveryState.DISPATCHING,
            RecoveryState.DISPATCHED,
            RecoveryState.FAILED,
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.CANCELLED,
            RecoveryState.RECOVERED,
            RecoveryState.SCHEDULED,
        },
        RecoveryState.ELIGIBLE: {
            RecoveryState.SCHEDULED,
            RecoveryState.DISPATCHING,
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.CANCELLED,
            RecoveryState.RECOVERED,
            RecoveryState.EXPIRED,
            RecoveryState.FAILED,
        },
        RecoveryState.SCHEDULED: {
            RecoveryState.DISPATCHING,
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.CANCELLED,
            RecoveryState.RECOVERED,
            RecoveryState.EXPIRED,
            RecoveryState.FAILED,
            RecoveryState.SCHEDULED,  # Rescheduling
        },
        RecoveryState.DISPATCHING: {
            RecoveryState.DISPATCHED,
            RecoveryState.DELIVERED,
            RecoveryState.READ,
            RecoveryState.SCHEDULED,  # Retry after transient error
            RecoveryState.FAILED,     # Terminal error
            RecoveryState.RECONCILIATION_REQUIRED,  # Ambiguous network timeout
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.RECOVERED,
            RecoveryState.CANCELLED,
        },
        RecoveryState.DISPATCHED: {
            RecoveryState.DELIVERED,
            RecoveryState.READ,
            RecoveryState.RECOVERED,
            RecoveryState.FAILED,
            RecoveryState.SCHEDULED,  # Next nudge attempt
            RecoveryState.EXPIRED,
            RecoveryState.CANCELLED,
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.RECONCILIATION_REQUIRED,
        },
        RecoveryState.DELIVERED: {
            RecoveryState.READ,
            RecoveryState.RECOVERED,
            RecoveryState.SCHEDULED,  # Next nudge attempt
            RecoveryState.FAILED,
            RecoveryState.EXPIRED,
            RecoveryState.CANCELLED,
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.RECONCILIATION_REQUIRED,
        },
        RecoveryState.READ: {
            RecoveryState.RECOVERED,
            RecoveryState.SCHEDULED,  # Next nudge attempt
            RecoveryState.EXPIRED,
            RecoveryState.FAILED,
            RecoveryState.CANCELLED,
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.RECONCILIATION_REQUIRED,
        },
        RecoveryState.RECONCILIATION_REQUIRED: {
            RecoveryState.RECOVERED,
            RecoveryState.FAILED,
            RecoveryState.EXPIRED,
            RecoveryState.SCHEDULED,
            RecoveryState.CANCELLED,
            RecoveryState.SUPPRESSED_OPT_OUT,
            RecoveryState.DISPATCHED,  # Provider confirmed original message accepted
        },
        RecoveryState.FAILED: {
            RecoveryState.SCHEDULED,  # Manual or policy retry
            RecoveryState.RECOVERED,  # Late payment capture overrides previous failure
            RecoveryState.CANCELLED,
            RecoveryState.RECONCILIATION_REQUIRED,
        },
        RecoveryState.EXPIRED: {
            RecoveryState.SCHEDULED,  # New link scheduled
            RecoveryState.RECOVERED,  # Late capture overrides expiration
            RecoveryState.CANCELLED,
            RecoveryState.RECONCILIATION_REQUIRED,
        },
        RecoveryState.SUPPRESSED_OPT_OUT: {
            RecoveryState.RECOVERED,  # Customer paid despite opting out of messages
            RecoveryState.CANCELLED,
        },
        RecoveryState.CANCELLED: {
            RecoveryState.RECOVERED,  # Customer paid despite merchant cancellation
        },
        RecoveryState.RECOVERED: {
            # Terminal authoritative state: RECOVERED can never be transitioned away from!
        },
    }

    @classmethod
    def can_transition(cls, from_state: RecoveryState, to_state: RecoveryState) -> bool:
        """Checks if a transition from from_state to to_state is valid."""
        if from_state == to_state:
            return True  # Idempotent no-op
        allowed = cls._ALLOWED_TRANSITIONS.get(from_state, set())
        return to_state in allowed

    @classmethod
    def transition(
        cls,
        case_id: str,
        current_state: RecoveryState,
        target_state: RecoveryState,
        event_trigger: Optional[str] = None,
        is_payment_capture: bool = False,
    ) -> Tuple[RecoveryState, bool]:
        """
        Executes a validated state transition.

        Returns:
            Tuple[RecoveryState, bool]: (resulting_state, state_changed)
            - If current_state == target_state: returns (current_state, False) [idempotent no-op]
            - If valid: returns (target_state, True)
            - If current is RECOVERED and target is non-RECOVERED: silently protects RECOVERED state
            - If invalid: raises InvalidStateTransitionError

        Guarantees:
        - Invariant 1 & 2: RECOVERED is authoritative; delayed failure events never downgrade RECOVERED.
        - Invariant 3: Duplicate transitions return state_changed=False cleanly.
        - Invariant 7: Illegal transitions raise InvalidStateTransitionError.
        """
        # Idempotent no-op check
        if current_state == target_state:
            logger.debug(f"Idempotent transition for case {case_id}: already in {current_state.value}")
            return current_state, False

        # Invariant: RECOVERED is terminal and authoritative
        if current_state == RecoveryState.RECOVERED:
            logger.warning(
                f"Authoritative protection for case {case_id}: "
                f"Ignored attempted transition from RECOVERED to {target_state.value} (trigger: {event_trigger}). "
                f"Preserving RECOVERED status."
            )
            return RecoveryState.RECOVERED, False

        # If incoming event is payment capture, it transitions immediately to RECOVERED from any state
        if is_payment_capture or target_state == RecoveryState.RECOVERED:
            logger.info(
                f"Authoritative recovery for case {case_id}: "
                f"transitioning from {current_state.value} to RECOVERED (trigger: {event_trigger})."
            )
            return RecoveryState.RECOVERED, True

        # Check transition graph
        if not cls.can_transition(current_state, target_state):
            err_msg = (
                f"Transition from {current_state.value} to {target_state.value} is not permitted by state machine "
                f"(trigger: {event_trigger})."
            )
            logger.error(f"State transition violation for case {case_id}: {err_msg}")
            raise InvalidStateTransitionError(current_state, target_state, case_id, err_msg)

        logger.info(
            f"Case {case_id} transitioned: {current_state.value} -> {target_state.value} "
            f"(trigger: {event_trigger or 'SYSTEM'})"
        )
        return target_state, True

