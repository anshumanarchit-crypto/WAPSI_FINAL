"""
Pydantic Schemas for WAPSI REST API Request/Response payloads.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class PaymentFailureEventRequest(BaseModel):
    event_id: Optional[str] = Field(default=None, description="Unique failure event ID")
    payment_id: str = Field(..., description="Razorpay payment ID e.g. pay_998124")
    order_id: Optional[str] = Field(default=None, description="Order ID e.g. order_783141")
    merchant_id: str = Field(default="merch_default", description="Merchant account ID")
    merchant_category: Optional[str] = Field(default="ecommerce", description="Merchant industry vertical")
    amount_in_inr: float = Field(..., gt=0, description="Payment transaction amount in INR")
    currency: str = Field(default="INR", description="Currency code")
    payment_method: str = Field(default="upi", description="Payment method: upi, card_credit, card_debit, netbanking, bnpl")
    error_code: str = Field(..., description="Gateway/bank error code e.g. UPI_APP_TIMEOUT")
    error_description: Optional[str] = Field(default="", description="Human-readable error description")
    user_id: str = Field(default="usr_anonymous", description="End customer user identifier")
    user_device_os: Optional[str] = Field(default="Android", description="Device OS: Android, iOS, Web_Desktop")
    user_network_type: Optional[str] = Field(default="4G", description="Network rail: 5G, 4G, 3G, WiFi")
    historical_orders_count: Optional[int] = Field(default=3, ge=0)
    historical_recovery_rate: Optional[float] = Field(default=0.35, ge=0.0, le=1.0)
    retry_attempt_number: Optional[int] = Field(default=1, ge=1)
    hour_of_day: Optional[int] = Field(default=14, ge=0, le=23)
    merchant_margin: Optional[float] = Field(default=0.20, ge=0.01, le=1.0)
    disallowed_actions: Optional[List[str]] = Field(default_factory=list)


class ActionRankingItem(BaseModel):
    action: str
    action_name: str
    channel: str
    predicted_recovery_probability: float
    causal_uplift_tau: float
    conformal_interval: List[float]
    confidence_tier: str
    dispatch_cost_inr: float
    friction_cost_inr: float
    net_expected_utility_inr: float


class PolicyEvaluationResult(BaseModel):
    is_allowed: bool
    proposed_action: str
    authorized_action: str
    override_applied: bool
    violations: List[str]
    dnd_active: bool
    frequency_cap_remaining: int
    rule_evaluation_summary: str


class CausalMetricsResult(BaseModel):
    baseline_organic_recovery_prob: float
    expected_action_recovery_prob: float
    individual_treatment_effect_uplift: float
    conformal_uplift_interval: List[float]
    confidence_tier: str
    net_expected_utility_inr: float
    total_action_cost_inr: float
    action_rankings: List[ActionRankingItem]


class CausalDecisionResponse(BaseModel):
    decision_id: str
    payment_id: str
    case_id: Optional[str] = None
    merchant_id: Optional[str] = None
    model_version: Optional[str] = None
    recommended_action: str
    recommended_action_name: str
    authorized_action: str
    channel: str
    execution_status: str
    requires_human_approval: bool = False
    human_approval_reason: Optional[str] = None
    risk_score: Optional[float] = None
    root_cause: Dict[str, Any]
    policy_evaluation: PolicyEvaluationResult
    causal_metrics: CausalMetricsResult
    timing: Dict[str, Any]
    precedent_evidence: Dict[str, Any]
    shap_explanations: Dict[str, Any]
    plain_english_rationale: str
    localized_copy: Dict[str, Any]
    audit_hash: str
    timestamp: str


class UnifiedCausalDecisionRequest(BaseModel):
    payment_id: str
    case_id: Optional[str] = None
    merchant_id: Optional[str] = "merch_default"
    amount_in_inr: float = 1000.0
    amount_paise: Optional[int] = None
    currency: Optional[str] = "INR"
    error_code: str = "insufficient_funds"
    error_description: Optional[str] = ""
    payment_method: Optional[str] = "upi"
    retry_attempt_number: Optional[int] = 1
    max_retries: Optional[int] = 3
    historical_recovery_rate: Optional[float] = 0.5
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    merchant_category: Optional[str] = "ecommerce"
    merchant_margin: Optional[float] = 0.20
    disallowed_actions: Optional[List[str]] = Field(default_factory=list)
    is_pre_approved_by_operator: Optional[bool] = False
    model_choice: Optional[str] = "dml"  # "dml", "x_learner", "t_learner"


class UnifiedCausalDecisionResponse(BaseModel):
    decision_id: str
    case_id: str
    payment_id: str
    merchant_id: str
    amount_in_inr: float
    model_version: str
    model_readiness_status: str = "BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS"
    deployment_mode: str = "ADVISORY_HUMAN_REVIEW"
    risk_score: float
    risk_assessment: Dict[str, Any]
    recommended_action: str
    recommended_action_name: str
    authorized_action: str
    channel: str
    execution_status: str
    requires_human_approval: bool
    human_approval_reason: Optional[str] = None
    estimated_treatment_uplift: float
    expected_recovered_value_inr: float
    net_expected_economic_value_inr: float
    uncertainty_information: Dict[str, Any]
    policy_decisions: Dict[str, Any]
    action_rankings: List[Dict[str, Any]]
    explanation_and_evidence: Dict[str, Any]
    plain_english_rationale: str
    localized_copy: Dict[str, Any]
    decision_timestamp: str
    audit_hash: str
    snapshot_hash: str


class ActionExecuteRequest(BaseModel):
    payment_id: str
    authorized_action: str
    event_data: Optional[Dict[str, Any]] = None
    message_copy: Optional[Dict[str, Any]] = None
    idempotency_key: Optional[str] = None


class ActionExecuteResponse(BaseModel):
    dispatch_id: str
    payment_id: str
    idempotency_key: str
    action_executed: str
    status: str
    channel: str
    dispatch_cost_inr: float
    timestamp: str
    channel_details: Dict[str, Any]
    is_idempotent_replay: bool
    audit_hash: str


class WebhookCallbackRequest(BaseModel):
    event_name: str = Field(..., description="e.g. payment.recovered, payment.failed, link.opened")
    payment_id: str
    status: str
    amount_in_inr: Optional[float] = 1000.0
    signature: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    status: str
    service: str
    version: str
    models_ready: bool
    tee_boundary: Dict[str, Any]
    audit_ledger_status: Dict[str, Any]


class RecoveryPaymentLinkRequest(BaseModel):
    case_id: Optional[str] = Field(default=None, max_length=64, description="Unique recovery case identifier")
    payment_id: Optional[str] = Field(default=None, max_length=64, description="Failed payment identifier")
    amount_paise: Optional[int] = Field(default=None, ge=100, le=100000000, description="Amount in integer paise")
    amount_inr: Optional[float] = Field(default=None, ge=1.0, le=1000000.0, description="Amount in INR decimal")
    amount_in_inr: Optional[float] = Field(default=None, ge=1.0, le=1000000.0, description="Amount in INR decimal (alias)")
    customer_name: str = Field(default="Valued Customer", min_length=1, max_length=100)
    customer_phone: str = Field(..., min_length=10, max_length=20, description="Customer phone number")
    merchant_name: str = Field(default="Merchant", max_length=100)
    merchant_id: Optional[str] = Field(default=None, max_length=64)
    expire_minutes: int = Field(default=15, ge=5, le=120)
    template_name: Optional[str] = Field(default=None, max_length=64)


class CreateRecoveryCaseRequest(BaseModel):
    case_id: Optional[str] = Field(default=None, max_length=64, description="Unique recovery case identifier")
    payment_id: str = Field(..., max_length=128, description="Failed payment identifier")
    amount_paise: Optional[int] = Field(default=None, ge=100, le=100000000, description="Amount in integer paise")
    amount_inr: Optional[float] = Field(default=None, ge=1.0, le=1000000.0, description="Amount in INR decimal")
    amount_in_inr: Optional[float] = Field(default=None, ge=1.0, le=1000000.0, description="Amount in INR decimal (alias)")
    customer_phone: str = Field(..., min_length=10, max_length=20, description="Customer phone number")
    customer_name: str = Field(default="Valued Customer", min_length=1, max_length=100)
    merchant_name: str = Field(default="Merchant", max_length=100)
    merchant_id: Optional[str] = Field(default="default_merchant", max_length=64)
    error_code: str = Field(default="GATEWAY_TIMEOUT", max_length=64)
    error_category: str = Field(default="TECHNICAL_GATEWAY", max_length=64)
    max_attempts: int = Field(default=3, ge=1, le=10)


class ScheduleRecoveryCaseRequest(BaseModel):
    customer_timezone: Optional[str] = Field(default="Asia/Kolkata", max_length=64)
    delay_seconds: Optional[int] = Field(default=0, ge=0, le=86400)
    template_name: Optional[str] = Field(default=None, max_length=64)


class CancelRecoveryCaseRequest(BaseModel):
    reason: str = Field(default="MANUAL_CANCEL", min_length=1, max_length=255)


class ApproveOutboxJobRequest(BaseModel):
    operator_id: str = Field(..., min_length=3, max_length=128, description="Operator identity assertion approving this job (attributed to authenticated tenant caller).")
    reason: Optional[str] = Field(default=None, max_length=255, description="Optional approval notes or rationale.")


class ApproveOutboxJobResponse(BaseModel):
    job_id: str
    status: str
    channel: str
    action: str
    recipient_masked: str
    approved_by_operator_id: str
    approved_at: str
    approval_snapshot_hash: str


class RejectOutboxJobRequest(BaseModel):
    operator_id: str = Field(..., min_length=3, max_length=128, description="Operator identity assertion rejecting this job (attributed to authenticated tenant caller).")
    reason: str = Field(default="Rejected by operator", min_length=3, max_length=255, description="Rejection rationale.")


class RejectOutboxJobResponse(BaseModel):
    job_id: str
    status: str
    operator_id: str
    reason: str
