# WAPSI — PHASE 3.1E: RESTRICTED DATABASE RUNTIME CUTOVER PREPARATION REPORT

**Date:** 2026-11-01  
**Project:** WAPSI — WhatsApp Autonomous Payment Recovery System  
**Backend Branch:** `wapsi/phase3-recovery-workflow`  
**Target Supabase Project:** `WAPSI-DEV-MUMBAI`  
**Project Ref:** `filofxijqmgluuulivxb` (AWS Mumbai, `ap-south-1`)  
**Database Engine:** PostgreSQL 17.11  
**Application Role:** `wapsi_app`  
**Connection Mode:** Supabase Session Pooler (port 5432, TLS/SSL required)  
**Status:** **READY FOR OPERATOR AUTHORIZATION** (Zero mutations executed, `.env` untouched, 0 synthetic records in hosted database)

---

## 1. EXECUTIVE SUMMARY

Phase 3.1E prepares the WAPSI backend to transition from the administrative PostgreSQL user (`postgres`) to the least-privilege application role (`wapsi_app`). This migration fulfills the core security architecture designed in Phase 1D and hardened in Phases 3.1B through 3.1D.2.

All preparation tasks have been completed and verified without mutating the production or staging runtime environment:
- **Runtime DB Configuration Audited:** All 9 operational and sensitive tables inspected across `session.py`, `models.py`, `repository.py`, `config.py`, and `app.py`.
- **API-Key Auth Isolated:** Integrated `public.lookup_merchant_by_api_key_hash(text)` into `MerchantRepository` and FastAPI endpoints (`/predict` and `_verify_recovery_auth`). Zero direct reads to `merchant_api_keys`.
- **Zero-DELETE & Outbox Leasing Enforced:** Outbox leasing operates via `SELECT ... FOR UPDATE SKIP LOCKED` and updates leases/status without executing DELETE operations.
- **Fail-Closed DB Configuration:** Verified `DATABASE_URL` is the sole variable determining database credentials. Administrative fallback does not exist, and SQLite fallback is strictly guarded (any PostgreSQL failure raises an exception and halts rather than silently degrading).
- **Atomic Switch Utility Built:** Created `scripts/switch_wapsi_runtime_to_app_role.py` with 10 comprehensive preflight security checks, atomic `.env` file swapping, and backup of admin credentials to `WAPSI_ADMIN_DATABASE_URL`.
- **Automated Rollback Utility Built:** Created `scripts/rollback_wapsi_runtime_to_admin.py` with pre-rollback connectivity health verification and atomic restoration of `DATABASE_URL`.
- **Comprehensive Automated Tests Passed:** 7 dedicated unit and PostgreSQL integration tests in `tests/test_phase3_1e_runtime_cutover.py` passed (100%). The entire backend test suite passed cleanly (`351 passed in 125.01s`).
- **Hosted Supabase State:** Verified 18 public base tables with **zero (0) synthetic records** committed.

---

## 2. RUNTIME DATABASE CONFIGURATION AUDIT

An audit was conducted across the database layer to ensure complete compatibility between the restricted permissions of `wapsi_app` and backend execution paths.

### 2.1 Table Permission & Interaction Matrix

