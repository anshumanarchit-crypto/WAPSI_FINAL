"""
Recovery Eligibility Engine for WAPSI Autonomous Payment Recovery Engine.

Evaluates payment failure candidates deterministically before recovery actions are scheduled.
Zero LLM involvement in monetary calculations, customer consent, or policy rules.

Evaluations:
1. Payment error category and code recoverability.
2. Payment capture / recovery status (not already paid/recovered).
3. Customer opt-out status (STOP/UNSUBSCRIBE registry).
4. Customer explicit consent status (DPDP / GDPR compliance).
5. Customer fatigue and contact budget limits.
6. Attempt limits and retry budget exhaustion.
7. Payment link expiration status.
8. Communication window / 24h Meta customer service window / approved template availability.
9. Merchant configuration thresholds (minimum recovery amount, margin, enabled flag).

Outputs:
- ELIGIBLE: Safe and permitted for automated recovery scheduling.
- INELIGIBLE: Non-recoverable payment or merchant policy rejection.
- SUPPRESSED: Legally or policy-suppressed (opt-out, fatigue, revoked consent).
- REQUIRES_REVIEW: High-risk or anomalous state requiring manual review.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from wapsi.recovery.state_machine import RecoveryState

logger = logging.getLogger("wapsi.recovery.eligibility")

# Irreversible failure categories and error codes that cannot be recovered automatically
NON_RECOVERABLE_ERROR_CODES: Set[str] = {
    "CARD_REPORTED_STOLEN",
    "FRAUD_SUSPECTED",
    "CARD_RESTRICTED",
    "ACCOUNT_CLOSED",
    "MERCHANT_BLOCKED_BY_RISK",
    "BLACKLISTED_CUSTOMER",
    "LEGAL_HOLD",
    "CHARGEBACK_IN_PROGRESS",
}

NON_RECOVERABLE_CATEGORIES: Set[str] = {
    "FRAUD_SECURITY_BLOCK",
    "LEGAL_REGULATORY_PROHIBITED",
}


class EligibilityStatus(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    SUPPRESSED = "SUPPRESSED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


@dataclass
class RecoveryEligibilityResult:
    """Deterministic eligibility decision record."""
    status: EligibilityStatus
    is_eligible: bool
    reason_code: str
    reasons: List[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    case_id: Optional[str] = None
    payment_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "is_eligible": self.is_eligible,
            "reason_code": self.reason_code,
            "reasons": self.reasons,
            "evaluated_at": self.evaluated_at.isoformat(),
            "case_id": self.case_id,
            "payment_id": self.payment_id,
            "metadata": self.metadata,
        }


@dataclass
class EligibilityEvaluationContext:
    """Input parameters for deterministic eligibility check."""
    case_id: str
    payment_id: str
    amount_paise: int
    customer_phone: str
    error_code: str
    error_category: str
    current_case_status: Optional[RecoveryState] = None
    payment_already_captured: bool = False
    customer_opted_out: bool = False
    customer_consent_status: str = "ACTIVE_CONSENT"  # 'ACTIVE_CONSENT', 'OPTED_OUT', 'REVOKED', 'EXPIRED'
    customer_fatigue_score: int = 1000  # Basis points: 0 - 10000 (1000 = 10%)
    customer_prior_failures: int = 0
    attempts_already_made: int = 0
    max_allowed_attempts: int = 3
    is_link_expired: bool = False
    is_within_communication_hours: bool = True
    is_within_24h_meta_window: bool = False
    has_approved_template: bool = True
    merchant_recovery_enabled: bool = True
    merchant_min_amount_paise: int = 1000  # Default ₹10.00 (1000 paise)
    merchant_margin_basis_points: int = 2000  # 20.00%
    is_manual_review_flagged: bool = False


class RecoveryEligibilityEngine:
    """
    Evaluates recovery candidate against strict deterministic criteria.
    """

    @classmethod
    def evaluate(cls, ctx: EligibilityEvaluationContext) -> RecoveryEligibilityResult:
        reasons: List[str] = []

        # 1. Authoritative Capture Check
        if ctx.payment_already_captured or ctx.current_case_status == RecoveryState.RECOVERED:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.INELIGIBLE,
                is_eligible=False,
                reason_code="PAYMENT_ALREADY_RECOVERED",
                reasons=["Payment is already captured and recorded as recovered."],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
                metadata={"current_status": "RECOVERED"},
            )

        # 2. Customer Opt-Out Check (Highest priority suppression)
        if ctx.customer_opted_out:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.SUPPRESSED,
                is_eligible=False,
                reason_code="CUSTOMER_OPTED_OUT",
                reasons=["Customer has explicitly opted out (STOP/UNSUBSCRIBE). All communications suppressed."],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
                metadata={"customer_opted_out": True},
            )

        # 3. Customer Consent Verification
        if ctx.customer_consent_status != "ACTIVE_CONSENT":
            return RecoveryEligibilityResult(
                status=EligibilityStatus.SUPPRESSED,
                is_eligible=False,
                reason_code="CONSENT_NOT_ACTIVE",
                reasons=[f"Customer consent status is '{ctx.customer_consent_status}'; requires ACTIVE_CONSENT."],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
                metadata={"consent_status": ctx.customer_consent_status},
            )

        # 4. Irreversible Failure / Fraud Rejection
        if ctx.error_code in NON_RECOVERABLE_ERROR_CODES or ctx.error_category in NON_RECOVERABLE_CATEGORIES:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.INELIGIBLE,
                is_eligible=False,
                reason_code="NON_RECOVERABLE_ERROR",
                reasons=[f"Error code '{ctx.error_code}' in category '{ctx.error_category}' cannot be recovered."],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
                metadata={"error_code": ctx.error_code, "error_category": ctx.error_category},
            )

        # 5. Attempt Budget Exhaustion
        if ctx.attempts_already_made >= ctx.max_allowed_attempts:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.INELIGIBLE,
                is_eligible=False,
                reason_code="RETRY_BUDGET_EXHAUSTED",
                reasons=[
                    f"Attempt limit exhausted: {ctx.attempts_already_made} attempts made "
                    f"(max allowed: {ctx.max_allowed_attempts})."
                ],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
                metadata={
                    "attempts_already_made": ctx.attempts_already_made,
                    "max_allowed_attempts": ctx.max_allowed_attempts,
                },
            )

        # 6. Customer Fatigue / Anti-Spam Throttling
        if ctx.customer_fatigue_score > 8000:  # > 80% fatigue
            return RecoveryEligibilityResult(
                status=EligibilityStatus.SUPPRESSED,
                is_eligible=False,
                reason_code="CUSTOMER_FATIGUE_EXCEEDED",
                reasons=[
                    f"Customer fatigue score {ctx.customer_fatigue_score}/10000 exceeds safety threshold (8000)."
                ],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
                metadata={"fatigue_score": ctx.customer_fatigue_score},
            )

        # 7. Merchant Recovery Policy & Configuration
        if not ctx.merchant_recovery_enabled:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.INELIGIBLE,
                is_eligible=False,
                reason_code="MERCHANT_RECOVERY_DISABLED",
                reasons=["Merchant has globally disabled autonomous recovery."],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
            )

        if ctx.amount_paise < ctx.merchant_min_amount_paise:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.INELIGIBLE,
                is_eligible=False,
                reason_code="AMOUNT_BELOW_MINIMUM",
                reasons=[
                    f"Transaction amount {ctx.amount_paise} paise is below merchant minimum threshold "
                    f"({ctx.merchant_min_amount_paise} paise)."
                ],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
                metadata={"amount_paise": ctx.amount_paise, "min_paise": ctx.merchant_min_amount_paise},
            )

        # 8. Communication Channel Policy (Meta 24h Window & Template Check)
        if not ctx.is_within_24h_meta_window and not ctx.has_approved_template:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.REQUIRES_REVIEW,
                is_eligible=False,
                reason_code="OUTSIDE_WINDOW_NO_TEMPLATE",
                reasons=[
                    "Customer is outside Meta 24-hour service window and no approved business template is configured."
                ],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
            )

        # 9. Link Expiration Check
        if ctx.is_link_expired:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.INELIGIBLE,
                is_eligible=False,
                reason_code="PAYMENT_LINK_EXPIRED",
                reasons=["Existing payment link has expired without active renewal."],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
            )

        # 10. Manual Review Flags
        if ctx.is_manual_review_flagged:
            return RecoveryEligibilityResult(
                status=EligibilityStatus.REQUIRES_REVIEW,
                is_eligible=False,
                reason_code="MANUAL_REVIEW_FLAGGED",
                reasons=["Transaction flagged for manual operator review before automated contact."],
                case_id=ctx.case_id,
                payment_id=ctx.payment_id,
            )

        # Passed all deterministic checks!
        reasons.append("All deterministic eligibility and policy checks passed.")
        return RecoveryEligibilityResult(
            status=EligibilityStatus.ELIGIBLE,
            is_eligible=True,
            reason_code="ELIGIBILITY_CONFIRMED",
            reasons=reasons,
            case_id=ctx.case_id,
            payment_id=ctx.payment_id,
            metadata={
                "amount_paise": ctx.amount_paise,
                "attempts_remaining": ctx.max_allowed_attempts - ctx.attempts_already_made,
                "is_within_24h_meta_window": ctx.is_within_24h_meta_window,
            },
        )

