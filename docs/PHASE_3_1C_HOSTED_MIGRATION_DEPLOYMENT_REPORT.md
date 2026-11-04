# WAPSI — PHASE 3.1C: HOSTED SUPABASE MIGRATION DEPLOYMENT REPORT

**Project Target:** WAPSI — WhatsApp Autonomous Payment Recovery System  
**Supabase Project:** `WAPSI-DEV-MUMBAI`  
**Project Reference:** `filofxijqmgluuulivxb`  
**Hosting Region:** `ap-south-1` (Mumbai, India)  
**Database Engine:** PostgreSQL 17.11 (Hosted Supabase)  
**Backend Workspace:** `C:\Users\arpit\Desktop\Razorpay\Razorpay`  
**Active Branch:** `wapsi/phase3-recovery-workflow`  
**Deployment Date:** November 1, 2026  
**Deployment Status:** **SUCCESSFULLY DEPLOYED & VERIFIED — ALL 5 MIGRATIONS RECORDED**  

---

## 1. Executive Summary

Phase 3.1C successfully executed the authorized live deployment of database migrations `20261101000004` (Restricted Application Role & RLS Retargeting) and `20261101000005` (Outbox Worker Leases & Zero-DELETE Opt-Out Governance) to the hosted Supabase PostgreSQL 17.11 instance `WAPSI-DEV-MUMBAI` (`filofxijqmgluuulivxb`).

Live read-only catalog queries verified all security invariants:
1. Role `wapsi_app` was created with `LOGIN`, `NOBYPASSRLS`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, and `NOINHERIT`.
2. `wapsi_app` has **ZERO DELETE privileges** across all 18 public application tables.
3. `wapsi_app` has zero DML grants on sensitive credential tables `merchant_api_keys` and `merchant_memberships`.
4. `lookup_merchant_by_api_key_hash` is restricted exclusively to authorized roles.
5. `opt_out_registry` has `is_active` (boolean, not null) and `revoked_at` (timestamptz) with the partial index `idx_opt_out_active`.
6. Outbox leasing columns and nullable `decision_id` are in place.
7. Row-Level Security (RLS) is active across all 18 public tables with policies explicitly evaluating `wapsi_app`.
8. Zero synthetic data was inserted; all 18 tables verified at **0 rows**.

---

## 2. Actual CLI Deployment Output

### Command Executed:
```powershell
npx supabase@latest db push --linked
```

### Exact Raw Output:
```text
Initialising login role...
Connecting to remote database...
Applying migration 20261101000004_phase1d_restricted_app_role.sql...
Applying migration 20261101000005_phase3_outbox_leases_and_opt_outs.sql...
{"upToDate":false,"dryRun":false,"migrations":["20261101000004_phase1d_restricted_app_role.sql","20261101000005_phase3_outbox_leases_and_opt_outs.sql"],"seeds":[],"roles":[],"message":"Finished supabase db push."}
```
*Result:* Exit code `0` (Success). Both migrations applied cleanly without conflict or repair warnings.

---

## 3. Remote Migration History Verification

### Command Executed:
```powershell
npx supabase@latest migration list --linked
```

### Exact Remote Registry Output:
```json
{
  "migrations": [
    {"local": "20261031000001", "remote": "20261031000001", "time": "2026-10-31 00:00:01"},
    {"local": "20261031000002", "remote": "20261031000002", "time": "2026-10-31 00:00:02"},
    {"local": "20261031000003", "remote": "20261031000003", "time": "2026-10-31 00:00:03"},
    {"local": "20261101000004", "remote": "20261101000004", "time": "2026-11-01 00:00:04"},
    {"local": "20261101000005", "remote": "20261101000005", "time": "2026-11-01 00:00:05"}
  ],
  "message": "Migrations listed"
}
```

### Verification Findings:
- Total applied migrations: **5/5**.
- Total pending migrations: **0**.
- Remote migration tracking table (`supabase_migrations.schema_migrations`) is 100% in sync with the local repository.

---

## 4. Hosted Database Security Catalog Verification

