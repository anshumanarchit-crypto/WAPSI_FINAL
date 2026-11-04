# WAPSI Phase 3.1D.1: API-Key Lookup Function Fix Report

**Project:** WAPSI — WhatsApp Autonomous Payment Recovery System  
**Target Cluster:** `WAPSI-DEV-MUMBAI` (`filofxijqmgluuulivxb`, AWS `ap-south-1`)  
**Engine:** PostgreSQL 17.11  
**Active Branch:** `wapsi/phase3-recovery-workflow`  
**Execution Date:** 2026-11-01  
**Status:** COMPLETE (Ready for Review & Deployment)

---

## 1. Executive Summary

During the Phase 3.1D secure application role provisioning and verification run, the initial stages succeeded:
- Strong role password provisioned via secure interactive prompt.
- Independent TLS Session Pooler connection (`wapsi_app.filofxijqmgluuulivxb:5432`) verified.
- Raw `psycopg2` and `SQLAlchemy 2.0.36` engine connectivity verified.
- Permitted table `SELECT` operations across 16 tables verified (0 records).
- Prohibited `SELECT` access on `merchant_api_keys` and `merchant_memberships` verified (42501).
- Prohibited `DELETE` privileges across operational tables verified (42501).

However, during test 4.4 (`SELECT * FROM public.lookup_merchant_by_api_key_hash('...')`), PostgreSQL raised:
```
column m.merchant_id does not exist
```

Phase 3.1D.1 identifies the exact root cause, creates forward-fix migration `20261101000006_fix_api_key_lookup_function.sql`, validates the fix against 19 local PostgreSQL 17 regression tests (full suite **344/344 passed**), verifies the official Supabase CLI linked dry-run, and prepares a non-mutating verification utility for subsequent execution without password rotation.

---

## 2. Root Cause Analysis

### 2.1 Failing Query in Migration 4 (`20261101000004_phase1d_restricted_app_role.sql`)
```sql
CREATE OR REPLACE FUNCTION public.lookup_merchant_by_api_key_hash(p_hashed_key text)
RETURNS TABLE (
    merchant_id uuid,
    merchant_code character varying,
    merchant_status character varying,
    key_scopes jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    ...
    RETURN QUERY
    SELECT 
        k.merchant_id,
        m.merchant_id AS merchant_code,  -- <-- ROOT CAUSE: m.merchant_id does not exist
        m.status AS merchant_status,
        k.scopes::jsonb AS key_scopes
    FROM public.merchant_api_keys k
    JOIN public.merchants m ON m.id = k.merchant_id
    WHERE k.hashed_key = p_hashed_key
      AND k.is_revoked = false
      AND (k.expires_at IS NULL OR k.expires_at > pg_catalog.now())
      AND m.status = 'ACTIVE';
END;
$$;
```

### 2.2 Actual Deployed Catalog Schema

Inspection of `information_schema.columns` on `WAPSI-DEV-MUMBAI` and `wapsi/db/models.py` confirms:

| Table | Column | Type | Nullable | Role / Semantics |
| :--- | :--- | :--- | :--- | :--- |
| **`public.merchants`** | `id` | `uuid` | `NO` | Primary Key (UUID) |
| | `merchant_code` | `character varying(64)` | `NO` | External Alphanumeric Identifier (e.g. `MRC_928374`) |
| | `name` | `character varying(255)` | `NO` | Merchant legal/trading name |
| | `status` | `character varying(32)` | `NO` | Lifecycle Status (`ACTIVE`, `SUSPENDED`, etc.) |
| **`public.merchant_api_keys`** | `id` | `uuid` | `NO` | Primary Key (UUID) |
| | `merchant_id` | `uuid` | `NO` | Foreign Key referencing `public.merchants(id)` |
| | `hashed_key` | `character varying(64)` | `NO` | SHA-256 Digest of API Key (Unique) |
| | `scopes` | `jsonb` | `NO` | Granted Scopes (e.g. `["recovery:predict"]`) |
| | `is_revoked` | `boolean` | `NO` | Revocation Flag |
| | `expires_at` | `timestamptz` | `YES` | Optional Expiry Timestamp |

### 2.3 Semantic Mapping Resolution

1. Table `public.merchants` has **no column named `merchant_id`**.
2. Table `public.merchants` primary key is `id` (`uuid`), which is joined to `k.merchant_id`.
3. Table `public.merchants` contains `merchant_code` (`varchar(64)`), which stores the external alphanumeric merchant identifier (e.g. `MRC_928374` or `MERCH_ACTIVE_001`).
4. The function returns `TABLE (merchant_id uuid, merchant_code character varying, merchant_status character varying, key_scopes jsonb)`.
5. Therefore:
   - `merchant_id` $\leftarrow$ `k.merchant_id` (or `m.id`)
   - `merchant_code` $\leftarrow$ `m.merchant_code` (resolving the typo `m.merchant_id`)
   - `merchant_status` $\leftarrow$ `m.status`
   - `key_scopes` $\leftarrow$ `k.scopes::jsonb`

