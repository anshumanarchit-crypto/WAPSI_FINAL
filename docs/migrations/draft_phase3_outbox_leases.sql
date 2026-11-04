-- ==============================================================================
-- WAPSI PHASE 3 DRAFT MIGRATION: Outbox Worker Lease and Concurrency Columns
-- Status: REVIEW-ONLY DRAFT — DO NOT EXECUTE AGAINST HOSTED SUPABASE
-- ==============================================================================

-- 1. Add lease ownership and expiration columns to recovery_outbox
ALTER TABLE public.recovery_outbox
    ADD COLUMN IF NOT EXISTS worker_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS case_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS payment_id VARCHAR(128);

-- 2. Add high-performance partial index for concurrent worker claims
CREATE INDEX IF NOT EXISTS idx_outbox_worker_claim
    ON public.recovery_outbox (status, next_attempt_at, lease_expires_at)
    WHERE status IN ('QUEUED', 'RETRY');

-- 3. Document query pattern for PostgreSQL FOR UPDATE SKIP LOCKED
COMMENT ON TABLE public.recovery_outbox IS
'Transactional outbox pattern with worker leasing. Claim queries should execute:
SELECT id FROM public.recovery_outbox
WHERE status IN (''QUEUED'', ''RETRY'')
  AND next_attempt_at <= clock_timestamp()
  AND (lease_expires_at IS NULL OR lease_expires_at < clock_timestamp())
ORDER BY next_attempt_at ASC
LIMIT :batch_size
FOR UPDATE SKIP LOCKED;';

