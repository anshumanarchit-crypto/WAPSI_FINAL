-- ==============================================================================
-- WAPSI MIGRATION 8: Durable Outbox Operator Authorization Gate & Claim Protection
-- Sequence: 20261102000008_outbox_operator_authorization_gate.sql
-- Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, PostgreSQL 17.11)
-- ==============================================================================

-- 1. Extend Status Check Constraint on recovery_outbox
-- Adds 'PENDING_APPROVAL' and 'REJECTED' to allowed outbox job statuses.
ALTER TABLE public.recovery_outbox DROP CONSTRAINT IF EXISTS ck_outbox_status;
ALTER TABLE public.recovery_outbox ADD CONSTRAINT ck_outbox_status
    CHECK (status IN (
        'PENDING_APPROVAL', 'QUEUED', 'SENDING', 'SENT', 'FAILED',
        'RETRY', 'DEAD_LETTER', 'RECONCILIATION_REQUIRED', 'CANCELLED', 'REJECTED'
    ));

-- 2. Add Operator Authorization & Cryptographic Snapshot Columns
ALTER TABLE public.recovery_outbox
    ADD COLUMN IF NOT EXISTS requires_operator_approval BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS approved_by_operator_id VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS approval_snapshot_hash VARCHAR(64) NULL;

-- 3. Create Performance & Security Index on Authorization Fields
CREATE INDEX IF NOT EXISTS idx_outbox_operator_approval
    ON public.recovery_outbox (requires_operator_approval, status, next_attempt_at);

-- 4. Transition Existing Sandbox Job to Safe PENDING_APPROVAL State
-- Transitions job 5a6587ab-2601-4017-b396-48e3d2fc2fda so it cannot be claimed autonomously.
UPDATE public.recovery_outbox
SET status = 'PENDING_APPROVAL',
    requires_operator_approval = TRUE,
    updated_at = pg_catalog.now()
WHERE id = '5a6587ab-2601-4017-b396-48e3d2fc2fda'
  AND approved_by_operator_id IS NULL;

-- Also ensure any non-contacting channel jobs do not require operator approval
UPDATE public.recovery_outbox
SET requires_operator_approval = FALSE
WHERE channel IN ('gateway', 'retry');

-- 5. Drop & Recreate public.claim_recovery_outbox_jobs with Hard Authorization Enforcement
DROP FUNCTION IF EXISTS public.claim_recovery_outbox_jobs(VARCHAR, INTEGER, INTEGER);

CREATE OR REPLACE FUNCTION public.claim_recovery_outbox_jobs(
    p_worker_id VARCHAR(64),
    p_limit INTEGER DEFAULT 10,
    p_lease_seconds INTEGER DEFAULT 60
)
RETURNS TABLE (
    id UUID,
    case_id VARCHAR(64),
    payment_id VARCHAR(128),
    merchant_id UUID,
    idempotency_key VARCHAR(128),
    action VARCHAR(64),
    channel VARCHAR(32),
    recipient_masked VARCHAR(64),
    message_payload JSONB,
    status VARCHAR(32),
    retry_count INTEGER,
    max_retries INTEGER,
    next_attempt_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    worker_id VARCHAR(64),
    last_error TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    requires_operator_approval BOOLEAN,
    approved_by_operator_id VARCHAR(128),
    approved_at TIMESTAMPTZ,
    approval_snapshot_hash VARCHAR(64)
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_now TIMESTAMPTZ := pg_catalog.now();
    v_lease_expires TIMESTAMPTZ := v_now + (LEAST(GREATEST(p_lease_seconds, 1), 3600) * interval '1 second');
    v_limit INTEGER := LEAST(GREATEST(p_limit, 1), 100);
BEGIN
    IF p_worker_id IS NULL OR p_worker_id ~ '^\s*$' THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH candidate_jobs AS (
        SELECT o.id
        FROM public.recovery_outbox o
        WHERE (
            (o.status IN ('QUEUED', 'RETRY') AND o.next_attempt_at <= v_now)
            OR
            (o.status = 'SENDING' AND o.lease_expires_at IS NOT NULL AND o.lease_expires_at < v_now)
        )
        -- HARD AUTHORIZATION GATES:
        -- 1. Unapproved or rejected jobs must NEVER be claimed
        AND o.status NOT IN ('PENDING_APPROVAL', 'REJECTED', 'CANCELLED', 'DEAD_LETTER')
        -- 2. Customer-contacting jobs MUST have verified operator approval evidence
        AND (
            o.requires_operator_approval IS FALSE
            OR (
                o.requires_operator_approval IS TRUE
                AND o.approved_by_operator_id IS NOT NULL
                AND o.approved_at IS NOT NULL
                AND o.approval_snapshot_hash IS NOT NULL
            )
        )
        ORDER BY o.next_attempt_at ASC
        LIMIT v_limit
        FOR UPDATE OF o SKIP LOCKED
    )
    UPDATE public.recovery_outbox o
    SET
        status = 'SENDING',
        worker_id = p_worker_id,
        lease_expires_at = v_lease_expires,
        updated_at = v_now
    FROM candidate_jobs c
    WHERE o.id = c.id
    RETURNING
        o.id,
        o.case_id,
        o.payment_id,
        o.merchant_id,
        o.idempotency_key,
        o.action,
        o.channel,
        o.recipient_masked,
        o.message_payload,
        o.status,
        o.retry_count,
        o.max_retries,
        o.next_attempt_at,
        o.lease_expires_at,
        o.worker_id,
        o.last_error,
        o.created_at,
        o.updated_at,
        o.requires_operator_approval,
        o.approved_by_operator_id,
        o.approved_at,
        o.approval_snapshot_hash;
END;
$$;

-- 6. Role Ownership and Least-Privilege Grants
ALTER FUNCTION public.claim_recovery_outbox_jobs(VARCHAR, INTEGER, INTEGER) OWNER TO postgres;

REVOKE ALL ON FUNCTION public.claim_recovery_outbox_jobs(VARCHAR, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_recovery_outbox_jobs(VARCHAR, INTEGER, INTEGER) TO wapsi_app, service_role;

GRANT SELECT, INSERT, UPDATE ON TABLE public.recovery_outbox TO wapsi_app;

