# WAPSI — PHASE 3.1 DEPLOYMENT PREFLIGHT REPORT

**Project Target:** WAPSI — WhatsApp Autonomous Payment Recovery System  
**Supabase Project:** `WAPSI-DEV-MUMBAI`  
**Project Reference:** `filofxijqmgluuulivxb`  
**Hosting Region:** `ap-south-1` (Mumbai, India)  
**PostgreSQL Version:** 17.11 (Hosted Supabase) / 17.9 (Local Verification Cluster)  
**Backend Repository:** `C:\Users\arpit\Desktop\Razorpay\Razorpay`  
**Active Branch:** `wapsi/phase3-recovery-workflow`  
**Preflight Status:** **VERIFIED & READY FOR HUMAN APPROVAL — ZERO HOSTED DDL EXECUTED**  

---

## Executive Summary

Phase 3.1 implementation and testing are complete. All 321 backend regression tests pass cleanly, 8/8 dedicated PostgreSQL 17 integration tests pass on an isolated local cluster, and direct catalog inspection confirms that the hosted Supabase database (`filofxijqmgluuulivxb`) remains pristine with exactly **0 synthetic rows** across all 15 public tables.

This deployment preflight report resolves the transition from the administrative `postgres` role (`BYPASSRLS = true`) to the least-privilege `wapsi_app` role (`BYPASSRLS = false`) and deploys the PostgreSQL recovery outbox lease engine and persistent opt-out governance.

```
Deployment Architecture:
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application Layer                       │
│                     (Session Pooler: Port 5432)                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ wapsi_app.filofxijqmgluuulivxb
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             Supavisor Session Pooler (aws-0-ap-south-1)                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Transaction: SET LOCAL app.current_merchant_id
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Supabase PostgreSQL 17.11 Engine                     │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Security Boundary: wapsi_app (NOBYPASSRLS, NOSUPERUSER)          │  │
│  │  - 0 DELETE grants on 15 core multi-tenant tables                │  │
│  │  - RLS Policies explicitly evaluate 'wapsi_app' + system_service │  │
│  │  - Zero access to merchant_api_keys (SECURITY DEFINER lookup)    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Outbox & Opt-Out Engine: Migration 5                             │  │
│  │  - FOR UPDATE SKIP LOCKED worker leasing                         │  │
│  │  - Shared opt-out registry & 24h customer interaction windows   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Task 1: Migration Consistency & Technical Audit

A rigorous cross-migration dependency, constraint, and syntax review was conducted between the three deployed base migrations and the two pending deployment drafts:

- **Deployed Base Migrations (`supabase/migrations/`):**
  1. `20261031000001_initial_core_schema.sql` (Creates core tables: `merchants`, `merchant_memberships`, `merchant_configurations`, `merchant_api_keys`, `customers`, `transactions`, `model_versions`, `causal_decisions`)
  2. `20261031000002_operations_outbox_audit.sql` (Creates operations tables: `webhook_inbox`, `idempotency_keys`, `recovery_outbox`, `recovery_dispatches`, `payment_outcomes`, `audit_ledger_blocks`, `bandit_weights`)
  3. `20261031000003_rls_policies_and_security.sql` (Enables RLS on 15 tables with helper functions: `current_active_merchant_id()`, `has_merchant_role()`, `update_dispatch_delivery_status()`, `prevent_audit_ledger_tampering()`)
- **Pending Deployment Drafts (`docs/migrations/`):**
  4. `20261101000004_phase1d_restricted_app_role.sql` (Creates `wapsi_app`, applies least-privilege DML grants, deploys `lookup_merchant_by_api_key_hash`, and retargets RLS policies to include `wapsi_app` and `system_service`)
  5. `20261101000005_phase3_outbox_leases_and_opt_outs.sql` (Alters `recovery_outbox` for worker leasing, creates opt-out tables with RLS and grants)

### 1.1 Dependency and Ordering Verification

| Verification Dimension | Assessment | Evidence / Technical Detail |
| :--- | :---: | :--- |
| **Object Dependency Sequence** | **PASS** | Migration 4 references only tables created in Migrations 1 & 2. Migration 5 modifies `recovery_outbox` (from Migration 2) and grants privileges to `wapsi_app` (created in Migration 4). Order $4 \rightarrow 5$ is mandatory and verified. |
| **Foreign Key Consistency** | **PASS** | Migration 5 creates `opt_out_registry` and `customer_interactions` keyed on `phone VARCHAR(32) PRIMARY KEY`. `opt_out_audit_trail` uses `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`. No invalid foreign key dependencies are introduced. |
| **Check Constraints & Enums** | **PASS** | Migration 5 drops constraints `recovery_outbox_status_check` and `ck_outbox_status` cleanly before recreating `ck_outbox_status`. All 8 statuses (`QUEUED`, `SENDING`, `SENT`, `FAILED`, `RETRY`, `DEAD_LETTER`, `RECONCILIATION_REQUIRED`, `CANCELLED`) strictly match the Python `RecoveryStatus` enum in [`wapsi/recovery/outbox.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/wapsi/recovery/outbox.py). |
| **Index Suitability** | **PASS** | Migration 5 adds `idx_outbox_worker_claim` (`WHERE status IN ('QUEUED', 'RETRY')`) supporting non-blocking concurrent worker claims with `FOR UPDATE SKIP LOCKED`. Indexes on `case_id`, `payment_id`, and `phone` are properly indexed. |
| **DML Privilege Alignment** | **PASS** | Zero `DELETE` privileges exist across all 15 core multi-tenant tables. `DELETE` is granted exclusively on `public.opt_out_registry` to allow legal opt-out revocation under DPDP 2023. |
| **Absence of Inter-Migration Conflicts** | **PASS** | Neither migration drops tables or removes production columns. `decision_id` is made nullable via `ALTER COLUMN decision_id DROP NOT NULL;` preventing failure on direct workflow dispatch. |