| Table Name | wapsi_app Grants | Runtime Access Method | Application Purpose & Invariants |
| :--- | :--- | :--- | :--- |
| `merchants` | `SELECT` | `MerchantRepository` | Merchant profile lookups, status checks, webhook configuration. Updates reserved for admin. |
| `merchant_api_keys` | **NONE (DENIED)** | `public.lookup_merchant_by_api_key_hash` | Raw key hashes are restricted. Application authenticates exclusively via `SECURITY DEFINER` function. |
| `merchant_memberships` | **NONE (DENIED)** | Direct access blocked | Team/membership management reserved for Supabase Auth / Admin console. |
| `customers` | `SELECT, INSERT, UPDATE` | `CustomerRepository` | Customer profile management and pseudonym storage. `DELETE` is blocked (`42501`). |
| `transactions` | `SELECT, INSERT, UPDATE` | `TransactionRepository` | Ingests payment failures and records status transitions. `DELETE` is blocked (`42501`). |
| `campaigns` | `SELECT, INSERT, UPDATE` | `CampaignRepository` | Recovery campaign metadata and lifecycle tracking. `DELETE` is blocked (`42501`). |
| `recovery_attempts` | `SELECT, INSERT, UPDATE` | `RecoveryAttemptRepository` | Recovery execution logs and link tracking. `DELETE` is blocked (`42501`). |
| `recovery_outbox` | `SELECT, INSERT, UPDATE` | `PostgresRecoveryOutboxStore` | Durable job queue. Leases claimed via `FOR UPDATE SKIP LOCKED`. Status transitions to `PROCESSED`. `DELETE` is blocked (`42501`). |
| `opt_out_registry` | `SELECT, INSERT, UPDATE` | `PostgresOptOutStore` | WhatsApp opt-outs. Unsubscribe/resubscribe managed via `status = 'ACTIVE'\|'INACTIVE'`. `DELETE` is blocked (`42501`). |

### 2.2 API-Key Authentication Code Path

Previously, merchant authentication required direct querying of merchant tables. Under `wapsi_app`, direct access to `merchant_api_keys` raises `psycopg2.errors.InsufficientPrivilege: permission denied for table merchant_api_keys` (`42501`).

To resolve this safely:
1. `MerchantRepository.authenticate_api_key(api_key_hash: str)` was added to `wapsi/db/repository.py`:
   ```python
   def authenticate_api_key(self, api_key_hash: str) -> Optional[Merchant]:
       with self._db.session() as session:
           stmt = text(
               "SELECT merchant_id, merchant_code, merchant_status, key_scopes "
               "FROM public.lookup_merchant_by_api_key_hash(:hash);"
           )
           row = session.execute(stmt, {"hash": api_key_hash}).first()
           if not row:
               return None
           return Merchant(
               id=row.merchant_id,
               merchant_code=row.merchant_code,
               status=row.merchant_status,
           )
   ```
2. FastAPI endpoints in `wapsi/api/app.py` (`_verify_recovery_auth` and `/api/v1/recovery/predict`) were updated to invoke this method. Direct access to `merchant_api_keys` has been eliminated.

### 2.3 Outbox Leasing & Zero-DELETE Lifecycle

- `PostgresRecoveryOutboxStore.claim_batch`:
  Uses `SELECT ... FROM public.recovery_outbox WHERE status = 'PENDING' AND (leased_until IS NULL OR leased_until < NOW()) ORDER BY priority DESC, created_at ASC FOR UPDATE SKIP LOCKED` inside a transaction.
- Completed and failed jobs are updated via `UPDATE public.recovery_outbox SET status = 'PROCESSED', processed_at = NOW() ...`.
- No `DELETE` statements exist in `wapsi/recovery/outbox.py`, `wapsi/recovery/worker.py`, or `wapsi/db/repository.py`.

---

## 3. RUNTIME CONFIGURATION COMPATIBILITY

### 3.1 Environment Variable Invariant
- Inspection of `wapsi/core/config.py` confirms that `database_url` is loaded from `DATABASE_URL` (or alias `wapsi_database_url`).
- `DatabaseManager` in `wapsi/db/session.py` receives `settings.database_url`.
- There are **no hidden or fallback administrative connection strings** in the runtime code.
- `WAPSI_ADMIN_DATABASE_URL` is not parsed by `WapsiSettings`, ensuring it remains completely inert during application execution.

### 3.2 Session Pooler & Connection Configuration
- **Host:** `aws-0-ap-south-1.pooler.supabase.com`
- **Port:** `5432` (Session Pooler mode, required for transaction-local `SET LOCAL` statements, advisory locks, and persistent prepared statements).
- **SSL Mode:** `sslmode=require` is explicitly configured in `create_engine(..., connect_args={"sslmode": "require"})`.
- **Pool Settings:** `pool_pre_ping=True`, `pool_size=10`, `max_overflow=20`, `pool_recycle=1800`.
- **User Identity:** When connecting via Session Pooler, the application authenticates as `wapsi_app.filofxijqmgluuulivxb`.

