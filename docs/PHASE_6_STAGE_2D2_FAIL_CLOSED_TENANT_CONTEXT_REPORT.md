# PHASE 6 STAGE 2D.2: FAIL-CLOSED TENANT CONTEXT VERIFICATION REPORT

**Audit Date**: November 3, 2026  
**Auditor**: Antigravity Autonomous Security & Recovery Subsystem  
**Target Environment**: Development / Sandbox (Hosted Supabase PostgreSQL)  
**Target Outbox Job ID**: `5a6587ab-2601-4017-b396-48e3d2fc2fda`  
**Target Merchant UUID**: `04a2aaf8-8c8a-4d99-852c-cefc80e82019` (`Acme Global Technologies`)  
**Target Razorpay Link ID**: `plink_TvKucM1yXJQAZA` (Status: Unpaid, INR 10.00)  
**Target Recipient**: `+91 62600 *****` (Authorized Meta Test Handset: Arpit Jham)  
**Target Sender**: `+1 555-214-8539` (Phone Number ID: `1407090562487899`, WABA: `969727602419694`)  
**Auth Mode**: `WHATSAPP_AUTH_MODE=dashboard_sandbox` (Token: `WHATSAPP_DIAGNOSTIC_TOKEN`)  
**Audit Verdict**: **PASS — FAIL-CLOSED TENANT CONTEXT ENFORCED & VERIFIED**

---

## 1. Executive Summary

In Stage 2D.1, Migration 10 introduced an explicit `p_merchant_id UUID` parameter to `public.claim_specific_recovery_outbox_job` to prevent cross-tenant claims under `SECURITY DEFINER` execution. However, inspection identified that Migration 10 contained an exception-swallowing block:
```sql
EXCEPTION WHEN OTHERS THEN NULL;
```
If `app.current_merchant_id` was unset, empty, or contained a malformed string, this block swallowed the error and allowed execution to continue to the query.

To achieve rigorous, zero-tolerance fail-closed tenant context isolation, **Migration 11** was authored, deployed, and verified live on hosted Supabase PostgreSQL:
1. **Strict Context Requirement**: `app.current_merchant_id` is mandatory in the active database transaction.
2. **Fail-Closed Validation**: Missing, empty, malformed, or mismatched tenant contexts immediately terminate execution and return an empty result set (0 rows). Zero errors are swallowed.
3. **Dual Predicate Hardening**: Enforces BOTH `o.id = p_job_id` and `o.merchant_id = p_merchant_id`, concurrency locking (`FOR UPDATE SKIP LOCKED`), and Migration 8 operator approval integrity.
4. **Least Privilege ACL**: Privilege review confirmed `service_role` does not execute outbox operations. Permissions were tightened by revoking `service_role`, `PUBLIC`, `anon`, and `authenticated`, granting `EXECUTE` strictly to `wapsi_app`.
5. **Comprehensive Verification**: All 10 fail-closed test scenarios and the complete 68-test Phase 6 regression suite passed with 100% compliance.
6. **Zero State Mutations**: Target outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` strictly remains in `PENDING_APPROVAL` with zero operator approvals, zero worker leases, and zero outbound message transmissions.

---

## 2. Migration 10 Defect Analysis vs. Migration 11 Correction

### Vulnerability Identified in Migration 10
```sql
-- Migration 10 flawed block:
BEGIN
    v_session_merchant := current_setting('app.current_merchant_id', true);
    IF v_session_merchant IS NOT NULL AND v_session_merchant != '' THEN
        IF v_session_merchant::UUID != p_merchant_id THEN
            RETURN;
        END IF;
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL; -- [DEFECT]: Allowed execution to continue if setting was malformed or missing!
END;
```

### Fail-Closed Implementation in Migration 11
Deployed live via [`scripts/deploy_migration_11.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/deploy_migration_11.py):
[`supabase/migrations/20261103000011_outbox_fail_closed_tenant_context.sql`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/supabase/migrations/20261103000011_outbox_fail_closed_tenant_context.sql)

```sql
CREATE OR REPLACE FUNCTION public.claim_specific_recovery_outbox_job(
    p_job_id UUID,
    p_merchant_id UUID,
    p_worker_id VARCHAR(100),
    p_lease_seconds INTEGER DEFAULT 60
)
RETURNS TABLE (
    id UUID, case_id VARCHAR(64), payment_id VARCHAR(64), merchant_id UUID,
    channel VARCHAR(32), recipient_masked VARCHAR(64), message_payload JSONB,
    idempotency_key VARCHAR(128), status VARCHAR(32), retry_count INTEGER,
    max_retries INTEGER, next_attempt_at TIMESTAMPTZ, worker_id VARCHAR(100),
    lease_expires_at TIMESTAMPTZ, last_error TEXT, requires_operator_approval BOOLEAN,
    approved_by_operator_id VARCHAR(128), approved_at TIMESTAMPTZ,
    approval_snapshot_hash VARCHAR(64), created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
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
    SELECT ... FROM updated u;
END;
$$;

-- Revoke all permissions from PUBLIC, anon, authenticated, and service_role
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM authenticated;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM service_role;

-- Grant EXECUTE exclusively to wapsi_app
GRANT EXECUTE ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) TO wapsi_app;
```

---

## 3. Transaction Context Synchronization Verification

Inspection of `DatabaseManager.tenant_session_scope(merchant_id)` in [`wapsi/db/session.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/db/session.py) verified:
```python
session = self.session_factory()
try:
    m_id_str = str(merchant_id)
    if self.engine.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_merchant_id', :merchant_id, true)"),
            {"merchant_id": m_id_str},
        )
    yield session
    session.commit()