### 1.2 Function Signature & Allowlist Review

1. **`public.lookup_merchant_by_api_key_hash(p_hashed_key text)`:**
   - **Parameter:** `p_hashed_key text`
   - **Validation:** Strict regex check `p_hashed_key ~ '^[0-9a-f]{64}$'` and length check `length = 64`. Rejects malformed strings immediately.
   - **Search Path:** Hardened with `SET search_path = ''`. All internal schema and function references are fully qualified (`public.merchant_api_keys`, `public.merchants`, `pg_catalog.now()`, `pg_catalog.length()`).
   - **Execution Grants:** Explicitly revoked from `PUBLIC`, `anon`, and `authenticated`. Granted exclusively to `wapsi_app` and `service_role`.
   - **Return Columns:** `merchant_id uuid`, `merchant_code character varying`, `merchant_status character varying`, `key_scopes jsonb`.
2. **Helper Function Access for `wapsi_app`:**
   - `GRANT EXECUTE ON FUNCTION public.current_active_merchant_id() TO wapsi_app;`
   - `GRANT EXECUTE ON FUNCTION public.has_merchant_role(uuid, text[]) TO wapsi_app;`
   - `GRANT EXECUTE ON FUNCTION public.update_dispatch_delivery_status(character varying, character varying, character varying) TO wapsi_app;`
   - Direct execution of trigger function `prevent_audit_ledger_tampering()` is withheld.

---

## 2. Task 2: Supabase Connection Architecture

### 2.1 Connection Parameters

For secure multi-merchant runtime, the backend application must connect via the Supabase shared **Session Pooler**:

| Parameter | Operational Value | Architectural Reason |
| :--- | :--- | :--- |
| **Pooler Host** | `aws-0-ap-south-1.pooler.supabase.com` | Verified Mumbai AWS pooler endpoint (`filofxijqmgluuulivxb`) |
| **Pooler Port** | `5432` | **Session Pooler mode** (Mandatory for WAPSI) |
| **Database Name** | `postgres` | Standard Supabase primary database name |
| **Database Username** | `wapsi_app.filofxijqmgluuulivxb` | Tenant-scoped pooler user identifier |
| **Password** | *`<WAPSI_APP_PASSWORD>`* | Secure generated secret (never committed to repository) |
| **SSL Mode** | `require` | Strict TLS encryption in transit across internet boundary |

### 2.2 Connection String Template

```env
DATABASE_URL=postgresql://wapsi_app.filofxijqmgluuulivxb:<WAPSI_APP_PASSWORD>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require
```

> [!CAUTION] Credential Security Requirement
> Never write raw passwords into migrations, markdown reports, or git commits. The password for `wapsi_app` must be generated as a high-entropy string (min 32 characters, alphanumeric + symbols) and provisioned directly into the database and backend `.env`.

### 2.3 Rationale: Port 5432 (Session) vs. Port 6543 (Transaction)

