"""
SQLAlchemy 2.0 Declarative ORM Models for WAPSI Multi-Tenant Persistence.
Project: ffgsrwjhguvubmhuefyj (Razorpay AI Buildathon 2026 - Track 3)

Entities:
  1.  MerchantModel             - Tenants
  2.  MerchantMembershipModel   - Decoupled User-to-Tenant Membership & RBAC
  3.  MerchantConfigurationModel- Recovery & Policy Configurations
  4.  MerchantApiKeyModel       - Hashed API Keys
  5.  CustomerModel             - Pseudonymized Customer Identity & Consent
  6.  TransactionModel          - Failed & Recovered Transactions (Paise precision)
  7.  ModelVersionModel         - ML Model Registry & Benchmarks
  8.  CausalDecisionModel       - Causal Uplift & Intervention Decisions
  9.  WebhookInboxModel         - Durable Multi-Provider Webhook Deduplication
  10. IdempotencyKeyModel       - API Idempotency Locks & Responses
  11. RecoveryOutboxModel       - Transactional Outbox Pattern
  12. RecoveryDispatchModel     - Dispatch Receipts
  13. PaymentOutcomeModel       - Promise-to-Pay Reconciliation
  14. AuditLedgerBlockModel     - Cryptographic Tamper-Evident Ledger
  15. BanditWeightModel         - Online Bandit LinUCB / Thompson Sampling State
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class with dictionary serialization."""

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model attributes to JSON-safe dictionary."""
        result = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, uuid.UUID):
                result[col.name] = str(val)
            elif isinstance(val, datetime):
                result[col.name] = val.isoformat()
            else:
                result[col.name] = val
        return result


# ==============================================================================
# 1. MERCHANTS
# ==============================================================================
class MerchantModel(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[str] = mapped_column(String(128), default="Ecommerce", nullable=False)
    industry: Mapped[str] = mapped_column(String(128), default="FinTech / Ecommerce", nullable=False)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    registered_email: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(64), default="India", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'ONBOARDING', 'ARCHIVED')", name="ck_merchant_status"),
    )

    # Relationships
    memberships = relationship("MerchantMembershipModel", back_populates="merchant", cascade="all, delete-orphan")
    configuration = relationship("MerchantConfigurationModel", back_populates="merchant", uselist=False, cascade="all, delete-orphan")
    api_keys = relationship("MerchantApiKeyModel", back_populates="merchant", cascade="all, delete-orphan")
    customers = relationship("CustomerModel", back_populates="merchant", cascade="all, delete-orphan")
    transactions = relationship("TransactionModel", back_populates="merchant", cascade="all, delete-orphan")


# ==============================================================================
# 2. MERCHANT MEMBERSHIPS
# ==============================================================================
class MerchantMembershipModel(Base):
    __tablename__ = "merchant_memberships"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True) # Decoupled Supabase Auth UID
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_id", "user_id", name="uq_merchant_membership_user"),
        CheckConstraint(
            "role IN ('merchant_admin', 'recovery_operator', 'risk_officer', 'auditor', 'system_service')",
            name="ck_membership_role"
        ),
    )

    merchant = relationship("MerchantModel", back_populates="memberships")


# ==============================================================================
# 3. MERCHANT CONFIGURATIONS
# ==============================================================================
class MerchantConfigurationModel(Base):
    __tablename__ = "merchant_configurations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    recovery_enabled_percent: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    confidence_threshold_percent: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    min_uplift_threshold_percent: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    retry_attempt_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    contact_budget_per_customer: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    recovery_window_start_hour: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    recovery_window_end_hour: Mapped[int] = mapped_column(Integer, default=21, nullable=False)
    min_ivr_amount_paise: Mapped[int] = mapped_column(BigInteger, default=150000, nullable=False) # ₹1,500.00
    default_merchant_margin_basis_points: Mapped[int] = mapped_column(Integer, default=2000, nullable=False) # 20.00%
    disallowed_actions: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    channel_settings: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"whatsapp": True, "sms": True, "email": True, "ivr": True, "smart_retry": True},
        nullable=False
    )
    alert_preferences: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"criticalAlerts": True, "recoveryUpdates": True, "dailySummary": True, "policyViolations": True},
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("recovery_enabled_percent BETWEEN 0 AND 100", name="ck_cfg_recovery_pct"),
        CheckConstraint("confidence_threshold_percent BETWEEN 0 AND 100", name="ck_cfg_conf_pct"),
        CheckConstraint("min_uplift_threshold_percent BETWEEN 0 AND 100", name="ck_cfg_uplift_pct"),
        CheckConstraint("recovery_window_start_hour BETWEEN 0 AND 23", name="ck_cfg_start_hr"),
        CheckConstraint("recovery_window_end_hour BETWEEN 0 AND 23", name="ck_cfg_end_hr"),
    )

    merchant = relationship("MerchantModel", back_populates="configuration")


# ==============================================================================
# 4. MERCHANT API KEYS
# ==============================================================================
class MerchantApiKeyModel(Base):
    __tablename__ = "merchant_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    key_name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(8), nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(16), default="test", nullable=False)
    scopes: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["recovery:predict", "recovery:read"], nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("environment IN ('test', 'live')", name="ck_api_key_env"),
    )

    merchant = relationship("MerchantModel", back_populates="api_keys")


# ==============================================================================
# 5. CUSTOMERS
# ==============================================================================
class CustomerModel(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_pseudonym: Mapped[str] = mapped_column(String(64), nullable=False, index=True) # HMAC-SHA256 hex
    masked_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    account_age_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prior_recoveries_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prior_failures_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fatigue_score_basis_points: Mapped[int] = mapped_column(Integer, default=1000, nullable=False) # 1000 = 0.1000
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opted_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(32), default="ACTIVE_CONSENT", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_id", "merchant_customer_id", name="uq_cust_merch_id"),
        UniqueConstraint("merchant_id", "customer_pseudonym", name="uq_cust_pseudonym"),
        CheckConstraint("fatigue_score_basis_points BETWEEN 0 AND 10000", name="ck_cust_fatigue"),
        CheckConstraint("consent_status IN ('ACTIVE_CONSENT', 'OPTED_OUT', 'REVOKED', 'EXPIRED')", name="ck_cust_consent"),
    )

    merchant = relationship("MerchantModel", back_populates="customers")
    transactions = relationship("TransactionModel", back_populates="customer")


# ==============================================================================
# 6. TRANSACTIONS
# ==============================================================================
class TransactionModel(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False) # Strict Integer Paise
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    issuer: Mapped[str] = mapped_column(String(64), default="HDFC", nullable=False)
    bin_bucket: Mapped[str] = mapped_column(String(32), default="classic", nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    error_category: Mapped[str] = mapped_column(String(32), nullable=False)
    error_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempts_used: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    hour_of_day: Mapped[int] = mapped_column(Integer, nullable=False)
    is_dnd_window: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="FAILED", nullable=False, index=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    recovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_id", "payment_id", name="uq_tx_merchant_payment"),
        CheckConstraint("amount_paise > 0", name="ck_tx_amount_positive"),
        CheckConstraint("hour_of_day BETWEEN 0 AND 23", name="ck_tx_hour"),
        CheckConstraint("status IN ('INITIATED', 'FAILED', 'RECOVERY_ROUTED', 'RECOVERED', 'EXPIRED', 'ABANDONED')", name="ck_tx_status"),
        CheckConstraint("error_category IN ('TECHNICAL_GATEWAY', 'FRICTION_OTP_UX', 'FINANCIAL_BALANCE', 'ABANDONMENT_INTENT')", name="ck_tx_error_cat"),
    )

    merchant = relationship("MerchantModel", back_populates="transactions")
    customer = relationship("CustomerModel", back_populates="transactions")
    causal_decisions = relationship("CausalDecisionModel", back_populates="transaction")


# ==============================================================================
# 7. MODEL VERSIONS
# ==============================================================================
class ModelVersionModel(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_filename: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    training_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conformal_coverage_level: Mapped[str] = mapped_column(String(32), default="90% Nominal Coverage", nullable=False)
    is_active_production: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("model_name", "version", name="uq_model_name_ver"),
    )


# ==============================================================================
# 8. CAUSAL DECISIONS
# ==============================================================================
class CausalDecisionModel(Base):
    __tablename__ = "causal_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False, index=True)
    model_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("model_versions.id"), nullable=True)
    recommended_action: Mapped[str] = mapped_column(String(64), nullable=False)
    authorized_action: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    causal_uplift_tau_basis_points: Mapped[int] = mapped_column(Integer, nullable=False) # e.g. 3600 = +36.0%
    baseline_prob_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_prob_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    conformal_interval: Mapped[List[float]] = mapped_column(JSON, nullable=False) # [0.31, 0.41]
    confidence_tier: Mapped[str] = mapped_column(String(16), default="HIGH", nullable=False)
    conformal_calibration_status: Mapped[str] = mapped_column(String(32), default="CALIBRATED_NOMINAL_90", nullable=False)
    net_expected_utility_paise: Mapped[int] = mapped_column(BigInteger, nullable=False) # Signed Integer Paise
    dispatch_cost_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    friction_cost_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timing_recommended_window: Mapped[str] = mapped_column(String(32), default="0-24h", nullable=False)
    timing_hazard_by_window: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    shap_top_features: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    precedents_evidence: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    counter_evidence_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    network_prior_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    bandit_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    policy_evaluation_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    execution_status: Mapped[str] = mapped_column(String(32), default="AUTHORIZED", nullable=False)
    plain_english_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    localized_customer_copy: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    tee_attestation_status: Mapped[str] = mapped_column(String(32), default="ATTESTED", nullable=False)
    tee_measurement_pcr0: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    audit_block_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("confidence_tier IN ('HIGH', 'MEDIUM', 'LOW')", name="ck_decision_conf_tier"),
        CheckConstraint("execution_status IN ('AUTHORIZED', 'POLICY_OVERRIDDEN', 'REJECTED', 'PENDING_APPROVAL', 'DISPATCHED')", name="ck_decision_status"),
    )

    transaction = relationship("TransactionModel", back_populates="causal_decisions")
    outbox_entries = relationship("RecoveryOutboxModel", back_populates="decision")


# ==============================================================================
# 9. WEBHOOK INBOX
# ==============================================================================
class WebhookInboxModel(Base):
    __tablename__ = "webhook_inbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="razorpay", nullable=False)
    environment: Mapped[str] = mapped_column(String(16), default="test", nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED", nullable=False, index=True)
    payload_sanitized: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "environment", "payment_id", "event_type", "nonce", name="uq_webhook_event_dedup"),
        CheckConstraint("provider IN ('razorpay', 'whatsapp_meta', 'sms_gateway', 'bank_simulator')", name="ck_inbox_provider"),
        CheckConstraint("environment IN ('test', 'live', 'production', 'sandbox')", name="ck_inbox_env"),
        CheckConstraint("status IN ('RECEIVED', 'PROCESSING', 'PROCESSED', 'DUPLICATE_IGNORED', 'FAILED')", name="ck_inbox_status"),
    )


# ==============================================================================
# 10. IDEMPOTENCY KEYS
# ==============================================================================
class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_path: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False) # SHA-256 hex
    status: Mapped[str] = mapped_column(String(32), default="PROCESSING", nullable=False)
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("merchant_id", "idempotency_key", name="uq_idemp_merchant_key"),
        CheckConstraint("status IN ('PROCESSING', 'COMPLETED', 'FAILED')", name="ck_idemp_status"),
    )


# ==============================================================================
# 11. RECOVERY OUTBOX
# ==============================================================================
class RecoveryOutboxModel(Base):
    __tablename__ = "recovery_outbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("causal_decisions.id", ondelete="CASCADE"), nullable=True, index=True)
    case_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_masked: Mapped[str] = mapped_column(String(64), nullable=False)
    message_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False, index=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requires_operator_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by_operator_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_id", "idempotency_key", name="uq_outbox_merch_idemp"),
        CheckConstraint("status IN ('PENDING_APPROVAL', 'QUEUED', 'SENDING', 'SENT', 'FAILED', 'RETRY', 'DEAD_LETTER', 'RECONCILIATION_REQUIRED', 'CANCELLED', 'REJECTED')", name="ck_outbox_status"),
    )

    decision = relationship("CausalDecisionModel", back_populates="outbox_entries")
    dispatches = relationship("RecoveryDispatchModel", back_populates="outbox_entry")


# ==============================================================================
# 12. RECOVERY DISPATCHES
# ==============================================================================
class RecoveryDispatchModel(Base):
    __tablename__ = "recovery_dispatches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dispatch_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    outbox_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("recovery_outbox.id", ondelete="SET NULL"), nullable=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("causal_decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    action_executed: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dispatch_cost_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DISPATCHED", nullable=False)
    is_idempotent_replay: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audit_block_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('DISPATCHED', 'DELIVERED', 'OPENED', 'CLICKED', 'FAILED')", name="ck_disp_status"),
    )

    outbox_entry = relationship("RecoveryOutboxModel", back_populates="dispatches")


# ==============================================================================
# 13. PAYMENT OUTCOMES
# ==============================================================================
class PaymentOutcomeModel(Base):
    __tablename__ = "payment_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    dispatch_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("recovery_dispatches.id", ondelete="SET NULL"), nullable=True)
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    outcome_status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    recovered_amount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    time_to_recovery_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bandit_reward_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bandit_reward_value: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_id", "payment_id", name="uq_outcome_merchant_pay"),
        CheckConstraint("outcome_status IN ('PENDING', 'RECOVERED', 'FAILED', 'EXPIRED', 'SUPPRESSED')", name="ck_outcome_status"),
        CheckConstraint("recovered_amount_paise >= 0", name="ck_outcome_recovered_positive"),
    )


# ==============================================================================
# 14. AUDIT LEDGER BLOCKS (Append-Only Cryptographic Chain)
# ==============================================================================
class AuditLedgerBlockModel(Base):
    __tablename__ = "audit_ledger_blocks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=True, index=True)
    block_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    block_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_id", "block_index", name="uq_audit_seq"),
    )


# ==============================================================================
# 15. BANDIT WEIGHTS
# ==============================================================================
class BanditWeightModel(Base):
    __tablename__ = "bandit_weights"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(32), default="v1.0.0", nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    matrix_a: Mapped[List[List[float]]] = mapped_column(JSON, nullable=False) # Serialized covariance matrix
    vector_b: Mapped[List[float]] = mapped_column(JSON, nullable=False) # Serialized reward vector
    alpha: Mapped[float] = mapped_column(Numeric(5, 4), default=0.8, nullable=False)
    total_updates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_id", "model_version", "action", name="uq_bandit_merch_ver_act"),
    )


# ==============================================================================
# 16. SHARED OPT-OUT & CONSENT GOVERNANCE (Multi-Worker Persistence)
# ==============================================================================
class OperationalBase(DeclarativeBase):
    """Declarative base for operational and shared persistence tables outside core 15 entities."""

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, uuid.UUID):
                result[col.name] = str(val)
            elif isinstance(val, datetime):
                result[col.name] = val.isoformat()
            else:
                result[col.name] = val
        return result


class OptOutRegistryModel(OperationalBase):
    __tablename__ = "opt_out_registry"

    phone: Mapped[str] = mapped_column(String(32), primary_key=True)
    reason: Mapped[str] = mapped_column(String(128), default="STOP_KEYWORD", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="inbound_whatsapp", nullable=False)
    opted_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerInteractionModel(OperationalBase):
    __tablename__ = "customer_interactions"

    phone: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_interaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class OptOutAuditTrailModel(OperationalBase):
    __tablename__ = "opt_out_audit_trail"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_proof: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class ObservationalLearningRecordModel(OperationalBase):
    __tablename__ = "observational_learning_records"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    decision_timestamp_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    context_features: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    feature_vector: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True)
    action_selected: Mapped[str] = mapped_column(String(64), nullable=False)
    action_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    assignment_propensity: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    is_propensity_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), default="v1.0.0", nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), default="v1.2.0-dml", nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    reward_definition_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    observation_status: Mapped[str] = mapped_column(String(32), default="PENDING_OUTCOME", nullable=False, index=True)
    outcome_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    recovered_amount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    outcome_timestamp_utc: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    event_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    deterministic_reward: Mapped[Optional[float]] = mapped_column(Numeric(6, 4), nullable=True)
    is_eligible_for_dml: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_eligible_for_bandit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exclusion_reasons: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    correction_history: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)

