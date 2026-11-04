# PHASE 6 STAGE 2D.1: FINAL DATABASE SECURITY & OPERATOR IDENTITY AUDIT REPORT

**Audit Date**: November 3, 2026  
**Auditor**: Antigravity Autonomous Security & Recovery Subsystem  
**Target Environment**: Development / Sandbox (Hosted Supabase PostgreSQL)  
**Target Outbox Job ID**: `5a6587ab-2601-4017-b396-48e3d2fc2fda`  
**Target Merchant UUID**: `04a2aaf8-8c8a-4d99-852c-cefc80e82019` (`Acme Global Technologies`)  
**Target Razorpay Link ID**: `plink_TvKucM1yXJQAZA` (Status: Unpaid, INR 10.00)  
**Target Recipient**: `+91 62600 *****` (Authorized Meta Test Handset: Arpit Jham)  
**Target Sender**: `+1 555-214-8539` (Phone Number ID: `1407090562487899`, WABA: `969727602419694`)  
**Auth Mode**: `WHATSAPP_AUTH_MODE=dashboard_sandbox` (Token: `WHATSAPP_DIAGNOSTIC_TOKEN`)  
**Audit Verdict**: **PASS — TENANT ISOLATION RE-ENFORCED & OPERATOR IDENTITY AUDITED**

---

## 1. Executive Summary

Prior to initiating any operator approval or outbound dispatch for outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda`, an in-depth security audit of the exact-job dispatch mechanism was performed, focusing on:
1. **Migration 9 Stored Procedure Tenant Isolation**: Verification of `public.claim_specific_recovery_outbox_job` ownership, `SECURITY DEFINER` execution semantics, PostgreSQL Row Level Security (RLS) interaction, and function access control lists (ACL).
2. **Operator Identity Authenticity**: Verification of whether `operator_id` submitted via the approval API or CLI runner represents a verified cryptographic identity or an attributed client assertion.

### Key Audit Findings:
1. **`SECURITY DEFINER` RLS Bypass Confirmed**: The function owner in Supabase is `postgres`, which possesses `rolbypassrls = True`. Because `claim_specific_recovery_outbox_job` executed with definer rights without an explicit `o.merchant_id = p_merchant_id` predicate, any caller granted `EXECUTE` could have claimed another tenant's outbox job if they supplied its UUID.
2. **Remediation Applied (Migration 10)**: Dropped the 3-argument function and deployed a hardened 4-argument function requiring `p_merchant_id UUID`. Enforced both `WHERE o.id = p_job_id AND o.merchant_id = p_merchant_id` and added a session-context guard (`v_session_merchant::UUID != p_merchant_id`). Tightened permissions so `PUBLIC`, `anon`, and `authenticated` roles are revoked, granting `EXECUTE` exclusively to `wapsi_app` and `service_role`.
3. **Operator Identity Ground Truth**: The WAPSI approval pipeline authenticates the **merchant tenant** via API key SHA-256 hash lookup in PostgreSQL. The `operator_id` submitted in request payloads or CLI arguments is an **asserted identity attribute** recorded into the tamper-proof approval hash and audit ledger; it is **not** an independently authenticated individual identity (such as a password, MFA session, or personal cryptographic signature).
4. **Target State Unchanged**: Target job `5a6587ab-2601-4017-b396-48e3d2fc2fda` remains strictly frozen in `PENDING_APPROVAL` status with zero mutations, zero approvals, zero worker claims, and zero outbound provider calls.

---

## 2. Section A: Database Tenant Isolation Audit

### Live PostgreSQL Catalog Inspection
Direct inspection of `pg_proc`, `pg_roles`, and `pg_class` on the live hosted Supabase cluster revealed:

| Parameter | Observed Live Value | Security Implication |
|-----------|---------------------|----------------------|
| **Function Name** | `public.claim_specific_recovery_outbox_job` | Stored procedure for single-job claim |
| **Owner Role** | `postgres` | Default administrative role in Supabase |
| **Owner `rolsuper`** | `false` | Managed cloud postgres role |
| **Owner `rolbypassrls`** | **`true`** | **Bypasses all Row-Level Security unconditionally** |
| **`prosecdef`** | **`true` (`SECURITY DEFINER`)** | Executes with privileges of owner (`postgres`) |
| **`recovery_outbox.relrowsecurity`** | `true` | Table has RLS enabled |
| **`recovery_outbox.relforcerowsecurity`**| `false` | RLS is not forced on table owner / bypass roles |
| **Original Predicate** | `WHERE o.id = p_job_id` | **Missing merchant tenant boundary** |
| **Original Permissions (`proacl`)** | `wapsi_app`, `service_role`, `postgres` | Initially allowed application execution |

### Vulnerability Analysis
In PostgreSQL, when a function is marked `SECURITY DEFINER`, queries inside the function body execute using the role and permissions of the function owner (`postgres`). Because `postgres` has `rolbypassrls = true`, PostgreSQL disables evaluation of row-level security policies (`p_outbox_manage` / `p_outbox_select`) for queries inside that function.

Consequently, Migration 9's query:
```sql
SELECT o.id FROM public.recovery_outbox o WHERE o.id = p_job_id ...
```
completely bypassed tenant RLS. If Merchant A passed the UUID of a job belonging to Merchant B, PostgreSQL would have returned and leased Merchant B's job.

### Remediation: Migration 10 Implemented & Deployed
Deployed live to hosted Supabase via [`scripts/deploy_migration_10.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/deploy_migration_10.py):
[`supabase/migrations/20261103000010_outbox_exact_job_tenant_isolation.sql`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/supabase/migrations/20261103000010_outbox_exact_job_tenant_isolation.sql)

