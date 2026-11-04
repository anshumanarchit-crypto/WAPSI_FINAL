-- WAPSI Migration 2: Operational Outbox, Webhook Inbox, Audit Ledger & Bandit State
-- Project: ffgsrwjhguvubmhuefyj (Razorpay AI Buildathon 2026 - Track 3)

-- ==============================================================================
-- 9. WEBHOOK INBOX (Durable Multi-Provider Event Deduplication)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.webhook_inbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID REFERENCES public.merchants(id) ON DELETE SET NULL,
    provider VARCHAR(32) NOT NULL DEFAULT 'razorpay' CHECK (provider IN (
        'razorpay', 'whatsapp_meta', 'sms_gateway', 'bank_simulator'
    )),
    environment VARCHAR(16) NOT NULL DEFAULT 'test' CHECK (environment IN ('test', 'live', 'production', 'sandbox')),
    event_id VARCHAR(128) NOT NULL, -- Provider event identifier or composite key
    event_type VARCHAR(64) NOT NULL, -- e.g. 'payment.failed', 'payment.recovered'
    payment_id VARCHAR(128) NOT NULL,
    nonce VARCHAR(128) NOT NULL,
    signature VARCHAR(128) NOT NULL, -- HMAC signature received
    signature_verified BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(32) NOT NULL DEFAULT 'RECEIVED' CHECK (status IN (
        'RECEIVED', 'PROCESSING', 'PROCESSED', 'DUPLICATE_IGNORED', 'FAILED'
    )),
    payload_sanitized JSONB NOT NULL, -- Sanitized payload without sensitive credentials
    error_message TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT uq_webhook_event_dedup UNIQUE (provider, environment, payment_id, event_type, nonce)
);

CREATE INDEX IF NOT EXISTS idx_webhook_inbox_lookup ON public.webhook_inbox (provider, environment, payment_id);
CREATE INDEX IF NOT EXISTS idx_webhook_inbox_status ON public.webhook_inbox (status, received_at DESC);


-- ==============================================================================
-- 10. IDEMPOTENCY KEYS (Transactional API Deduplication)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    idempotency_key VARCHAR(128) NOT NULL,
    request_path VARCHAR(255) NOT NULL,
    request_hash VARCHAR(64) NOT NULL, -- SHA-256 of canonical request payload
    status VARCHAR(32) NOT NULL DEFAULT 'PROCESSING' CHECK (status IN ('PROCESSING', 'COMPLETED', 'FAILED')),
    response_status_code INTEGER,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_merchant_idempotency UNIQUE (merchant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_lookup ON public.idempotency_keys (merchant_id, idempotency_key, expires_at);


-- ==============================================================================
-- 11. RECOVERY OUTBOX (Transactional Outbox Pattern)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.recovery_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    decision_id UUID NOT NULL REFERENCES public.causal_decisions(id) ON DELETE CASCADE,
    idempotency_key VARCHAR(128) NOT NULL,
    action VARCHAR(64) NOT NULL,
    channel VARCHAR(32) NOT NULL,
    recipient_masked VARCHAR(64) NOT NULL,
    message_payload JSONB NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'QUEUED' CHECK (status IN (
        'QUEUED', 'SENDING', 'SENT', 'FAILED', 'RETRY', 'DEAD_LETTER'
    )),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_outbox_idempotency UNIQUE (merchant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_outbox_dispatch ON public.recovery_outbox (status, next_attempt_at)
    WHERE status IN ('QUEUED', 'RETRY');
CREATE INDEX IF NOT EXISTS idx_outbox_decision ON public.recovery_outbox (decision_id);


-- ==============================================================================
-- 12. RECOVERY DISPATCHES (Execution Receipts)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.recovery_dispatches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dispatch_id VARCHAR(64) UNIQUE NOT NULL, -- e.g. "disp_4f9a01b2"
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    outbox_id UUID REFERENCES public.recovery_outbox(id) ON DELETE SET NULL,
    decision_id UUID NOT NULL REFERENCES public.causal_decisions(id) ON DELETE CASCADE,
    channel VARCHAR(32) NOT NULL,
    action_executed VARCHAR(64) NOT NULL,
    provider_message_id VARCHAR(128),
    dispatch_cost_paise INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'DISPATCHED' CHECK (status IN (
        'DISPATCHED', 'DELIVERED', 'OPENED', 'CLICKED', 'FAILED'
    )),
    is_idempotent_replay BOOLEAN NOT NULL DEFAULT false,
    audit_block_hash VARCHAR(64),
    dispatched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dispatches_merchant ON public.recovery_dispatches (merchant_id, dispatched_at DESC);
CREATE INDEX IF NOT EXISTS idx_dispatches_decision ON public.recovery_dispatches (decision_id);


-- ==============================================================================
-- 13. PAYMENT OUTCOMES (Reconciliation & Online Loop Tracking)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.payment_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    transaction_id UUID NOT NULL REFERENCES public.transactions(id) ON DELETE CASCADE,
    dispatch_id UUID REFERENCES public.recovery_dispatches(id) ON DELETE SET NULL,
    payment_id VARCHAR(128) NOT NULL,
    outcome_status VARCHAR(32) NOT NULL DEFAULT 'PENDING' CHECK (outcome_status IN (
        'PENDING', 'RECOVERED', 'FAILED', 'EXPIRED', 'SUPPRESSED'
    )),
    recovered_amount_paise BIGINT NOT NULL DEFAULT 0 CHECK (recovered_amount_paise >= 0),
    time_to_recovery_seconds INTEGER,
    bandit_reward_applied BOOLEAN NOT NULL DEFAULT false,
    bandit_reward_value NUMERIC(5, 4), -- e.g. 1.0000 or 0.0000
    reconciled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_payment_outcome_payment_id UNIQUE (merchant_id, payment_id)
);

CREATE INDEX IF NOT EXISTS idx_outcomes_merchant ON public.payment_outcomes (merchant_id, outcome_status);
CREATE INDEX IF NOT EXISTS idx_outcomes_payment_id ON public.payment_outcomes (payment_id);


-- ==============================================================================
-- 14. AUDIT LEDGER BLOCKS (Cryptographic Tamper-Evident Ledger)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.audit_ledger_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID REFERENCES public.merchants(id) ON DELETE CASCADE,
    block_index BIGINT NOT NULL,
    previous_hash VARCHAR(64) NOT NULL,
    block_hash VARCHAR(64) UNIQUE NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    data_payload JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_audit_block_seq UNIQUE (merchant_id, block_index)
);

CREATE INDEX IF NOT EXISTS idx_audit_blocks_merchant ON public.audit_ledger_blocks (merchant_id, block_index ASC);
CREATE INDEX IF NOT EXISTS idx_audit_blocks_hash ON public.audit_ledger_blocks (block_hash);


-- ==============================================================================
-- 15. BANDIT WEIGHTS (Contextual LinUCB / Thompson Sampling Persistence)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.bandit_weights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
    model_version VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
    action VARCHAR(64) NOT NULL,
    matrix_a JSONB NOT NULL, -- Serialized inverse covariance / ridge matrix
    vector_b JSONB NOT NULL, -- Serialized reward vector
    alpha NUMERIC(5, 4) NOT NULL DEFAULT 0.8000,
    total_updates INTEGER NOT NULL DEFAULT 0 CHECK (total_updates >= 0),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_bandit_weights UNIQUE (merchant_id, model_version, action)
);

CREATE INDEX IF NOT EXISTS idx_bandit_weights_lookup ON public.bandit_weights (merchant_id, model_version, action);

