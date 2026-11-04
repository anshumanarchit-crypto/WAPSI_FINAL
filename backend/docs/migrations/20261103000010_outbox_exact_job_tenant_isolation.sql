-- Migration 10: Enforce Tenant Isolation on Exact-Job Claim Function
-- Replaces claim_specific_recovery_outbox_job(p_job_id, p_worker_id, p_lease_seconds)
-- with claim_specific_recovery_outbox_job(p_job_id, p_merchant_id, p_worker_id, p_lease_seconds)
-- Guarantees that SECURITY DEFINER execution cannot bypass tenant merchant isolation.

-- 1. Drop old 3-argument function
DROP FUNCTION IF EXISTS public.claim_specific_recovery_outbox_job(UUID, VARCHAR, INTEGER);

-- 2. Create new 4-argument function with strict p_merchant_id parameter
CREATE OR REPLACE FUNCTION public.claim_specific_recovery_outbox_job(
    p_job_id UUID,
    p_merchant_id UUID,
    p_worker_id VARCHAR(100),
    p_lease_seconds INTEGER DEFAULT 60
)
RETURNS TABLE (
    id UUID,
    case_id VARCHAR(64),
    payment_id VARCHAR(64),
    merchant_id UUID,
    channel VARCHAR(32),
    recipient_masked VARCHAR(64),
    message_payload JSONB,
    idempotency_key VARCHAR(128),
    status VARCHAR(32),
    retry_count INTEGER,
    max_retries INTEGER,
    next_attempt_at TIMESTAMPTZ,
    worker_id VARCHAR(100),
    lease_expires_at TIMESTAMPTZ,
    last_error TEXT,
    requires_operator_approval BOOLEAN,
    approved_by_operator_id VARCHAR(128),
    approved_at TIMESTAMPTZ,
    approval_snapshot_hash VARCHAR(64),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_lease_expiry TIMESTAMPTZ := clock_timestamp() + (LEAST(GREATEST(p_lease_seconds, 1), 3600) || ' seconds')::INTERVAL;
    v_session_merchant TEXT;
BEGIN
    -- Strict parameter validation
    IF p_job_id IS NULL OR p_merchant_id IS NULL THEN
        RETURN;
    END IF;

    IF p_worker_id IS NULL OR p_worker_id ~ '^\s*$' THEN
        RETURN;
    END IF;

    -- Defense-in-depth: If app.current_merchant_id is configured in caller session,
    -- it MUST match p_merchant_id (rejects cross-tenant impersonation attempt)
    BEGIN
        v_session_merchant := current_setting('app.current_merchant_id', true);
        IF v_session_merchant IS NOT NULL AND v_session_merchant != '' THEN
            IF v_session_merchant::UUID != p_merchant_id THEN
                RETURN;
            END IF;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    RETURN QUERY
    WITH candidate AS (
        SELECT o.id AS candidate_id
        FROM public.recovery_outbox o
        WHERE o.id = p_job_id
          AND o.merchant_id = p_merchant_id  -- INDEPENDENT TENANT BOUNDARY ENFORCEMENT
          AND o.status NOT IN ('PENDING_APPROVAL', 'REJECTED', 'CANCELLED', 'DEAD_LETTER')
          AND (
              o.status IN ('QUEUED', 'RETRY')
              OR (o.status = 'SENDING' AND o.lease_expires_at < v_now)
          )
          AND (o.next_attempt_at IS NULL OR o.next_attempt_at <= v_now)
          AND (
              o.requires_operator_approval IS FALSE
              OR (
                  o.approved_by_operator_id IS NOT NULL
                  AND o.approved_at IS NOT NULL
                  AND o.approval_snapshot_hash IS NOT NULL
              )
          )
        FOR UPDATE SKIP LOCKED
    ),
    updated AS (
        UPDATE public.recovery_outbox o
        SET
            status = 'SENDING',
            worker_id = p_worker_id,
            lease_expires_at = v_lease_expiry,
            updated_at = v_now
        FROM candidate
        WHERE o.id = candidate.candidate_id
        RETURNING o.*
    )
    SELECT
        u.id, u.case_id, u.payment_id, u.merchant_id, u.channel, u.recipient_masked,
        u.message_payload, u.idempotency_key, u.status, u.retry_count, u.max_retries,
        u.next_attempt_at, u.worker_id, u.lease_expires_at, u.last_error,
        u.requires_operator_approval, u.approved_by_operator_id, u.approved_at,
        u.approval_snapshot_hash, u.created_at, u.updated_at
    FROM updated u;
END;
$$;

-- 3. Revoke all privileges from PUBLIC, anon, and authenticated
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM authenticated;

-- 4. Grant EXECUTE exclusively to wapsi_app and service_role
GRANT EXECUTE ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) TO wapsi_app, service_role;
