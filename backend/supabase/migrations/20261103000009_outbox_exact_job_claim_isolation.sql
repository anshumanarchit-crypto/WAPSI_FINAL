-- ==============================================================================
-- WAPSI MIGRATION 9: Outbox Exact-Job Claim Isolation Function
-- Sequence: 20261103000009_outbox_exact_job_claim_isolation.sql
-- Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, PostgreSQL 17.11)
-- ==============================================================================

CREATE OR REPLACE FUNCTION public.claim_specific_recovery_outbox_job(
    p_job_id UUID,
    p_worker_id VARCHAR(64),
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
BEGIN
    IF p_job_id IS NULL OR p_worker_id IS NULL OR p_worker_id ~ '^\s*$' THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH candidate_job AS (
        SELECT o.id
        FROM public.recovery_outbox o
        WHERE o.id = p_job_id
        AND (
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
        FOR UPDATE OF o SKIP LOCKED
    )
    UPDATE public.recovery_outbox o
    SET
        status = 'SENDING',
        worker_id = p_worker_id,
        lease_expires_at = v_lease_expires,
        updated_at = v_now
    FROM candidate_job c
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

ALTER FUNCTION public.claim_specific_recovery_outbox_job(UUID, VARCHAR, INTEGER) OWNER TO postgres;

REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, VARCHAR, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, VARCHAR, INTEGER) TO wapsi_app, service_role;