Supabase provides two connection pooling modes through Supavisor:
1. **Port 6543 (Transaction Pooler):**
   - Connections are returned to the pool immediately after each transaction completes.
   - **Incompatible with WAPSI:** Transaction pooling resets or forbids session-level constructs. Prepared statements, SQLAlchemy statement caching, advisory locks, and session parameter state cannot be maintained. Attempting to execute `SET LOCAL app.current_merchant_id` across multi-statement ORM workflows in transaction pooler mode risks context bleed or query re-execution failures.
2. **Port 5432 (Session Pooler):**
   - Assigns a physical PostgreSQL server connection for the entire lifecycle of the client socket.
   - **Required for WAPSI:** Fully supports SQLAlchemy statement caching, `SELECT set_config('app.current_merchant_id', :merchant_id, true)`, transaction-scoped rollback guarantees, and concurrent `SELECT ... FOR UPDATE SKIP LOCKED` worker claims without connection eviction.

---

## 3. Task 3: Migration History & Canonical Deployment Strategy

### 3.1 Evaluation of Deployment Routes

| Deployment Route | Pros | Cons | Verdict |
| :--- | :--- | :--- | :---: |
| **Option A: Supabase Dashboard SQL Editor + Explicit Migration Tracking** | • Zero local Docker dependency.<br>• Direct administrative execution by project owner.<br>• Eliminates CLI linking authentication errors.<br>• Clean atomic verification per migration script. | • Requires manual execution of two SQL files in Dashboard.<br>• Requires running explicit version tracking SQL. | **RECOMMENDED (Canonical Route)** |
| **Option B: Supabase CLI `supabase db push`** | • Automated command line execution. | • Requires Docker Desktop running on Windows.<br>• Requires `supabase link` with access token.<br>• CLI push may trigger schema drift warnings or role ownership conflicts on managed Supabase projects. | **NOT RECOMMENDED** |

### 3.2 Canonical Deployment Procedure (Option A)

To ensure the remote database migration history matches local files and avoids duplicate application:

1. **Step 1:** Execute `docs/migrations/20261101000004_phase1d_restricted_app_role.sql` in the Supabase Dashboard SQL Editor.
2. **Step 2:** Provision the password for `wapsi_app` via SQL Editor:
   ```sql
   ALTER ROLE wapsi_app WITH PASSWORD '<STRONG_SECURE_PASSWORD>';
   ```
3. **Step 3:** Execute `docs/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql` in the Supabase Dashboard SQL Editor.
4. **Step 4:** Record the applied migrations in Supabase's internal migration registry:
   ```sql
   INSERT INTO supabase_migrations.schema_migrations (version, statements, name)
   VALUES 
       ('20261101000004', NULL, 'phase1d_restricted_app_role'),
       ('20261101000005', NULL, 'phase3_outbox_leases_and_opt_outs')
   ON CONFLICT (version) DO NOTHING;
   ```
5. **Step 5:** In the local repository, move the reviewed SQL files into `supabase/migrations/`:
   - `docs/migrations/20261101000004_phase1d_restricted_app_role.sql` $\rightarrow$ `supabase/migrations/20261101000004_phase1d_restricted_app_role.sql`
   - `docs/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql` $\rightarrow$ `supabase/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql`

This guarantees that future migrations will build on a synchronized state.

---

## 4. Task 4: Security Review & Privilege Enforcements

### 4.1 Role Privilege Matrix (`wapsi_app`)

```
PostgreSQL Role Definition:
  CREATE ROLE wapsi_app WITH
      LOGIN
      NOBYPASSRLS
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT;
```

1. **Strict `NOBYPASSRLS` Enforcement:**
   `wapsi_app` has `rolbypassrls = false`. PostgreSQL unconditionally evaluates RLS policies on every `SELECT`, `INSERT`, `UPDATE`, and `DELETE` query, even if the user has table-level DML grants.
2. **Table Non-Ownership:**
   All 15 core tables and 3 new opt-out tables remain owned by `postgres` / `supabase_admin`. Because `wapsi_app` is not an owner and lacks `SUPERUSER`, it **cannot** alter schemas, drop tables, disable triggers, or execute `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`.
3. **Zero Unrestricted DELETE Grants:**
   - Multi-tenant tables (`transactions`, `customers`, `causal_decisions`, `recovery_outbox`, `recovery_dispatches`, `audit_ledger_blocks`, etc.) have **ZERO DELETE GRANTS** to `wapsi_app`.
   - The single table with `DELETE` granted is `public.opt_out_registry`, which is legally required to handle customer opt-out revocations under Indian DPDP Act 2023.
4. **Zero Administrative `postgres` Application Fallback:**
   The backend database manager (`wapsi/db/session.py`) enforces that all application transactions connect using `DATABASE_URL` (configured as `wapsi_app`). No fallback to administrative credentials exists in code.