```sql
-- 1. Drop old 3-argument function
DROP FUNCTION IF EXISTS public.claim_specific_recovery_outbox_job(UUID, VARCHAR, INTEGER);

-- 2. Create hardened 4-argument function requiring explicit p_merchant_id
CREATE OR REPLACE FUNCTION public.claim_specific_recovery_outbox_job(
    p_job_id UUID,
    p_merchant_id UUID,
    p_worker_id VARCHAR(100),
    p_lease_seconds INTEGER DEFAULT 60
)
RETURNS TABLE (...)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_lease_expiry TIMESTAMPTZ := clock_timestamp() + (LEAST(GREATEST(p_lease_seconds, 1), 3600) || ' seconds')::INTERVAL;
    v_session_merchant TEXT;
BEGIN
    IF p_job_id IS NULL OR p_merchant_id IS NULL THEN
        RETURN;
    END IF;

    IF p_worker_id IS NULL OR p_worker_id ~ '^\s*$' THEN
        RETURN;
    END IF;

    -- Session context alignment guard (defense-in-depth)
    BEGIN
        v_session_merchant := current_setting('app.current_merchant_id', true);
        IF v_session_merchant IS NOT NULL AND v_session_merchant != '' THEN
            IF v_session_merchant::UUID != p_merchant_id THEN
                RETURN;  -- Reject cross-tenant session mismatch
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
    SELECT ... FROM updated u;
END;
$$;

-- 3. Strict ACL Enforcement
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.claim_specific_recovery_outbox_job(UUID, UUID, VARCHAR, INTEGER) TO wapsi_app, service_role;
```

### Verified Live Function State
```python
{
    'proname': 'claim_specific_recovery_outbox_job',
    'args': 'p_job_id uuid, p_merchant_id uuid, p_worker_id character varying, p_lease_seconds integer',
    'owner': 'postgres',
    'is_superuser': False,
    'bypass_rls': True,
    'is_security_definer': True,
    'proacl': '{postgres=X/postgres,service_role=X/postgres,wapsi_app=X/postgres}'
}
```

---

## 3. Section B: Operator Identity Authenticity Audit

### Investigation of API & Runner Architecture
The audit reviewed [`wapsi/api/app.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/api/app.py), [`wapsi/api/schemas.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/api/schemas.py), and [`scripts/dispatch_approved_sandbox_job.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/dispatch_approved_sandbox_job.py).

#### 1. Authentication vs. Attribution
- **Tenant Authentication**: When an operator calls `POST /api/v1/recovery/outbox/{job_id}/approve`, `_verify_recovery_auth(request)` validates the incoming API key header (`Authorization: Bearer <key>`) against `public.lookup_merchant_by_api_key_hash`. This cryptographically verifies the **tenant merchant identity** (`request.state.tenant_merchant_id`).
- **Operator Attribution**: The request payload contains:
  ```json
  {
      "operator_id": "operator_arpit",
      "reason": "Sandbox manual approval"
  }
  ```
  `operator_id` is an input string validated only for length (`min_length=3, max_length=128`).
- **Audit Ground Truth**: The WAPSI application does **not** validate `operator_id` against an individual user registry (such as Supabase Auth user passwords or personal keypairs). Any caller possessing the merchant's API key can pass an arbitrary string as `operator_id`.

#### 2. Tamper-Proof Audit Guarantees Maintained
While `operator_id` is an asserted identity, the system maintains strict cryptographic and operational integrity:
- **Canonical Snapshot Hash**: `compute_approval_hash()` binds `recipient_masked`, `channel`, and `message_payload`. Any subsequent alteration to the message or recipient invalidates the approval at dispatch time.
- **Immutable Timestamp & Audit Row**: `approved_at` and `approved_by_operator_id` are recorded in the PostgreSQL row and can only be set during transition from `PENDING_APPROVAL` to `QUEUED`.
- **Schema Honesty**: Updated schema descriptions in `wapsi/api/schemas.py` from `"Authenticated operator identity approving this job"` to `"Operator identity assertion approving this job (attributed to authenticated tenant caller)"`.

#### 3. Cross-Tenant Fallback Hardening
In `approve_outbox_job_endpoint` and `reject_outbox_job_endpoint`, a preexisting fallback to `04a2aaf8-8c8a-4d99-852c-cefc80e82019` was restricted so that it **only** activates in development mode when the caller is using the explicit mock unit-test key (`00000000-0000-0000-0000-000000000001`). Real authenticated merchants can never access another merchant's outbox jobs.

---

## 4. Code Changes Summary

| File | Change Description |
|------|--------------------|
| [`supabase/migrations/20261103000010_outbox_exact_job_tenant_isolation.sql`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/supabase/migrations/20261103000010_outbox_exact_job_tenant_isolation.sql) | Deployed Migration 10: drops 3-arg function, creates 4-arg function with `p_merchant_id`, session check, and restricts ACL to `wapsi_app, service_role`. |
| [`docs/migrations/20261103000010_outbox_exact_job_tenant_isolation.sql`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/docs/migrations/20261103000010_outbox_exact_job_tenant_isolation.sql) | Mirrored Migration 10 in documentation directory. |
| [`wapsi/db/repository.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/db/repository.py) | Updated `claim_job_by_id` to accept and pass `merchant_id: Optional[uuid.UUID]` to `claim_specific_recovery_outbox_job` and SQL fallback. |
| [`wapsi/recovery/outbox.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/recovery/outbox.py) | Updated `claim_job_by_id` to pass `merchant_id` to repository and enforce `merchant_id = ?` in SQLite fallback. |
| [`wapsi/api/app.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/api/app.py) | Hardened approval/rejection endpoints: restricted mock fallback to test mock tenant ID; ensured cross-tenant approvals are rejected. |
| [`wapsi/api/schemas.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/api/schemas.py) | Updated `operator_id` documentation to clarify it is an asserted identity attribute. |
| [`tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py) | Added 8 dedicated regression tests covering tenant claim rejection, live stored procedure enforcement, tampering, and ACL. |

