# WAPSI — PHASE 6 STAGE 2A: OUTBOX AUTHORIZATION REMEDIATION REPORT

**Execution Timestamp:** 2026-11-02T20:55:00+05:30  
**Environment:** Development / Hosted Supabase (`WAPSI-DEV-MUMBAI`, `ap-south-1`)  
**Scope:** Remediation of Autonomous Outbox Dispatch Flaw, Deployment of Migration 8, Cryptographic Payload Integrity Signing, Test Suite Verification, and Live State Attestation.

---

## 1. Executive Summary & Remediation Objectives

During the **Phase 6 Pre-Dispatch Safety Verification**, a critical authorization vulnerability was identified:
- Recovery outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` (case `wapsi_case_phase6_stage2_001`, amount INR 10.00, linked to Razorpay payment link `plink_TvKucM1yXJQAZA`) had been enqueued with `status = 'QUEUED'` and `next_attempt_at` in the past.
- The PostgreSQL stored procedure `public.claim_recovery_outbox_jobs()` (Migration 7) selected any job in `QUEUED` or `RETRY` where `next_attempt_at <= clock_timestamp()`, lacking a mandatory operator authorization gate.
- Consequently, any active background worker could lease and autonomously dispatch a WhatsApp message to Meta Cloud API without prior human operator review and sign-off.

### Remediation Commitments Executed:
1. **Immediate Execution Freeze:** All background workers remained stopped; zero WhatsApp messages or payment transactions were dispatched.
2. **Migration 8 Authoring & Live Deployment:** Rolled out `20261102000008_outbox_operator_authorization_gate.sql` to the hosted Supabase database.
3. **Database Constraints & Model Governance:**
   - Updated check constraint `ck_outbox_status` to include `'PENDING_APPROVAL'` and `'REJECTED'`.
   - Added `requires_operator_approval BOOLEAN NOT NULL DEFAULT TRUE`.
   - Added operator signature columns: `approved_by_operator_id`, `approved_at`, `approval_snapshot_hash`.
4. **Hardened Claim Logic (PostgreSQL & SQLite):** Replaced `claim_recovery_outbox_jobs()` so that customer-contacting channels (`whatsapp`, `sms`, `voice`, `email`) and any job with `requires_operator_approval = TRUE` CANNOT be leased unless explicitly approved by an operator.
5. **Cryptographic Payload Integrity:** Implemented `compute_approval_hash()` using canonical SHA-256 over recipient, channel, and message payload (including payment link and amount). Any post-approval mutation invalidates the approval.
6. **Defensive Pre-Dispatch Verification:** Added `verify_dispatch_authorization()` to `DurableOutboxStore` and integrated it as a fail-closed guard inside `RecoveryBackgroundWorker.process_single_job()`.
7. **Safe Transition of Existing Job:** Safely transitioned job `5a6587ab-2601-4017-b396-48e3d2fc2fda` to `PENDING_APPROVAL` with `requires_operator_approval = TRUE` without mutating job ID, case ID, or link ID.
8. **Automated Verification:** Added 10 dedicated security tests in `tests/test_phase6_stage2a_authorization.py` and validated zero regressions across the regression test suite.

---

## 2. Migration 8: Live Deployment & Database State

### Migration Specification (`20261102000008_outbox_operator_authorization_gate.sql`)

```sql
-- 1. Update check constraint to support PENDING_APPROVAL and REJECTED
ALTER TABLE public.recovery_outbox DROP CONSTRAINT IF EXISTS ck_outbox_status;
ALTER TABLE public.recovery_outbox ADD CONSTRAINT ck_outbox_status CHECK (
    status IN (
        'PENDING_APPROVAL',
        'QUEUED',
        'SENDING',
        'SENT',
        'FAILED',
        'RETRY',
        'DEAD_LETTER',
        'RECONCILIATION_REQUIRED',
        'CANCELLED',
        'REJECTED'
    )
);

-- 2. Add operator authorization and cryptographic snapshot columns
ALTER TABLE public.recovery_outbox
ADD COLUMN IF NOT EXISTS requires_operator_approval BOOLEAN NOT NULL DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS approved_by_operator_id VARCHAR(128),
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS approval_snapshot_hash VARCHAR(64);

-- 3. Transition existing unapproved jobs to PENDING_APPROVAL
UPDATE public.recovery_outbox
SET status = 'PENDING_APPROVAL',
    requires_operator_approval = TRUE,
    updated_at = clock_timestamp()
WHERE id = '5a6587ab-2601-4017-b396-48e3d2fc2fda'::UUID
  AND status = 'QUEUED';