5. **API-Key Boundary Isolation (`merchant_api_keys`):**
   `wapsi_app` possesses zero DML grants on `merchant_api_keys`. API authentication occurs strictly through `lookup_merchant_by_api_key_hash(p_hashed_key text)` running with `SECURITY DEFINER` and `search_path = ''`. The application cannot read raw API keys, hashed keys of other tenants, or secret metadata.
6. **Custom GUC Forgery Limitation (`app.current_merchant_id`):**
   > [!IMPORTANT] Threat Model Notice: GUC Trust Boundary
   > In PostgreSQL, any client connected as `wapsi_app` can technically execute `SELECT set_config('app.current_merchant_id', '<any_uuid>', true)`. 
   > 
   > Row-Level Security ensures that queries are strictly isolated to the merchant ID configured in `app.current_merchant_id`. However, RLS cannot independently prove that the client possesses the credentials for that merchant ID.
   > 
   > Therefore, **multi-tenant isolation is co-dependent on the FastAPI application layer**:
   > - The application layer must authenticate the client API key using `lookup_merchant_by_api_key_hash`.
   > - The application layer must strictly set `app.current_merchant_id` from the *authenticated* record, never from unverified request parameters.
7. **Production Multi-Merchant Disclaimer:**
   While Phase 1D and 3.1 establish least-privilege role boundaries and RLS policies, production multi-tenant compliance requires defense-in-depth: strict egress controls, WAF rate limiting on authentication endpoints, continuous audit ledger monitoring, and credential rotation.

---

## 5. Task 5: Final Deployment Runbook (Step-by-Step 1 to 9)

Follow this precise sequence to deploy the database changes to hosted Supabase:

### Step 1: Preflight Database Health & Catalog Check
Confirm remote database availability and verify row counts before executing any changes:
```powershell
cd C:\Users\arpit\Desktop\Razorpay\Razorpay
py -3.13 scripts/verify_postgres_connection.py
```
*Expected Outcome:* PostgreSQL 17.11 connected, 15 public tables detected, 0 rows across all tables.