```
The parameter `is_local = true` binds `app.current_merchant_id` strictly to the active transaction. Because `claim_job_by_id` executes within `with self.db_manager.tenant_session_scope(m_uuid) as session:`, the stored procedure is executed within the **exact same transaction**, ensuring context presence and alignment without connection pollution.

---

## 4. Live Catalog & Access Control Verification

Read-only inspection of hosted PostgreSQL confirmed:

| Catalog Field | Live Value | Compliance Status |
|---------------|------------|:-----------------:|
| **Proname** | `claim_specific_recovery_outbox_job` | Verified |
| **Arguments** | `p_job_id uuid, p_merchant_id uuid, p_worker_id character varying, p_lease_seconds integer` | Verified |
| **Owner** | `postgres` | Verified |
| **`prosecdef`** | `true` (`SECURITY DEFINER`) | Verified |
| **`rolbypassrls`** | `true` | Mitigated via Migration 11 dual predicate & fail-closed context |
| **ACL Grants (`proacl`)** | `{postgres=X/postgres,wapsi_app=X/postgres}` | **Hardened (service_role revoked)** |

---

## 5. Focused Regression Test Results

### Dedicated Stage 2D.2 Suite (`tests/test_phase6_stage2d2_fail_closed_tenant_context.py`)
All 10 requested fail-closed scenarios verified:

| # | Scenario | Condition Tested | Result |
|---|----------|------------------|:------:|
| 1 | `test_01_correct_session_context_and_correct_merchant_id` | Valid transaction context & matching `p_merchant_id` executes cleanly without context error. | **PASS** |
| 2 | `test_02_missing_session_context` | Unset `app.current_merchant_id` fails closed (returns 0 rows). | **PASS** |
| 3 | `test_03_empty_session_context` | Whitespace `app.current_merchant_id = '   '` fails closed (returns 0 rows). | **PASS** |
| 4 | `test_04_malformed_uuid_session_context` | Invalid string `'not-a-valid-uuid'` fails closed via regex guard (returns 0 rows). | **PASS** |
| 5 | `test_05_mismatched_session_context` | Context `11111111-...` != `p_merchant_id` `04a2aaf8-...` fails closed (returns 0 rows). | **PASS** |
| 6 | `test_06_correct_session_context_but_wrong_p_merchant_id` | Context `04a2aaf8-...` with wrong `p_merchant_id` fails closed (returns 0 rows). | **PASS** |
| 7 | `test_07_wrong_job_id` | Non-existent job UUID returns 0 rows. | **PASS** |
| 8 | `test_08_unapproved_target_job` | Live target job in `PENDING_APPROVAL` is strictly rejected by claim procedure. | **PASS** |
| 9 | `test_09_payload_tampering` | Post-approval payload tampering detected at pre-dispatch; job moved to `DEAD_LETTER`. | **PASS** |
| 10 | `test_10_opt_out_restriction` | Customer opt-out before dispatch halts execution; job moved to `DEAD_LETTER`. | **PASS** |

### Complete Phase 6 Test Suite Results
Full regression run across all Phase 6 test suites completed with **0 failures**:
- `tests/test_phase6_stage2d2_fail_closed_tenant_context.py` (10 passed)
- `tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py` (8 passed)
- `tests/test_phase6_stage2d_exact_job_isolation.py` (8 passed)
- `tests/test_phase6_stage2c_operator_approval_preparation.py` (7 passed)
- `tests/test_phase6_stage2b_sandbox_token_routing.py` (10 passed)
- `tests/test_phase6_stage2a_authorization.py` (10 passed)
- `tests/test_phase6_webhook_authentication_and_ingestion.py` (15 passed)
- **Total: 68 passed in 20.12s**

---

## 6. Live Database State Verification (Hosted PostgreSQL)

Direct read-only inspection via [`scripts/verify_live_stage2d2.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/verify_live_stage2d2.py):
```
=== 1. LIVE FUNCTION CATALOG ===
Signature & Ownership: {
    'proname': 'claim_specific_recovery_outbox_job',
    'args': 'p_job_id uuid, p_merchant_id uuid, p_worker_id character varying, p_lease_seconds integer',
    'owner': 'postgres',
    'bypass_rls': True,
    'is_security_definer': True,
    'proacl': '{postgres=X/postgres,wapsi_app=X/postgres}'
}

=== 2. TENANT JOB VISIBILITY & CLAIMS ===
A. Target job under correct tenant scope: {
    'id': UUID('5a6587ab-2601-4017-b396-48e3d2fc2fda'),
    'status': 'PENDING_APPROVAL',
    'requires_operator_approval': True,
    'approved_by_operator_id': None,
    'approved_at': None,
    'approval_snapshot_hash': None,
    'worker_id': None,
    'retry_count': 0
}
B. Target job visible under wrong tenant scope: 0 rows (RLS enforced)
C. Claim with missing context returned: 0 rows (Fail-closed enforced)
D. Claim with malformed context returned: 0 rows (Fail-closed enforced)
E. Claim with mismatched context returned: 0 rows (Fail-closed enforced)
```

### Strict Execution Boundaries Maintained:
- **Zero approvals executed**
- **Zero workers executed**
- **Zero `POST /messages` dispatched**
- **Zero database mutations on target outbox record**
- **Zero new payment links created**