Replacing `m.merchant_id` with `m.merchant_code` restores semantic alignment between the database schema, the declared function return type, and the application's multi-tenant authentication model.

---

## 3. Forward-Fix Migration: `20261101000006_fix_api_key_lookup_function.sql`

The migration was staged in `supabase/migrations/` and mirrored in `docs/migrations/`:
- `supabase/migrations/20261101000006_fix_api_key_lookup_function.sql`
- `docs/migrations/20261101000006_fix_api_key_lookup_function.sql`

### 3.1 Migration File Checksums
```
Algorithm: SHA256
Hash:      7091770F945704ABA983DA8AB74BC1CF6E54D739088E4FE08EDCE3318F1D32EB
Status:    IDENTICAL (Review Copy matches Staged Migration exactly)
```

### 3.2 SQL Implementation
```sql
-- ==============================================================================
-- WAPSI — Migration 20261101000006: Fix API-Key Lookup Function Column Reference
-- Target: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb)
-- Forward-Fix: Corrects m.merchant_id -> m.merchant_code in public.lookup_merchant_by_api_key_hash
-- Schema Alignment:
--   - public.merchants: primary key is 'id' (UUID), external identifier is 'merchant_code' (VARCHAR(64))
--   - public.merchant_api_keys: foreign key 'merchant_id' references public.merchants(id)
-- Security: Preserves SECURITY DEFINER, SET search_path = '', strict SHA-256 validation,
--           read-only execution, and least-privilege EXECUTE grants to wapsi_app & service_role.
-- ==============================================================================

CREATE OR REPLACE FUNCTION public.lookup_merchant_by_api_key_hash(p_hashed_key text)
RETURNS TABLE (
    merchant_id uuid,
    merchant_code character varying,
    merchant_status character varying,
    key_scopes jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    -- Strict input validation: SHA-256 hex string (exactly 64 hex characters)
    IF p_hashed_key IS NULL 
       OR pg_catalog.length(p_hashed_key) != 64 
       OR p_hashed_key !~ '^[0-9a-f]{64}$' THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT 
        k.merchant_id,
        m.merchant_code AS merchant_code,
        m.status AS merchant_status,
        k.scopes::jsonb AS key_scopes
    FROM public.merchant_api_keys k
    JOIN public.merchants m ON m.id = k.merchant_id
    WHERE k.hashed_key = p_hashed_key
      AND k.is_revoked = false
      AND (k.expires_at IS NULL OR k.expires_at > pg_catalog.now())
      AND m.status = 'ACTIVE';
END;
$$;

-- Explicitly enforce function ownership and least-privilege execution permissions
ALTER FUNCTION public.lookup_merchant_by_api_key_hash(text) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.lookup_merchant_by_api_key_hash(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lookup_merchant_by_api_key_hash(text) TO wapsi_app, service_role;
```

### 3.3 Security Invariants Preserved
- **Function Replacement:** Uses `CREATE OR REPLACE FUNCTION` without dropping (function signature and return type are completely preserved).
- **Security Definer & Pinned Search Path:** Preserves `SECURITY DEFINER` and `SET search_path = ''`.
- **Fully Qualified References:** All schema objects are qualified (`public.merchant_api_keys`, `public.merchants`, `pg_catalog.length`, `pg_catalog.now()`).
- **Input Validation:** Strict regex `^[0-9a-f]{64}$` and length validation prevents malformed queries and injection attempts.
- **Strict Read-Only:** Zero writes; does not touch `last_used_at` during lookup.
- **Least-Privilege Execution:** Revoked from `PUBLIC`, `anon`, and `authenticated`. Granted exclusively to `wapsi_app` and `service_role`.
- **Zero DELETE Invariant:** No `DELETE` privileges granted anywhere.

---

## 4. Local PostgreSQL Regression Testing

