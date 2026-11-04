"""
Pydantic Data Contracts & API Schemas for WAPSI Decision Engine.
Razorpay AI Buildathon 2026 - Track 3

Defines request/response contracts for:
  - POST /api/v1/recovery/predict
  - GET  /health
  - GET  /api/v1/model/info
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class RecoveryPredictRequest(BaseModel):
    """
    Inference request payload for a payment failure recovery case.
    """
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "case_id": "CASE_123",
                "merchant_id": "M001",
                "domain": "subscription",
                "amount": 4999.0,
                "decline_reason": "insufficient_funds",
                "attempts_used": 1,
                "account_age_days": 730,
                "previous_failures": 3,
                "previous_recoveries": 2,
                "prior_recovery_rate": 0.67,
                "day_of_week": 2,
                "hour": 11,
                "issuer": "HDFC",
                "bin_bucket": "classic",
                "fatigue_score": 0.10
            }
        }
    )

    case_id: Optional[str] = Field(
        default=None,
        description="Unique payment failure identifier. Auto-generated if not provided."
    )
    merchant_id: Optional[str] = Field(
        default="merch_default",
        description="Merchant identifier for merchant-specific shrinkage & contextual bandits."
    )
    domain: str = Field(
        default="ecommerce",
        description="Industry domain (e.g. ecommerce, subscription, b2b_saas, food_delivery, travel)."
    )
    amount: float = Field(
        gt=0.0,
        description="Transaction amount in INR (must be positive)."
    )
    decline_reason: str = Field(
        default="insufficient_funds",
        description="Root cause payment decline reason code."
    )
    attempts_used: int = Field(
        default=1,
        ge=1,
        description="Number of retry/recovery attempts already made for this transaction."
    )
    account_age_days: Optional[int] = Field(
        default=0,
        ge=0,
        description="Customer account age in days."
    )
    previous_failures: Optional[int] = Field(
        default=0,
        ge=0,
        description="Historical failed transactions for this customer."
    )
    previous_recoveries: Optional[int] = Field(
        default=0,
        ge=0,
        description="Historical successful recoveries for this customer."
    )
    prior_recovery_rate: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Historical recovery success rate (0.0 to 1.0)."
    )
    day_of_week: Optional[int] = Field(
        default=0,
        ge=0,
        le=6,
        description="Day of week index (0=Monday, 6=Sunday)."
    )
    hour: Optional[int] = Field(
        default=14,
        ge=0,
        le=23,
        description="Hour of transaction failure (0-23 IST)."
    )
    issuer: Optional[str] = Field(
        default="HDFC",
        description="Issuing bank (e.g. HDFC, ICICI, SBI, AXIS, KOTAK)."
    )
    bin_bucket: Optional[str] = Field(
        default="classic",
        description="Card BIN classification tier (e.g. classic, platinum, corporate, rupay)."
    )
    fatigue_score: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Customer contact fatigue score from 0.0 (fresh) to 1.0 (highly fatigued)."
    )


class TimingResponse(BaseModel):
    """Timing hazard recommendations across operational recovery windows."""
    recommended_window: str = Field(
        description="Optimal timing window (e.g. '0-24h', '24-48h', '48-72h', '72h+')."
    )
    hazard_by_window: Dict[str, float] = Field(
        description="Discrete conditional recovery hazard probability across all 4 time windows."
    )


class ShapReason(BaseModel):
    """Local causal attribution driver for why WAPSI recommended the action."""
    feature: str = Field(description="Covariate / feature name.")
    value: Union[str, float, int, None] = Field(description="Observed value of the feature.")
    impact: float = Field(description="SHAP local attribution impact on incremental uplift.")


class ExplanationResponse(BaseModel):
    """SHAP-based local explainability payload."""
    top_reasons: List[ShapReason] = Field(
        description="Ranked top driving features influencing the causal uplift estimate."
    )
    top_positive_features: Optional[List[ShapReason]] = Field(
        default=None,
        description="Features pushing uplift higher for this action."
    )
    top_negative_features: Optional[List[ShapReason]] = Field(
        default=None,
        description="Features pushing uplift lower for this action."
    )


class PrecedentItem(BaseModel):
    """Historical peer transaction record retrieved for transparent grounding."""
    model_config = ConfigDict(extra="allow")

    case_id: str = Field(description="Anonymized historical case identifier.")
    action: str = Field(description="Intervention action taken historically.")
    recovered: bool = Field(description="Factual observed outcome (true if recovered).")
    similarity: float = Field(description="Cosine / feature similarity score (0.0 to 1.0).")
    time_to_recovery_hours: Optional[float] = Field(
        default=None,
        description="Observed time elapsed until recovery in hours."
    )


class NetworkPriorResponse(BaseModel):
    """Empirical Bayes partial pooling shrinkage for merchant cold-start."""
    network_uplift: float = Field(description="Estimated action uplift across global network.")
    merchant_uplift: float = Field(description="Merchant-specific observed uplift estimate.")
    merchant_observations: int = Field(description="Number of observations for this merchant.")
    merchant_weight: float = Field(description="Shrinkage weight w(n) allocated to merchant evidence.")
    combined_uplift: float = Field(description="Final partially pooled blended uplift estimate.")


class BanditResponse(BaseModel):
    """Contextual Thompson Sampling online exploration/exploitation state."""
    selected_action: str = Field(description="Action sampled by Linear Thompson Sampling.")
    sampled_rewards: Dict[str, float] = Field(description="Posterior sampled net business rewards in INR.")
    expected_rewards: Dict[str, float] = Field(description="Posterior mean expected net business rewards in INR.")


class ConformalGateResponse(BaseModel):
    """Split-conformal statistical calibration decision gate."""
    eligible_for_auto_action: bool = Field(
        description="True if statistical 90% confidence interval lower bound is strictly positive."
    )
    confidence: float = Field(description="Statistical confidence / reliability score.")
    calibration_status: str = Field(description="Calibration guarantee status (e.g. CALIBRATED_NOMINAL_90).")
    action: Optional[str] = Field(default=None, description="Action evaluated by the gate.")
    predicted_uplift: Optional[float] = Field(default=None, description="Point estimate of causal uplift.")
    prediction_interval: Optional[List[float]] = Field(
        default=None,
        description="90% distribution-free conformal prediction bounds [lower, upper]."
    )
    conformal_score: Optional[float] = Field(default=None, description="Nonconformity metric.")
    conformal_threshold: Optional[float] = Field(default=None, description="Calibrated quantile threshold.")
    reason: str = Field(description="Plain-English explanation of the gating authorization or escalation.")


class PolicyInputsResponse(BaseModel):
    """Operational compliance, DND, and safety guardrail checks."""
    dnd_active: bool = Field(description="True if transaction occurred during TRAI DND (21:00 - 09:00 IST).")
    frequency_capped: bool = Field(description="True if customer has exceeded channel communication frequency caps.")
    conformal_gate: ConformalGateResponse = Field(description="Conformal statistical gate output.")


class RecoveryPredictResponse(BaseModel):
    """
    Unified WAPSI Causal Recovery Recommendation Object.
    Matches the exact JSON schema contract required by the frontend teammate.
    """
    case_id: str = Field(description="Unique case identifier.")
    decision_id: str = Field(description="Unique decision transaction identifier.")
    recommended_action: str = Field(description="Optimal recovery action recommended by the causal router.")
    uplift: float = Field(description="Estimated incremental recovery uplift (CATE) over baseline no_action.")
    action_scores: Dict[str, float] = Field(
        description="Estimated incremental uplift for all evaluated recovery actions."
    )
    timing: TimingResponse = Field(description="Timing hazard recommendations.")
    confidence: float = Field(description="Calibrated confidence score.")
    explanation: ExplanationResponse = Field(description="SHAP local attribution explanation.")
    precedents: List[PrecedentItem] = Field(
        description="Top similar historical cases and their factual outcomes."
    )
    counter_evidence: bool = Field(
        description="True if similar historical cases showed failure under the recommended action."
    )
    network_prior: NetworkPriorResponse = Field(description="Empirical Bayes network prior shrinkage.")
    bandit: BanditResponse = Field(description="Contextual bandit Thompson Sampling recommendation.")
    tee_status: str = Field(
        default="attested",
        description="Confidential Computing TEE trust attestation status (e.g. 'attested', 'unverified', 'failed_closed')."
    )
    policy_status: str = Field(
        default="allowed",
        description="Operational compliance gate status (e.g. 'allowed', 'dnd_restricted', 'blocked')."
    )
    policy_inputs: Optional[PolicyInputsResponse] = Field(
        default=None,
        description="Policy Engine & Conformal Gate guardrails."
    )


class HealthResponse(BaseModel):
    """Service health status response."""
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "status": "healthy",
                "service": "wapsi-causal-decision-engine",
                "version": "1.0.0",
                "models_loaded": True,
                "timestamp": "2026-08-30T13:30:00Z"
            }
        }
    )
    status: str
    service: str
    version: str
    models_loaded: bool
    timestamp: str
    database: Optional[Dict[str, Any]] = None
    tee_boundary: Optional[Dict[str, Any]] = None
    audit_ledger_status: Optional[Dict[str, Any]] = None


class ModelInfoResponse(BaseModel):
    """Public model metadata, versioning, and capabilities disclosure."""
    service: str = "wapsi-causal-decision-engine"
    version: str = "1.0.0"
    model_tier: str = "T-Learner Meta-Estimator + Linear Thompson Sampling + Conformal Gate"
    supported_actions: List[str]
    supported_domains: List[str]
    supported_decline_reasons: List[str]
    conformal_calibration_level: str = "90% Nominal Coverage (Finite-Sample Valid)"
    advisory_mode_only: bool = True
    notice: str = "This service is an advisory causal recommendation engine. It does not execute live payments or dispatches."


class ErrorResponse(BaseModel):
    """Standardized error payload."""
    error: str
    detail: str
    status_code: int
    case_id: Optional[str] = None


class WebhookPayloadRequest(BaseModel):
    """Incoming payment gateway webhook payload."""
    event: str = Field(description="Webhook event type, e.g., 'payment.recovered', 'payment.failed'.")
    payment_id: str = Field(description="Payment transaction identifier.")
    case_id: Optional[str] = None
    merchant_id: str = Field(default="merch_default")
    amount: float = Field(gt=0.0)
    status: str = Field(default="captured")
    timestamp: int = Field(description="Epoch timestamp of event in seconds.")
    nonce: str = Field(description="Anti-replay unique nonce.")


class WebhookResponse(BaseModel):
    """Webhook ingestion response."""
    status: str = "received"
    event_id: str
    signature_verified: bool = True
    idempotency_status: str = "processed"
    timestamp: str