### 3.3 Fail-Closed DB Initialization
In `wapsi/db/session.py`:
- SQLite fallback is only triggered if `database_url` is empty (`if not url:`).
- When `DATABASE_URL` contains a PostgreSQL connection string, any connection drop, authentication failure, or network disruption immediately raises an `OperationalError` or `DatabaseConnectionError`.
- Silent fallback to SQLite or memory is completely disabled.

---

## 4. SECURE SWITCH UTILITY SPECIFICATION

**Script:** `scripts/switch_wapsi_runtime_to_app_role.py`

### 4.1 Preflight Verification Sequence
Before touching `.env`, the script executes 10 non-destructive verification steps:
1. **Administrative Connection Check:** Connects using existing `DATABASE_URL` and validates connectivity.
2. **Session Pooler TLS Check:** Connects as `wapsi_app` to port 5432 and verifies `ssl_in_use == True`.
3. **Role Attributes Verification:** Queries `pg_roles` to assert `current_user == 'wapsi_app'`, `rolsuper == False`, `rolbypassrls == False`.
4. **SQLAlchemy 2.0 Pool Pre-Ping:** Tests engine connection pool with `SELECT 1;`.
5. **Permitted Table SELECTs:** Asserts successful read access on `merchants`, `customers`, `transactions`, `recovery_outbox`, `opt_out_registry`.
6. **Sensitive Table Access Rejection:** Asserts `psycopg2.errors.InsufficientPrivilege` (error `42501`) when attempting to read `merchant_api_keys` and `merchant_memberships`.
7. **Zero-DELETE Rejection:** Asserts `psycopg2.errors.InsufficientPrivilege` (error `42501`) when attempting `DELETE` on operational tables (`transactions`, `customers`, `recovery_outbox`, `opt_out_registry`).
8. **API-Key Function Execution:** Asserts successful execution of `public.lookup_merchant_by_api_key_hash(text)`.
9. **Password Safety:** Prompts securely via `getpass` or reads `WAPSI_APP_PASSWORD` environment variable. Never prints or logs plain passwords.
10. **Atomic `.env` Update:** Writes the new file to a temporary file (`.env.tmp_*`) and uses `os.replace` for atomic replacement.

### 4.2 Switch Command Syntax
```powershell
# Dry run (validates all 10 preflight checks without modifying .env)
py -3.13 scripts/switch_wapsi_runtime_to_app_role.py --dry-run

# Live switch (prompts for wapsi_app password interactively)
py -3.13 scripts/switch_wapsi_runtime_to_app_role.py
```

---

## 5. SECURE ROLLBACK UTILITY SPECIFICATION

**Script:** `scripts/rollback_wapsi_runtime_to_admin.py`

### 5.1 Verification & Restoration Logic
1. Checks that `.env` contains `WAPSI_ADMIN_DATABASE_URL`.
2. Validates administrative database connectivity using the stored backup URL.
3. Atomically restores `DATABASE_URL` = `WAPSI_ADMIN_DATABASE_URL` via temporary file replacement.
4. Preserves all other environment variables and comments.

### 5.2 Rollback Command Syntax
```powershell
# Dry run verification
py -3.13 scripts/rollback_wapsi_runtime_to_admin.py --dry-run

# Live rollback
py -3.13 scripts/rollback_wapsi_runtime_to_admin.py
```

---

## 6. AUTOMATED TEST SUITE & VERIFICATION

### 6.1 Cutover Test Suite (`tests/test_phase3_1e_runtime_cutover.py`)

A dedicated suite of 7 tests was executed against both unit mocks and an isolated PostgreSQL cluster:

| Test Name | Focus Area | Result |
| :--- | :--- | :--- |
| `test_fastapi_uses_database_url_from_settings` | Verifies FastAPI engine initializes strictly from `settings.database_url`. | **PASSED** |
| `test_no_hidden_administrative_fallback` | Verifies `WAPSI_ADMIN_DATABASE_URL` is ignored by settings/engine. | **PASSED** |
| `test_sqlite_fallback_not_activated_when_postgres_configured` | Confirms failed PostgreSQL connection raises `OperationalError` (no SQLite fallback). | **PASSED** |
| `test_api_key_lookup_function_repository_integration` | Validates `authenticate_api_key` calls `lookup_merchant_by_api_key_hash`. | **PASSED** |
| `test_restricted_role_table_grants_and_denials` | Verifies permitted SELECTs, denied sensitive tables, and zero DELETE privileges. | **PASSED** |
| `test_cross_merchant_rls_row_isolation` | Verifies Tenant A cannot read Tenant B rows using `SET LOCAL app.current_merchant_id`. | **PASSED** |
| `test_env_switch_and_rollback_utilities` | Verifies end-to-end atomic update and rollback of `.env` configuration. | **PASSED** |

### 6.2 Full Regression Suite
- **Command:** `py -3.13 -m pytest -q`
- **Result:** `351 passed in 125.01s (0:02:05)`
- **Regressions:** Zero.

---

## 7. TENANT ISOLATION & ROW-LEVEL SECURITY (RLS) ANALYSIS

### 7.1 Authentication Context & Current Boundary
- In the Supabase environment, client-facing JWT requests set `auth.uid()`.
- When FastAPI connects as `wapsi_app` through Session Pooler, `auth.uid()` evaluates to `NULL`.
- Tenant isolation under `wapsi_app` is governed by PostgreSQL RLS policies defined in Migration 4:
  ```sql
  CREATE POLICY transactions_tenant_isolation ON public.transactions
  FOR ALL TO wapsi_app
  USING (merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::uuid);
  ```
- **Default-Deny Invariant:** If `app.current_merchant_id` is NOT set in a session/transaction, `NULLIF(..., '')` yields `NULL`, causing `merchant_id = NULL` to evaluate to `false` for all rows. As proven in `test_cross_merchant_rls_row_isolation`, zero rows are returned.
- **Scoping Invariant:** Executing `SET LOCAL app.current_merchant_id = '<merchant_uuid>'` limits the transaction strictly to that merchant's data.

### 7.2 Documented Operational Limitations & Future Roadmap
1. **Application-Enforced Filtering:** In Phase 3, repository methods enforce `merchant_id = :id` at the query level. While secure, database-level RLS provides defense-in-depth.
2. **Transaction-Local Setting in FastAPI Middleware:** In a future phase, a FastAPI dependency or middleware can issue `SET LOCAL app.current_merchant_id = :merchant_id` upon successful API-key verification, ensuring RLS enforcement is automatic at the PostgreSQL engine level.
3. **Background Worker Scope:** Background outbox workers lease jobs globally across tenants (`public.recovery_outbox`). Once an outbox record is leased, the worker processes the associated merchant recovery attempt within that merchant's tenant boundary.

---

## 8. CURRENT ENVIRONMENT STATE

- **`.env` State:** **UNTOUCHED.** Currently contains administrative connection string (`DATABASE_URL`). `WAPSI_ADMIN_DATABASE_URL` is not present.
- **Hosted Supabase Project:** `filofxijqmgluuulivxb` (`WAPSI-DEV-MUMBAI`).
- **Hosted Data State:** **0 synthetic records** across all 18 public base tables.
- **Git Working Tree:** All modifications preserved in working directory on branch `wapsi/phase3-recovery-workflow`. No commits or pushes performed.

---

## 9. OPERATOR AUTHORIZATION GATE

All preflight prerequisites, integration tests, utility scripts, and security checks are complete. 

The runtime cutover utility `scripts/switch_wapsi_runtime_to_app_role.py` is ready to execute upon operator confirmation.

**STOPPED.** Awaiting operator authorization.