---

## 5. Automated Verification Results

### Stage 2D.1 Dedicated Regression Suite
Execution of `pytest -v tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py`:
- `test_1_cross_tenant_claim_is_rejected_in_sqlite`: **PASSED**
- `test_2_stored_procedure_enforces_tenant_boundary_on_postgres`: **PASSED** (0 rows on wrong/null merchant)
- `test_3_wrong_merchant_cannot_claim_live_target_job`: **PASSED** (returns `None`)
- `test_4_live_target_job_remains_unapproved_and_unclaimable`: **PASSED** (status `PENDING_APPROVAL`)
- `test_5_correct_merchant_claims_only_after_approval`: **PASSED**
- `test_6_payload_tampering_and_optout_block_dispatch`: **PASSED** (`payload integrity violation` halts worker)
- `test_7_migration_10_signature_and_acl_verification`: **PASSED** (ACL grants strictly verified)
- `test_8_operator_id_attribution_in_approval_hash`: **PASSED**
**Result: 8/8 PASSED in 8.52s**

### Comprehensive Phase 6 Test Suite
Execution of `pytest -q tests/test_phase6_*.py`:
- `tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py` (8 passed)
- `tests/test_phase6_stage2d_exact_job_isolation.py` (8 passed)
- `tests/test_phase6_stage2c_operator_approval_preparation.py` (7 passed)
- `tests/test_phase6_stage2b_sandbox_token_routing.py` (10 passed)
- `tests/test_phase6_stage2a_authorization.py` (10 passed)
- `tests/test_phase6_webhook_authentication_and_ingestion.py` (15 passed)
**Total: 58 passed, 0 failures, 2 warnings in 23.09s**

---

## 6. Live Target Job State Verification

Direct inspection of outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` in hosted PostgreSQL:

```python
Target job live state under tenant scope: {
    'id': UUID('5a6587ab-2601-4017-b396-48e3d2fc2fda'),
    'case_id': 'wapsi_case_phase6_stage2_001',
    'merchant_id': UUID('04a2aaf8-8c8a-4d99-852c-cefc80e82019'),
    'status': 'PENDING_APPROVAL',
    'channel': 'whatsapp',
    'recipient_masked': '+91****5671',
    'requires_operator_approval': True,
    'approved_by_operator_id': None,
    'approved_at': None,
    'approval_snapshot_hash': None,
    'worker_id': None,
    'retry_count': 0,
    'last_error': None
}
```

### Verified Security Invariants:
1. **Zero Database Mutations**: Status is strictly `PENDING_APPROVAL`.
2. **Zero Approvals**: `approved_by_operator_id` and `approval_snapshot_hash` remain `None`.
3. **Zero Leases**: `worker_id` remains `None`.
4. **Zero Dispatches**: 0 calls made to Meta Graph API or Razorpay API.
5. **RLS Isolation Demonstrated**: Querying without tenant scope or under an alternative merchant ID returns 0 rows.

