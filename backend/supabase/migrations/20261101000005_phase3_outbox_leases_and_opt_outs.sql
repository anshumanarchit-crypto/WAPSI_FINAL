-- ==============================================================================
-- WAPSI MIGRATION 5: Outbox Worker Leases & Shared Persistent Opt-Out Governance
-- Sequence: 20261101000005_phase3_outbox_leases_and_opt_outs.sql
-- Status: REVIEW ONLY — DO NOT EXECUTE DIRECTLY ON HOSTED SUPABASE
-- Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, PostgreSQL 17.11)
-- ==============================================================================

-- 1. Add Lease Ownership, Expiration, and Correlation Columns to recovery_outbox
ALTER TABLE public.recovery_outbox
    ADD COLUMN IF NOT EXISTS worker_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS case_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS payment_id VARCHAR(128);

-- Allow recovery outbox actions to be enqueued directly from workflow engine (make decision_id optional)
ALTER TABLE public.recovery_outbox
    ALTER COLUMN decision_id DROP NOT NULL;

-- Update check constraint on status to include RECONCILIATION_REQUIRED and CANCELLED
ALTER TABLE public.recovery_outbox DROP CONSTRAINT IF EXISTS recovery_outbox_status_check;
ALTER TABLE public.recovery_outbox DROP CONSTRAINT IF EXISTS ck_outbox_status;
ALTER TABLE public.recovery_outbox
    ADD CONSTRAINT ck_outbox_status CHECK (
        status IN ('QUEUED', 'SENDING', 'SENT', 'FAILED', 'RETRY', 'DEAD_LETTER', 'RECONCILIATION_REQUIRED', 'CANCELLED')
    );

-- High-performance partial index for concurrent worker claims with FOR UPDATE SKIP LOCKED
CREATE INDEX IF NOT EXISTS idx_outbox_worker_claim
    ON public.recovery_outbox (status, next_attempt_at, lease_expires_at)
    WHERE status IN ('QUEUED', 'RETRY');

CREATE INDEX IF NOT EXISTS idx_outbox_case_id
    ON public.recovery_outbox (case_id);

CREATE INDEX IF NOT EXISTS idx_outbox_payment_id
    ON public.recovery_outbox (payment_id);


-- 2. Shared Multi-Worker Persistent Opt-Out Registry (DPDP 2023 & Meta Compliance)
CREATE TABLE IF NOT EXISTS public.opt_out_registry (
    phone VARCHAR(32) PRIMARY KEY,
    reason VARCHAR(128) NOT NULL DEFAULT 'STOP_KEYWORD',
    source VARCHAR(64) NOT NULL DEFAULT 'inbound_whatsapp',
    opted_out_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor VARCHAR(128),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_opt_out_phone ON public.opt_out_registry (phone);
CREATE INDEX IF NOT EXISTS idx_opt_out_active ON public.opt_out_registry (phone) WHERE is_active = TRUE;


-- 3. Customer Service 24-Hour Window Tracking (Meta Messaging Policy)
CREATE TABLE IF NOT EXISTS public.customer_interactions (
    phone VARCHAR(32) PRIMARY KEY,
    last_interaction_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_interactions_phone ON public.customer_interactions (phone);


-- 4. Immutable Opt-Out Compliance Audit Trail
CREATE TABLE IF NOT EXISTS public.opt_out_audit_trail (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(32) NOT NULL,
    action VARCHAR(64) NOT NULL, -- 'OPT_OUT', 'REVOCATION', 'DUPLICATE_OPT_OUT'
    reason VARCHAR(128) NOT NULL,
    source VARCHAR(64) NOT NULL,
    consent_proof TEXT,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor VARCHAR(128)
);

CREATE INDEX IF NOT EXISTS idx_opt_out_audit_phone ON public.opt_out_audit_trail (phone, created_at_utc DESC);


-- 5. Row-Level Security Configuration
ALTER TABLE public.opt_out_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opt_out_audit_trail ENABLE ROW LEVEL SECURITY;

-- Global governance policies: regulatory opt-outs and service windows apply across tenants
DROP POLICY IF EXISTS p_opt_out_registry_all ON public.opt_out_registry;
CREATE POLICY p_opt_out_registry_all ON public.opt_out_registry
    FOR ALL TO authenticated, wapsi_app
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS p_customer_interactions_all ON public.customer_interactions;
CREATE POLICY p_customer_interactions_all ON public.customer_interactions
    FOR ALL TO authenticated, wapsi_app
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS p_opt_out_audit_trail_select ON public.opt_out_audit_trail;
CREATE POLICY p_opt_out_audit_trail_select ON public.opt_out_audit_trail
    FOR SELECT TO authenticated, wapsi_app
    USING (true);

DROP POLICY IF EXISTS p_opt_out_audit_trail_insert ON public.opt_out_audit_trail;
CREATE POLICY p_opt_out_audit_trail_insert ON public.opt_out_audit_trail
    FOR INSERT TO authenticated, wapsi_app
    WITH CHECK (true);


-- 6. Least-Privilege Grants to Restricted Application Role (wapsi_app)
GRANT SELECT, INSERT, UPDATE ON public.opt_out_registry TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.customer_interactions TO wapsi_app;
GRANT SELECT, INSERT ON public.opt_out_audit_trail TO wapsi_app;