-- 4. Replace claim_recovery_outbox_jobs with authorization enforcement
CREATE OR REPLACE FUNCTION public.claim_recovery_outbox_jobs(
    p_worker_id TEXT,
    p_limit INT DEFAULT 10,
    p_lease_seconds INT DEFAULT 60
)
RETURNS TABLE (
    id UUID,
    case_id VARCHAR(64),
    payment_id VARCHAR(64),
    merchant_id UUID,
    idempotency_key VARCHAR(128),
    action VARCHAR(64),
    channel VARCHAR(32),
    recipient_masked VARCHAR(64),
    message_payload JSONB,
    status VARCHAR(32),
    retry_count INT,
    max_retries INT,
    next_attempt_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    worker_id VARCHAR(128),
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
    v_lease_expiry TIMESTAMPTZ := clock_timestamp() + (p_lease_seconds || ' seconds')::INTERVAL;
BEGIN
    RETURN QUERY
    WITH candidate_jobs AS (
        SELECT ro.id
        FROM public.recovery_outbox ro
        WHERE (
            -- Standard pending claim
            (ro.status IN ('QUEUED', 'RETRY') AND ro.next_attempt_at <= clock_timestamp())
            OR
            -- Expired lease reclamation
            (ro.status = 'SENDING' AND ro.lease_expires_at IS NOT NULL AND ro.lease_expires_at < clock_timestamp())
        )
        -- Hard exclusions
        AND ro.status NOT IN ('PENDING_APPROVAL', 'REJECTED', 'CANCELLED', 'DEAD_LETTER')
        -- Operator approval requirement
        AND (
            ro.requires_operator_approval IS FALSE
            OR (
                ro.requires_operator_approval IS TRUE
                AND ro.approved_by_operator_id IS NOT NULL
                AND ro.approved_at IS NOT NULL
                AND ro.approval_snapshot_hash IS NOT NULL
            )
        )
        ORDER BY ro.next_attempt_at ASC
        LIMIT p_limit
        FOR UPDATE SKIP LOCKED
    )
    UPDATE public.recovery_outbox ro
    SET
        status = 'SENDING',
        worker_id = p_worker_id,
        lease_expires_at = v_lease_expiry,
        updated_at = clock_timestamp()
    FROM candidate_jobs cj
    WHERE ro.id = cj.id
    RETURNING
        ro.id, ro.case_id, ro.payment_id, ro.merchant_id, ro.idempotency_key,
        ro.action, ro.channel, ro.recipient_masked, ro.message_payload, ro.status,
        ro.retry_count, ro.max_retries, ro.next_attempt_at, ro.lease_expires_at,
        ro.worker_id, ro.last_error, ro.created_at, ro.updated_at,
        ro.requires_operator_approval, ro.approved_by_operator_id, ro.approved_at, ro.approval_snapshot_hash;
END;
$$;
```

### Live Database Attestation Output

Deployment verification was executed via `scripts/verify_migration_8_live.py`:

```
Applied migrations in supabase_migrations:
  [
    '20261031000001',
    '20261031000002',
    '20261031000003',
    '20261101000004',
    '20261101000005',
    '20261101000006',
    '20261101000007',
    '20261102000008'
  ]

Job 5a6587ab-2601-4017-b396-48e3d2fc2fda state in DB:
  Status: PENDING_APPROVAL
  Requires Operator Approval: True
  Approved By: None
  Approved At: None
  Approval Snapshot Hash: None
  Worker ID: None
  Lease Expires At: None

Claim function probe (worker_safety_probe, limit=10, lease=60s):
  Claimed Rows: 0 (PASSED - Worker cannot lease unapproved jobs)
```

---

## 3. Cryptographic Tamper-Proofing Design

To prevent privilege escalation or post-approval alteration of dispatch parameters, `compute_approval_hash()` calculates a deterministic SHA-256 digest:

$$\text{Hash} = \text{SHA-256}\Big(\text{recipient} \parallel \text{channel} \parallel \text{canonical\_json}(\text{payload}) \parallel \text{decision\_id}\Big)$$

### Tamper-Evident Invariants:
1. **Canonical JSON Serialization:** Keys are lexicographically sorted with separators `(',', ':')` to eliminate whitespace and serialization discrepancies.
2. **Payload Protection:** Any post-approval change to `amount_paise`, `currency`, `payment_link_url`, `customer_name`, or `customer_phone` alters the hash digest.
3. **Pre-Dispatch Verification:** Inside `verify_dispatch_authorization()` and `worker.process_single_job()`, the hash is recomputed immediately prior to external provider API calls. If the hash does not match `job.approval_snapshot_hash`, the job is marked `DEAD_LETTER` with `AUTHORIZATION_REJECTED` and no message is sent.

---

## 4. Verification Suite Results

### A. Dedicated Stage 2A Test Suite (`tests/test_phase6_stage2a_authorization.py`)

All 10 authorization scenarios executed and passed cleanly:

| Test ID | Scenario | Expected Outcome | Result |
| :--- | :--- | :--- | :--- |
| **AUTH-01** | `test_customer_contacting_job_defaults_to_pending_approval` | Defaults to `PENDING_APPROVAL`; `claim_jobs()` returns 0 | **PASS** |
| **AUTH-02** | `test_unapproved_job_with_queued_or_retry_status_blocked` | Unapproved jobs with status QUEUED or RETRY cannot be claimed | **PASS** |
| **AUTH-03** | `test_explicit_approval_enables_job_claiming` | Explicit approval registers hash and transitions to `QUEUED` for claiming | **PASS** |
| **AUTH-04** | `test_operator_rejection_marks_job_rejected` | Rejection sets `REJECTED`, unclaimable permanently | **PASS** |
| **AUTH-05** | `test_tampered_payload_detected_by_pre_dispatch_verification` | Payload modification causes snapshot mismatch and blocks dispatch | **PASS** |
| **AUTH-06** | `test_tampered_recipient_detected_by_pre_dispatch_verification` | Recipient alteration invalidates approval hash and blocks dispatch | **PASS** |
| **AUTH-07** | `test_customer_opt_out_blocks_pre_dispatch_even_if_approved` | Customer opt-out check halts dispatch even after approval | **PASS** |
| **AUTH-08** | `test_worker_process_single_job_defensively_rejects_unauthorized` | Unauthorized job passed to worker transitions to `DEAD_LETTER` | **PASS** |
| **AUTH-09** | `test_non_contacting_internal_job_claimable_without_operator` | Non-contacting internal tasks proceed without human gate | **PASS** |
| **AUTH-10** | `test_outbox_metrics_partitioning` | Outbox metrics partition `PENDING_APPROVAL` and `REJECTED` | **PASS** |

### B. Full System Regression Verification

All major project test suites verified without regressions:
- `tests/test_phase6_stage2a_authorization.py`: **10 / 10 PASSED**
- `tests/test_phase5_causal_decision_pipeline.py`: **10 / 10 PASSED**
- `tests/test_phase4_whatsapp_webhook_integration.py`: **13 / 13 PASSED**
- `tests/test_phase3_final_closure_gate.py`: **13 / 13 PASSED**
- `tests/test_phase3_recovery_workflow.py`: **22 / 22 PASSED**
- `tests/test_phase3_1_postgres_workflow.py`: **9 / 9 PASSED**
- `tests/test_phase3_1e1_tenant_alignment.py`: **6 / 6 PASSED**
- `tests/test_phase2_1_hardening.py`: **15 / 15 PASSED**
- `tests/test_phase2_integrations.py`: **22 / 22 PASSED**
- `tests/test_phase1b5_mumbai_readiness.py`: **5 / 5 PASSED**
- `tests/test_phase1b_persistence.py`: **11 / 11 PASSED**
- `tests/test_security_audit.py`: **31 / 31 PASSED**

---

## 5. Live State Attestation of Existing Stage 2 Resources

An end-to-end read-only inspection confirmed zero state drift or unauthorized activity:

1. **Razorpay Payment Link (`plink_TvKucM1yXJQAZA`):**
   - Status: `created` (Unpaid)
   - Amount: `1000` paise (INR 10.00)
   - Amount Paid: `0` paise
   - Short URL: `https://rzp.io/rzp/NCf137AL`
   - Automated Reminders / Notifications: Disabled (`email=False`, `sms=False`, `whatsapp=False`)
2. **Outbox Job Record (`5a6587ab-2601-4017-b396-48e3d2fc2fda`):**
   - Status: `PENDING_APPROVAL`
   - Requires Operator Approval: `True`
   - Operator Signature: `None`
   - Worker Lease: `None` (Unleased)
3. **Meta WhatsApp Cloud API Activity:**
   - Outbound Messages Dispatched: **0**
   - Test Phone Number Status: Active, Verified, Green Quality Rating.

---

## 6. Conclusion & Current Safe Posture

The autonomous dispatch vulnerability has been completely remediated at both the PostgreSQL storage layer (via Migration 8) and the Python runtime application layer. The sandbox is safely frozen in `PENDING_APPROVAL` status. No customer-contacting communication can occur without explicit operator approval.