### Step 2: Deploy Migration 4 (`20261101000004_phase1d_restricted_app_role.sql`)
1. Open the [Supabase Dashboard SQL Editor](https://supabase.com/dashboard/project/filofxijqmgluuulivxb/sql).
2. Copy the full contents of [`docs/migrations/20261101000004_phase1d_restricted_app_role.sql`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/docs/migrations/20261101000004_phase1d_restricted_app_role.sql).
3. Paste into the SQL Editor and click **Run**.
4. Confirm output: `Success. No rows returned.`

### Step 3: Secure `wapsi_app` Password Provisioning
In the Supabase SQL Editor, execute:
```sql
-- Generate a strong 32+ character password and substitute below:
ALTER ROLE wapsi_app WITH PASSWORD '<STRONG_GENERATED_PASSWORD>';
```
*Verify role configuration:*
```sql
SELECT rolname, rolsuper, rolbypassrls, rolinherit, rolcanlogin 
FROM pg_roles 
WHERE rolname = 'wapsi_app';
```
*Expected Result:*
- `rolname`: `wapsi_app`
- `rolsuper`: `false`
- `rolbypassrls`: `false`
- `rolinherit`: `false`
- `rolcanlogin`: `true`

### Step 4: Deploy Migration 5 (`20261101000005_phase3_outbox_leases_and_opt_outs.sql`)
1. In the Supabase Dashboard SQL Editor, copy the full contents of [`docs/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/docs/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql).
2. Paste into the SQL Editor and click **Run**.
3. Confirm output: `Success. No rows returned.`
4. Record applied migrations:
```sql
INSERT INTO supabase_migrations.schema_migrations (version, statements, name)
VALUES 
    ('20261101000004', NULL, 'phase1d_restricted_app_role'),
    ('20261101000005', NULL, 'phase3_outbox_leases_and_opt_outs')
ON CONFLICT (version) DO NOTHING;
```

### Step 5: Session Pooler DATABASE_URL Configuration
1. Open [`C:\Users\arpit\Desktop\Razorpay\Razorpay\.env`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/.env).
2. Update `DATABASE_URL` to connect as `wapsi_app` via port 5432:
```env
DATABASE_URL=postgresql://wapsi_app.filofxijqmgluuulivxb:<STRONG_GENERATED_PASSWORD>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require
```

### Step 6: PostgreSQL Smoke Test as `wapsi_app`
Verify application authentication using the restricted role:
```powershell
py -3.13 scripts/verify_postgres_connection.py
```
*Checklist:*
- Connected user reports: `wapsi_app`
- `rolbypassrls` reports: `false`
- All 18 public tables (`15 core + 3 opt-out tables`) detected.

### Step 7: RLS and Least-Privilege Grant Verification
Verify that `wapsi_app` cannot bypass RLS or execute forbidden operations:
```sql
-- Run in Supabase SQL Editor to test wapsi_app restrictions:
SET ROLE wapsi_app;

-- Test 1: Selecting from merchants without context must return 0 rows (Fail-Closed)
SELECT count(*) FROM public.merchants;
-- Expected: 0

-- Test 2: Attempting direct read on merchant_api_keys must fail
SELECT * FROM public.merchant_api_keys;
-- Expected: ERROR: permission denied for table merchant_api_keys

-- Test 3: Attempting DELETE on transactions must fail
DELETE FROM public.transactions WHERE 1=1;
-- Expected: ERROR: permission denied for table transactions

RESET ROLE;
```

### Step 8: Outbox Worker Integration Verification
Verify that the recovery outbox engine can acquire leases under `wapsi_app`:
```powershell
py -3.13 -m pytest tests/test_phase3_1_postgres_workflow.py -q
```
*Expected Outcome:* 8 passed in ~10 seconds.

### Step 9: Safe Rollback Procedure
If any unexpected error occurs during deployment, execute the following rollback script in the Supabase Dashboard SQL Editor as `postgres`:

```sql
-- ROLLBACK SCRIPT FOR MIGRATIONS 4 & 5

-- 1. Remove Schema Migrations Records
DELETE FROM supabase_migrations.schema_migrations 
WHERE version IN ('20261101000004', '20261101000005');

-- 2. Drop Opt-Out Governance Tables
DROP TABLE IF EXISTS public.opt_out_audit_trail CASCADE;
DROP TABLE IF EXISTS public.customer_interactions CASCADE;
DROP TABLE IF EXISTS public.opt_out_registry CASCADE;

-- 3. Revert recovery_outbox Schema Changes
DROP INDEX IF EXISTS public.idx_outbox_worker_claim;
DROP INDEX IF EXISTS public.idx_outbox_case_id;
DROP INDEX IF EXISTS public.idx_outbox_payment_id;

ALTER TABLE public.recovery_outbox
    DROP CONSTRAINT IF EXISTS ck_outbox_status;

ALTER TABLE public.recovery_outbox
    DROP COLUMN IF EXISTS worker_id,
    DROP COLUMN IF EXISTS lease_expires_at,
    DROP COLUMN IF EXISTS case_id,
    DROP COLUMN IF EXISTS payment_id;

-- Restore original status constraint from Migration 2
ALTER TABLE public.recovery_outbox
    ADD CONSTRAINT recovery_outbox_status_check CHECK (
        status IN ('QUEUED', 'SENDING', 'SENT', 'FAILED', 'RETRY', 'DEAD_LETTER')
    );

-- 4. Revert RLS Policies to authenticated-only (Migration 3 baseline)
-- (Re-apply supabase/migrations/20261031000003_rls_policies_and_security.sql)

-- 5. Drop Hardened Functions & Role
DROP FUNCTION IF EXISTS public.lookup_merchant_by_api_key_hash(text);

-- Revoke and Drop wapsi_app
REVOKE USAGE ON SCHEMA public FROM wapsi_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM wapsi_app;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM wapsi_app;
DROP ROLE IF EXISTS wapsi_app;
```

---

## 6. Preflight Checklist & Approval Status

- [x] **Zero DDL Executed on Hosted Database:** Remote database remains on Migration 3 baseline.
- [x] **Zero Synthetic Records Written:** Hosted database verified at 0 rows across all tables.
- [x] **Full Regression Suite Verified:** 321/321 tests passing (100%).
- [x] **PostgreSQL 17 Integration Tests Verified:** 8/8 tests passing on isolated local cluster.
- [x] **Migration Files Validated:** No conflicts, no missing columns, correct check constraints.
- [x] **Credential Cleanliness:** Zero secrets or passwords exposed in code or logs.
- [x] **Rollback Plan Documented:** Clean SQL rollback script provided.

---

> [!IMPORTANT] Awaiting Human Approval
> Deployment preflight is complete and verified. No changes will be made to the hosted database without your explicit authorization.
> 
> To proceed with deployment, please authorize execution of **Step 2 through Step 5** in the Supabase Dashboard, or instruct whether you prefer an alternative workflow.

