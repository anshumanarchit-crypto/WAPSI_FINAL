-- Migration 11: Enforce Fail-Closed Tenant Context Validation on Exact-Job Claim Function
-- Replaces claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER)
-- Strictly requires app.current_merchant_id transaction setting.
-- Fails closed (returns 0 rows) on missing, empty, malformed, or mismatched context.
-- Restricts EXECUTE privilege strictly to wapsi_app.

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
    v_session_raw TEXT;
    v_session_uuid UUID;
BEGIN
    -- 1. Parameter Validation: p_job_id and p_merchant_id must be non-null
    IF p_job_id IS NULL OR p_merchant_id IS NULL THEN
        RETURN;
    END IF;

    IF p_worker_id IS NULL OR p_worker_id ~ '^\s*$' THEN
        RETURN;
    END IF;

    -- 2. Fail-Closed Tenant Context Enforcement
    -- app.current_merchant_id MUST be set in current transaction
    BEGIN
        v_session_raw := current_setting('app.current_merchant_id', true);
    EXCEPTION WHEN OTHERS THEN
        RETURN; -- Configuration parameter unreadable or missing -> fail closed
    END;

    -- Missing or empty session merchant context -> fail closed
    IF v_session_raw IS NULL OR v_session_raw ~ '^\s*$' THEN
        RETURN;
    END IF;

    -- Malformed UUID check (standard 8-4-4-4-12 hex format)
    IF v_session_raw !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
        RETURN; -- Malformed UUID session context -> fail closed
    END IF;

    -- Parse UUID (fail closed on any error)
    BEGIN
        v_session_uuid := v_session_raw::UUID;
    EXCEPTION WHEN OTHERS THEN
        RETURN; -- Malformed UUID cast failure -> fail closed
    END;

    -- Tenant Context Mismatch Guard: session context must equal p_merchant_id
    IF v_session_uuid != p_merchant_id THEN
        RETURN; -- Cross-tenant mismatch -> fail closed
    END IF;

    -- 3. Exact Candidate Selection under Dual Predicate
    RETURN QUERY
    WITH candidate AS (
        SELECT o.id AS candidate_id
        FROM public.recovery_outbox o
        WHERE o.id = p_job_id
          AND o.merchant_id = p_merchant_id  -- DUAL EXACT PREDICATE
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

-- Revoke all permissions from PUBLIC, anon, authenticated, and service_role
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM authenticated;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM service_role;

-- Grant EXECUTE exclusively to wapsi_app
GRANT EXECUTE ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) TO wapsi_app;