Verification was executed via direct read-only inspection script [`scripts/verify_phase3_1c_hosted_catalog.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/verify_phase3_1c_hosted_catalog.py) connecting to hosted `filofxijqmgluuulivxb`.

### 4.1 Role Attributes (`pg_roles`)
Query:
```sql
SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolinherit
FROM pg_catalog.pg_roles WHERE rolname = 'wapsi_app';
```

| Role Attribute | Actual Hosted Value | Required Invariant | Status |
| :--- | :---: | :---: | :---: |
| `rolname` | `wapsi_app` | `wapsi_app` | **PASS** |
| `rolcanlogin` | `true` | `true` (Application login) | **PASS** |
| `rolsuper` | `false` | `false` (Non-superuser) | **PASS** |
| `rolbypassrls` | `false` | `false` (RLS Unconditionally Enforced) | **PASS** |
| `rolcreatedb` | `false` | `false` (Cannot create databases) | **PASS** |
| `rolcreaterole` | `false` | `false` (Cannot create roles) | **PASS** |
| `rolinherit` | `false` | `false` (No privilege inheritance) | **PASS** |

### 4.2 Table Privilege Verification (`information_schema.role_table_grants`)
Live query of all DML privileges granted to `wapsi_app` across the `public` schema:

| # | Public Table Name | Privileges Granted to `wapsi_app` | DELETE Privilege | Access Level |
|---|:---|:---|:---:|:---|
| 1 | `audit_ledger_blocks` | `INSERT, SELECT` | **NONE** | Append-only audit blocks |
| 2 | `bandit_weights` | `INSERT, SELECT, UPDATE` | **NONE** | Policy weights runtime |
| 3 | `causal_decisions` | `INSERT, SELECT, UPDATE` | **NONE** | Causal engine decisions |
| 4 | `customer_interactions` | `INSERT, SELECT, UPDATE` | **NONE** | Meta 24-hour service window |
| 5 | `customers` | `INSERT, SELECT, UPDATE` | **NONE** | Customer profile storage |
| 6 | `idempotency_keys` | `INSERT, SELECT, UPDATE` | **NONE** | Request idempotency |
| 7 | `merchant_configurations` | `SELECT` | **NONE** | Read-only configuration |
| 8 | `merchants` | `SELECT` | **NONE** | Read-only merchant record |
| 9 | `model_versions` | `SELECT` | **NONE** | Read-only AI model catalog |
| 10 | `opt_out_audit_trail` | `INSERT, SELECT` | **NONE** | Append-only opt-out audit trail |
| 11 | `opt_out_registry` | `INSERT, SELECT, UPDATE` | **NONE** | Status-based opt-out suppression |
| 12 | `payment_outcomes` | `INSERT, SELECT, UPDATE` | **NONE** | Payment webhook outcomes |
| 13 | `recovery_dispatches` | `INSERT, SELECT, UPDATE` | **NONE** | Message dispatch logging |
| 14 | `recovery_outbox` | `INSERT, SELECT, UPDATE` | **NONE** | Outbox worker task queue |
| 15 | `transactions` | `INSERT, SELECT, UPDATE` | **NONE** | Transaction records |
| 16 | `webhook_inbox` | `INSERT, SELECT` | **NONE** | Deduplicated webhook storage |
| 17 | `merchant_api_keys` | **NONE (0 GRANTS)** | **NONE** | Direct table access forbidden |
| 18 | `merchant_memberships` | **NONE (0 GRANTS)** | **NONE** | Direct table access forbidden |

- **Zero DELETE Invariant:** Confirmed **0 DELETE privileges** across all 18 tables.
- **Sensitive Isolation:** Tables `merchant_api_keys` and `merchant_memberships` have zero grants to `wapsi_app`.

### 4.3 Function Execution Grants (`information_schema.routine_privileges`)
Query of `lookup_merchant_by_api_key_hash`:
- `EXECUTE` granted to: `postgres` (owner), `service_role`, `wapsi_app`.
- `EXECUTE` revoked from: `PUBLIC`, `anon`, `authenticated`.
- `search_path`: Pinned to empty (`search_path = ''`).

### 4.4 Opt-Out Registry Schema & Partial Index
- Columns present: `phone`, `reason`, `source`, `opted_out_at`, `actor`, `is_active`, `revoked_at`.
- Column `is_active`: `boolean`, `is_nullable = NO`, default `'true'`.
- Column `revoked_at`: `timestamp with time zone`, `is_nullable = YES`.
- Partial index verified:
  ```sql
  CREATE INDEX idx_opt_out_active ON public.opt_out_registry USING btree (phone) WHERE (is_active = true)
  ```

### 4.5 Recovery Outbox Lease Schema
- New columns verified: `worker_id VARCHAR(64)`, `lease_expires_at TIMESTAMPTZ`, `case_id VARCHAR(64)`, `payment_id VARCHAR(128)`.
- Column `decision_id`: Confirmed `is_nullable = 'YES'`.
- Indexes verified: `idx_outbox_worker_claim` (partial index `WHERE status IN ('QUEUED', 'RETRY')`), `idx_outbox_case_id`, `idx_outbox_payment_id`.
- Constraint `ck_outbox_status`: Enforces 8 states (`QUEUED`, `SENDING`, `SENT`, `FAILED`, `RETRY`, `DEAD_LETTER`, `RECONCILIATION_REQUIRED`, `CANCELLED`).

### 4.6 Row-Level Security Policies (`pg_policies`)
RLS is active (`rowsecurity = true`) on all 18 tables in `public`. Policies explicitly target `authenticated, wapsi_app`:
- `audit_ledger_blocks`: `p_audit_blocks_select`, `p_audit_blocks_insert`, `p_audit_blocks_update_forbidden`, `p_audit_blocks_delete_forbidden`
- `bandit_weights`: `p_bandit_weights_select`, `p_bandit_weights_manage`
- `causal_decisions`: `p_decisions_select`, `p_decisions_insert`, `p_decisions_update`
- `customer_interactions`: `p_customer_interactions_all`
- `customers`: `p_customers_select`, `p_customers_manage`
- `idempotency_keys`: `p_idempotency_select`, `p_idempotency_manage`
- `merchant_configurations`: `p_configurations_select`
- `merchants`: `p_merchants_select`
- `model_versions`: `p_model_versions_select`
- `opt_out_audit_trail`: `p_opt_out_audit_trail_select`, `p_opt_out_audit_trail_insert`
- `opt_out_registry`: `p_opt_out_registry_all`
- `payment_outcomes`: `p_outcomes_select`, `p_outcomes_manage`
- `recovery_dispatches`: `p_dispatches_select`, `p_dispatches_insert`, `p_dispatches_update`
- `recovery_outbox`: `p_outbox_select`, `p_outbox_manage`
- `transactions`: `p_transactions_select`, `p_transactions_insert`, `p_transactions_update`
- `webhook_inbox`: `p_webhook_inbox_select`, `p_webhook_inbox_insert`

> [!NOTE] Catalog Verification vs. Tenant Isolation
> The passage of database catalog checks proves that the PostgreSQL permissions and policy definitions are correctly established. However, real tenant isolation also depends on the application layer properly establishing the authenticated merchant identity from API keys before invoking `SET LOCAL app.current_merchant_id`.

---

## 5. Zero Synthetic Data Confirmation

Live row-count audit across all 18 public tables:

```text
public.audit_ledger_blocks: 0 rows
public.bandit_weights: 0 rows
public.causal_decisions: 0 rows
public.customer_interactions: 0 rows
public.customers: 0 rows
public.idempotency_keys: 0 rows
public.merchant_api_keys: 0 rows
public.merchant_configurations: 0 rows
public.merchant_memberships: 0 rows
public.merchants: 0 rows
public.model_versions: 0 rows
public.opt_out_audit_trail: 0 rows
public.opt_out_registry: 0 rows
public.payment_outcomes: 0 rows
public.recovery_dispatches: 0 rows
public.recovery_outbox: 0 rows
public.transactions: 0 rows
public.webhook_inbox: 0 rows
```
**Total Rows Across Entire Database:** **0**. Zero test data, synthetic records, or dummy transactions were written to hosted Supabase.

---

## 6. Verification Status & Failed Check Summary

- **Failed Checks:** **0**.
- **Incomplete Checks:** **0**.
- **All 18 Catalog Invariants:** **100% Verified**.

---

## 7. Strict Deployment Boundary Maintained

- [x] Migrations deployed via authorized command `npx supabase db push --linked`.
- [x] Zero password provisioned or exposed for `wapsi_app` yet.
- [x] Backend `.env` remains on administrative connection (runtime has not been switched to `wapsi_app` yet).
- [x] Zero synthetic data inserted into hosted Supabase.
- [x] No recovery workers or automated jobs executed against hosted data.
- [x] No unrelated code modified.
- [x] Zero Git commits, pushes, resets, or stashes performed.

---

> [!IMPORTANT] Awaiting Next Instructions
> Hosted database migration deployment is complete and 100% catalog-verified.
> 
> As instructed, the FastAPI runtime has **not** been switched to `wapsi_app` yet. Awaiting your instructions for the next phase (e.g., secure password provisioning for `wapsi_app`, Session Pooler configuration, and multi-tenant live runtime verification).

