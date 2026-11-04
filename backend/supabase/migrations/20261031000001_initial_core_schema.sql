-- WAPSI Migration 1: Initial Core Multi-Tenant Schema
-- Project: ffgsrwjhguvubmhuefyj (Razorpay AI Buildathon 2026 - Track 3)
-- Architecture: Decoupled Tenant Authorization, Integer Paise Monetary Precision, Complete Isolation

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 1. MERCHANTS (Tenants)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.merchants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    business_type VARCHAR(128) NOT NULL DEFAULT 'Ecommerce',
    industry VARCHAR(128) NOT NULL DEFAULT 'FinTech / Ecommerce',
    website VARCHAR(255),
    registered_email VARCHAR(255) NOT NULL,
    country VARCHAR(64) NOT NULL DEFAULT 'India',
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED', 'ONBOARDING', 'ARCHIVED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_merchants_code ON public.merchants (merchant_code);
CREATE INDEX IF NOT EXISTS idx_merchants_status ON public.merchants (status);


-- ==============================================================================
-- 2. MERCHANT MEMBERSHIPS (Decoupled User-to-Tenant Mapping)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.merchant_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL CHECK (role IN (
        'merchant_admin',
        'recovery_operator',
        'risk_officer',
        'auditor',
        'system_service'
    )),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_merchant_user UNIQUE (merchant_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_memberships_user ON public.merchant_memberships (user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_memberships_merchant ON public.merchant_memberships (merchant_id, role);


-- ==============================================================================
-- 3. MERCHANT CONFIGURATIONS
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.merchant_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID UNIQUE NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    recovery_enabled_percent INTEGER NOT NULL DEFAULT 85 CHECK (recovery_enabled_percent BETWEEN 0 AND 100),
    confidence_threshold_percent INTEGER NOT NULL DEFAULT 80 CHECK (confidence_threshold_percent BETWEEN 0 AND 100),
    min_uplift_threshold_percent INTEGER NOT NULL DEFAULT 10 CHECK (min_uplift_threshold_percent BETWEEN 0 AND 100),
    retry_attempt_limit INTEGER NOT NULL DEFAULT 3 CHECK (retry_attempt_limit >= 1),
    contact_budget_per_customer INTEGER NOT NULL DEFAULT 2 CHECK (contact_budget_per_customer >= 1),
    recovery_window_start_hour INTEGER NOT NULL DEFAULT 9 CHECK (recovery_window_start_hour BETWEEN 0 AND 23),
    recovery_window_end_hour INTEGER NOT NULL DEFAULT 21 CHECK (recovery_window_end_hour BETWEEN 0 AND 23),
    min_ivr_amount_paise BIGINT NOT NULL DEFAULT 150000 CHECK (min_ivr_amount_paise >= 0), -- ₹1,500.00
    default_merchant_margin_basis_points INTEGER NOT NULL DEFAULT 2000 CHECK (default_merchant_margin_basis_points BETWEEN 100 AND 10000), -- 20.00%
    disallowed_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    channel_settings JSONB NOT NULL DEFAULT '{"whatsapp": true, "sms": true, "email": true, "ivr": true, "smart_retry": true}'::jsonb,
    alert_preferences JSONB NOT NULL DEFAULT '{"criticalAlerts": true, "recoveryUpdates": true, "dailySummary": true, "policyViolations": true}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_merchant_configs_merchant ON public.merchant_configurations (merchant_id);


-- ==============================================================================
-- 4. MERCHANT API KEYS (Hashed Storage)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.merchant_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    key_name VARCHAR(128) NOT NULL,
    key_prefix VARCHAR(16) NOT NULL,
    key_suffix VARCHAR(8) NOT NULL,
    hashed_key VARCHAR(64) UNIQUE NOT NULL, -- SHA-256 digest
    environment VARCHAR(16) NOT NULL DEFAULT 'test' CHECK (environment IN ('test', 'live')),
    scopes JSONB NOT NULL DEFAULT '["recovery:predict", "recovery:read"]'::jsonb,
    is_revoked BOOLEAN NOT NULL DEFAULT false,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_lookup ON public.merchant_api_keys (hashed_key, is_revoked);
CREATE INDEX IF NOT EXISTS idx_api_keys_merchant ON public.merchant_api_keys (merchant_id, environment);


-- ==============================================================================
-- 5. CUSTOMERS (Pseudonymized Identity & Consent)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    merchant_customer_id VARCHAR(128) NOT NULL,
    customer_pseudonym VARCHAR(64) NOT NULL, -- HMAC-SHA256 hex
    masked_identifier VARCHAR(64) NOT NULL, -- e.g. "+91 98****1234"
    account_age_days INTEGER NOT NULL DEFAULT 0 CHECK (account_age_days >= 0),
    total_orders_count INTEGER NOT NULL DEFAULT 0 CHECK (total_orders_count >= 0),
    prior_recoveries_count INTEGER NOT NULL DEFAULT 0 CHECK (prior_recoveries_count >= 0),
    prior_failures_count INTEGER NOT NULL DEFAULT 0 CHECK (prior_failures_count >= 0),
    fatigue_score_basis_points INTEGER NOT NULL DEFAULT 1000 CHECK (fatigue_score_basis_points BETWEEN 0 AND 10000), -- 0.1000 = 10%
    opted_out BOOLEAN NOT NULL DEFAULT false,
    opted_out_at TIMESTAMPTZ,
    consent_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE_CONSENT' CHECK (consent_status IN ('ACTIVE_CONSENT', 'OPTED_OUT', 'REVOKED', 'EXPIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_customer_merchant_id UNIQUE (merchant_id, merchant_customer_id),
    CONSTRAINT uq_customer_pseudonym UNIQUE (merchant_id, customer_pseudonym)
);

CREATE INDEX IF NOT EXISTS idx_customers_merchant ON public.customers (merchant_id);
CREATE INDEX IF NOT EXISTS idx_customers_pseudonym ON public.customers (merchant_id, customer_pseudonym);


-- ==============================================================================
-- 6. TRANSACTIONS (Monetary Amounts in Integer Paise)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES public.customers(id) ON DELETE RESTRICT,
    payment_id VARCHAR(128) NOT NULL, -- Gateway payment ID e.g. "pay_998124"
    order_id VARCHAR(128),
    amount_paise BIGINT NOT NULL CHECK (amount_paise > 0), -- Strict integer paise
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    payment_method VARCHAR(32) NOT NULL CHECK (payment_method IN (
        'upi', 'card_debit', 'card_credit', 'netbanking', 'bnpl', 'wallet'
    )),
    issuer VARCHAR(64) NOT NULL DEFAULT 'HDFC',
    bin_bucket VARCHAR(32) NOT NULL DEFAULT 'classic',
    error_code VARCHAR(64) NOT NULL,
    error_category VARCHAR(32) NOT NULL CHECK (error_category IN (
        'TECHNICAL_GATEWAY', 'FRICTION_OTP_UX', 'FINANCIAL_BALANCE', 'ABANDONMENT_INTENT'
    )),
    error_description TEXT,
    attempts_used INTEGER NOT NULL DEFAULT 1 CHECK (attempts_used >= 1),
    hour_of_day INTEGER NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    is_dnd_window BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(32) NOT NULL DEFAULT 'FAILED' CHECK (status IN (
        'INITIATED', 'FAILED', 'RECOVERY_ROUTED', 'RECOVERED', 'EXPIRED', 'ABANDONED'
    )),
    failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recovered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_transactions_payment_id UNIQUE (merchant_id, payment_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_merchant ON public.transactions (merchant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_payment_id ON public.transactions (payment_id);
CREATE INDEX IF NOT EXISTS idx_transactions_customer ON public.transactions (customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON public.transactions (merchant_id, status);


-- ==============================================================================
-- 7. MODEL VERSIONS (Registry & Governance)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.model_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(64) NOT NULL,
    version VARCHAR(32) NOT NULL,
    artifact_filename VARCHAR(128) NOT NULL,
    artifact_hash_sha256 VARCHAR(64) NOT NULL,
    model_type VARCHAR(64) NOT NULL,
    training_rows INTEGER NOT NULL CHECK (training_rows >= 0),
    conformal_coverage_level VARCHAR(32) NOT NULL DEFAULT '90% Nominal Coverage',
    is_active_production BOOLEAN NOT NULL DEFAULT false,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_model_version UNIQUE (model_name, version)
);

CREATE INDEX IF NOT EXISTS idx_model_versions_active ON public.model_versions (model_name, is_active_production);


-- ==============================================================================
-- 8. CAUSAL DECISIONS (Auditable Interventions Snapshot)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.causal_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id VARCHAR(64) UNIQUE NOT NULL, -- e.g. "dec_a8f9c12e34b5"
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    transaction_id UUID NOT NULL REFERENCES public.transactions(id) ON DELETE RESTRICT,
    model_version_id UUID REFERENCES public.model_versions(id),
    recommended_action VARCHAR(64) NOT NULL,
    authorized_action VARCHAR(64) NOT NULL,
    channel VARCHAR(32) NOT NULL,
    causal_uplift_tau_basis_points INTEGER NOT NULL, -- e.g. +36.0% = 3600 bps
    baseline_prob_basis_points INTEGER NOT NULL, -- e.g. 15.0% = 1500 bps
    expected_prob_basis_points INTEGER NOT NULL, -- e.g. 51.0% = 5100 bps
    conformal_interval JSONB NOT NULL, -- [0.31, 0.41]
    confidence_tier VARCHAR(16) NOT NULL CHECK (confidence_tier IN ('HIGH', 'MEDIUM', 'LOW')),
    conformal_calibration_status VARCHAR(32) NOT NULL DEFAULT 'CALIBRATED_NOMINAL_90',
    net_expected_utility_paise BIGINT NOT NULL, -- Signed integer paise
    dispatch_cost_paise INTEGER NOT NULL DEFAULT 0,
    friction_cost_paise INTEGER NOT NULL DEFAULT 0,
    timing_recommended_window VARCHAR(32) NOT NULL DEFAULT '0-24h',
    timing_hazard_by_window JSONB NOT NULL DEFAULT '{}'::jsonb,
    shap_top_features JSONB NOT NULL DEFAULT '[]'::jsonb,
    precedents_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    counter_evidence_flag BOOLEAN NOT NULL DEFAULT false,
    network_prior_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    bandit_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_evaluation_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    execution_status VARCHAR(32) NOT NULL DEFAULT 'AUTHORIZED' CHECK (execution_status IN (
        'AUTHORIZED', 'POLICY_OVERRIDDEN', 'REJECTED', 'PENDING_APPROVAL', 'DISPATCHED'
    )),
    plain_english_rationale TEXT NOT NULL,
    localized_customer_copy JSONB NOT NULL DEFAULT '{}'::jsonb,
    tee_attestation_status VARCHAR(32) NOT NULL DEFAULT 'ATTESTED',
    tee_measurement_pcr0 VARCHAR(64),
    audit_block_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decisions_merchant ON public.causal_decisions (merchant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_transaction ON public.causal_decisions (transaction_id);
CREATE INDEX IF NOT EXISTS idx_decisions_decision_id ON public.causal_decisions (decision_id);