A dedicated test suite was implemented in [`tests/test_phase3_1d1_lookup_function.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/tests/test_phase3_1d1_lookup_function.py) using an isolated temporary PostgreSQL 17 test cluster (port 5439) with migrations 1–6 applied.

### 4.1 Test Results Summary

| # | Test Case | Target Requirement | Verdict |
| :--- | :--- | :--- | :--- |
| 1 | `test_valid_api_key_lookup` | Valid SHA-256 hash returns correct `merchant_id`, `merchant_code`, `status`, `scopes` | **PASSED** |
| 2 | `test_valid_key_with_future_expiry` | Active key with `expires_at > now()` returns merchant identity | **PASSED** |
| 3 | `test_unknown_hash_returns_empty` | Nonexistent hash returns 0 rows safely | **PASSED** |
| 4 | `test_revoked_key_rejected` | Key with `is_revoked = true` returns 0 rows | **PASSED** |
| 5 | `test_expired_key_rejected` | Key with `expires_at < now()` returns 0 rows | **PASSED** |
| 6 | `test_inactive_merchant_rejected` | Key belonging to `status = 'SUSPENDED'` merchant returns 0 rows | **PASSED** |
| 7 | `test_invalid_hash_format_fails_closed` (9 cases) | Malformed input (NULL, empty, len 63, len 65, invalid hex, uppercase, whitespace, SQL injection) returns 0 rows | **PASSED** (9/9) |
| 8 | `test_return_field_names_and_types` | Verifies column names (`merchant_id`, `merchant_code`, `merchant_status`, `key_scopes`) and types (UUID, str, str, list) | **PASSED** |
| 9 | `test_wapsi_app_can_execute_function` | Role `wapsi_app` successfully executes lookup function | **PASSED** |
| 10 | `test_wapsi_app_cannot_select_merchant_api_keys` | Direct `SELECT * FROM merchant_api_keys` by `wapsi_app` raises `42501 InsufficientPrivilege` | **PASSED** |
| 11 | `test_public_anon_authenticated_cannot_execute` | `anon` and `authenticated` roles executing the function raise `42501 InsufficientPrivilege` | **PASSED** |

**Local Regression Verdict:** **19/19 passed** in 15.93s.  
**Full Backend Regression Suite:** **344/344 passed** in 154.69s.

---

## 5. Migration Staging & Supabase CLI Dry-Run

### 5.1 Remote Migration List (`npx supabase@latest migration list --linked`)
```json
{
  "migrations": [
    {"local": "20261031000001", "remote": "20261031000001", "time": "2026-10-31 00:00:01"},
    {"local": "20261031000002", "remote": "20261031000002", "time": "2026-10-31 00:00:02"},
    {"local": "20261031000003", "remote": "20261031000003", "time": "2026-10-31 00:00:03"},
    {"local": "20261101000004", "remote": "20261101000004", "time": "2026-11-01 00:00:04"},
    {"local": "20261101000005", "remote": "20261101000005", "time": "2026-11-01 00:00:05"},
    {"local": "20261101000006", "remote": "", "time": "2026-11-01 00:00:06"}
  ],
  "message": "Migrations listed"
}
```
Migrations 1–5 are deployed on `WAPSI-DEV-MUMBAI`. Migration 6 is the only pending migration.

### 5.2 Dry-Run Output (`npx supabase@latest db push --dry-run --linked`)
```
Initialising login role...
DRY RUN: migrations will *not* be pushed to the database.
Connecting to remote database...
Would push these migrations:
 • 20261101000006_fix_api_key_lookup_function.sql
{"upToDate":false,"dryRun":true,"migrations":["20261101000006_fix_api_key_lookup_function.sql"],"seeds":[],"roles":[],"message":"Finished supabase db push."}
```
The dry-run succeeds with zero errors, proposing strictly Migration 6.

---

## 6. Phase 3.1D Follow-Up & Non-Mutating Verification Utility

### 6.1 Status of Initial Phase 3.1D Run
1. `wapsi_app` password was altered and provisioned successfully in the remote database.
2. Independent TLS connection to Session Pooler (`port 5432`) as `wapsi_app` succeeded.
3. Raw psycopg2 and SQLAlchemy connection tests succeeded.
4. Permitted SELECTs on all 16 application tables succeeded (0 synthetic rows).
5. Permission denial (42501) on `merchant_api_keys` and `merchant_memberships` succeeded.
6. Permission denial (42501) on `DELETE` queries succeeded.
7. Step 4.4 encountered `column m.merchant_id does not exist` and halted before executing RLS context tests and writing `docs/.phase3_1d_provision_evidence.json`.

### 6.2 Non-Mutating Verification Script
To avoid password re-alteration, [`scripts/verify_wapsi_app_role.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/verify_wapsi_app_role.py) was created:
- It **never executes `ALTER ROLE`**.
- It prompts for the existing password (or reads `WAPSI_APP_PASSWORD`).
- It runs the full suite of Session Pooler, SQLAlchemy, permitted SELECT, denied direct access, denied DELETE, `lookup_merchant_by_api_key_hash`, and transaction-local RLS isolation tests.
- Once Migration 6 is applied, running this script completes all checks and generates `docs/.phase3_1d_provision_evidence.json`.

---

## 7. Operational Checkpoint & Next Steps

All Phase 3.1D.1 preparation and verification tasks are complete.

Per the strict boundary instructions:
- **No live `db push` has been performed.**
- **No passwords have been altered.**
- **`.env` has not been modified.**
- **The FastAPI runtime has not been switched.**
- **Hosted Supabase contains 0 synthetic rows.**
- **Git modifications remain uncommitted.**

**Awaiting user authorization to deploy Migration 6 to hosted Supabase.**

