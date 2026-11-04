-- ==============================================================================
-- WAPSI MIGRATION 7: Least-Privilege Outbox Worker Job Claiming Function
-- Sequence: 20261101000007_outbox_worker_claim_function.sql
-- Status: DRAFT / DRY-RUN ONLY — DO NOT EXECUTE DIRECTLY ON HOSTED SUPABASE
-- Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, PostgreSQL 17.11)
-- ==============================================================================

-- 1. Hardened SECURITY DEFINER Function for Cross-Tenant Outbox Leasing
-- Enables background recovery workers (operating under wapsi_app) to atomically
-- claim and lease jobs across tenants WITHOUT requiring BYPASSRLS or cross-tenant SELECT grants.
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
    updated_at TIMESTAMPTZ
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
        ORDER BY o.next_attempt_at ASC
        LIMIT v_limit
        FOR UPDATE OF o SKIP LOCKED
    ),
    updated_jobs AS (
        UPDATE public.recovery_outbox o
        SET status = 'SENDING',
            worker_id = p_worker_id,
            lease_expires_at = v_lease_expires,
            updated_at = v_now
        FROM candidate_jobs c
        WHERE o.id = c.id
        RETURNING o.*
    )
    SELECT 
        u.id, u.case_id, u.payment_id, u.merchant_id, u.idempotency_key,
        u.action, u.channel, u.recipient_masked, u.message_payload,
        u.status, u.retry_count, u.max_retries, u.next_attempt_at,
        u.lease_expires_at, u.worker_id, u.last_error, u.created_at, u.updated_at
    FROM updated_jobs u
    ORDER BY u.next_attempt_at ASC;
END;
$$;

-- 2. Restrict Execution Privileges
REVOKE ALL ON FUNCTION public.claim_recovery_outbox_jobs(VARCHAR, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_recovery_outbox_jobs(VARCHAR, INTEGER, INTEGER) TO wapsi_app, service_role;
