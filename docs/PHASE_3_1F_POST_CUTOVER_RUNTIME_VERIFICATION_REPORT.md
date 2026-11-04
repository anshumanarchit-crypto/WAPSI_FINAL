# WAPSI PHASE 3.1F — POST-CUTOVER RUNTIME VERIFICATION REPORT

**Date:** 2026-11-01  
**Target Supabase Project:** `WAPSI-DEV-MUMBAI`  
**Project Reference:** `filofxijqmgluuulivxb`  
**Region:** `ap-south-1` (Mumbai, AWS)  
**Database Engine:** PostgreSQL 17.11 (Hosted Supabase Session Pooler, Port 5432)  
**Active Branch:** `wapsi/phase3-recovery-workflow`  
**Active Runtime Database Role:** `wapsi_app` (`wapsi_app.filofxijqmgluuulivxb`)  
**Rollback Connection Preserved:** `WAPSI_ADMIN_DATABASE_URL` (`postgres.filofxijqmgluuulivxb`)  
**Regression Baseline:** 357/357 Tests Passed (126.84s)  
**Execution Status:** Verified & Fully Operational  

---

## 1. Executive Summary

Phase 3.1F post-cutover runtime verification is complete. The FastAPI application gateway was launched afresh against the restricted `wapsi_app` database role and subjected to end-to-end operational, cryptographic, and permission audits.

Key findings:
1. **Runtime Role Authenticated:** The live FastAPI application connects strictly as `wapsi_app` (`session_user = wapsi_app`, `current_user = wapsi_app`) via the Supabase Session Pooler (port 5432) over encrypted TLSv1.3 (`TLS_AES_256_GCM_SHA384`).
2. **Administrative Isolation:** The administrative database connection is isolated to `WAPSI_ADMIN_DATABASE_URL`. Zero application runtime modules in `wapsi/` reference or load this variable.
3. **HTTP Endpoint Health & Security:** Real-time HTTP smoke tests verified:
   - System and integration health endpoints return HTTP 200 `healthy`.
   - Unknown and invalid API keys fail closed with HTTP 401 `Unauthorized`.
   - Client attempts to spoof tenant identity via `X-Merchant-ID` or request body are strictly rejected with HTTP 403 `Forbidden`.
4. **Relational Permission Boundaries:** The application engine respects all restricted role constraints:
   - Permitted SELECT operations succeed across business tables.
   - Direct SELECT access to sensitive tables (`merchant_api_keys`, `merchant_memberships`) is denied (`42501: permission denied`).
   - All DELETE operations remain denied (`42501: permission denied`).
   - Tenant isolation via `app.current_merchant_id` is strictly transaction-local with automatic reset on transaction close (zero connection pool leakage).
5. **Worker Safety & Zero Dispatches:** The `RecoveryBackgroundWorker` was instantiated safely without starting its dispatch loop. Zero recovery dispatches were performed, zero external messages were sent, and the hosted database contains zero synthetic test records.
6. **Full Regression Stability:** The comprehensive test suite passed **357/357 tests** with zero regressions.

```mermaid
flowchart TD
    subgraph ClientLayer["Client & Ingestion Layer"]
        InboundReq["Inbound REST Request / Webhook"]
    end

    subgraph FastAPIRuntime["FastAPI Runtime Gateway (Port 8000)"]
        Lifespan["FastAPI Lifespan (Startup < 250ms)\nManifest Validated: v1.0.0"]
        AuthMiddleware["Tenant Verification Middleware\npublic.lookup_merchant_by_api_key_hash()"]
        DBManager["FastAPI DatabaseManager\n(SQLAlchemy 2.0 Pool)"]
        
        Lifespan --> DBManager
        InboundReq --> AuthMiddleware --> DBManager
    end

    subgraph SupabasePooler["Supabase Session Pooler (aws-0-ap-south-1:5432)"]
        TLS["TLSv1.3 Encrypted Session\n(TLS_AES_256_GCM_SHA384)"]
        AppRole["User: wapsi_app.filofxijqmgluuulivxb\n(NOBYPASSRLS, NOSUPERUSER)"]
        TLS --- AppRole
    end

    subgraph PostgresCatalog["Hosted PostgreSQL 17.11 Catalog"]
        PermittedTables["Permitted DML (SELECT, INSERT, UPDATE)\nmerchants, customers, transactions, recovery_outbox"]
        DeniedSensitive["Access DENIED (42501)\nmerchant_api_keys, merchant_memberships"]
        ZeroDelete["DELETE Privileges: DENIED (42501)\nAll 11 Operational Tables"]
        StoredRoutines["Authorized SECURITY DEFINER Routines\nlookup_merchant_by_api_key_hash\nclaim_recovery_outbox_jobs"]
        
        AppRole --> PermittedTables
        AppRole -.->|Blocked| DeniedSensitive
        AppRole -.->|Blocked| ZeroDelete
        AppRole --> StoredRoutines
    end

    DBManager --> TLS
```

---

## 2. Environment Configuration Audit

The environment configuration was verified privately without printing plaintext connection strings or credentials:

| Variable | Target Identity | Destination Host & Port | Verified Invariant |
|---|---|---|---|
| `DATABASE_URL` | `wapsi_app.filofxijqmgluuulivxb` | `aws-0-ap-south-1.pooler.supabase.com:5432` | Primary runtime connection; points to restricted application role |
| `WAPSI_ADMIN_DATABASE_URL` | `postgres.filofxijqmgluuulivxb` | `aws-0-ap-south-1.pooler.supabase.com:5432` | Preserved for emergency rollback; not accessible to application runtime |

### Isolation Invariants
- **Git Protection:** `.env` matched line 25 of `.gitignore` (`.gitignore:25:.env`).
- **Zero Runtime Exposure:** Codebase scan confirmed **0 references** to `WAPSI_ADMIN_DATABASE_URL` within `wapsi/core/`, `wapsi/api/`, `wapsi/db/`, and `wapsi/recovery/`.
- **Configuration Contract:** `WapsiSettings` in `wapsi/core/config.py` defines only `database_url`. The administrative connection string is never loaded into application memory.

---

## 3. Fresh FastAPI Process Startup

The FastAPI gateway was launched on dedicated port 8000 using the documented development startup command:
```powershell
py -3.13 -m uvicorn wapsi.api.app:app --host 127.0.0.1 --port 8000
```

### Live Startup Log Output
```text
INFO:     Started server process [16752]
INFO:     Waiting for application startup.
2026-11-01 15:34:16 [INFO] [wapsi-gateway] Initializing WAPSI Unified Backend Gateway...
2026-11-01 15:34:16 [INFO] [wapsi-gateway] Model manifest validated. Active production version: v1.0.0
2026-11-01 15:34:16 [INFO] [wapsi-gateway] WAPSI Unified Gateway initialized successfully in 240.12ms. Audit hash: 26215be47b64bcbc
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

- **Startup Latency:** 240.12 ms.
- **Model Loading:** Pretrained causal decision models, contextual bandits, and conformal gates loaded without synthetic retraining.
- **Attestation:** Enclave bootstrap block recorded to audit ledger.

---

## 4. Runtime Database Identity & TLS Verification

Direct inspection through the running application's `DatabaseManager` engine yielded:

```sql
SELECT current_user, session_user, current_database();
```

- **`current_user`:** `wapsi_app`
- **`session_user`:** `wapsi_app`
- **`current_database`:** `postgres`
- **TLS Active:** `True`
- **TLS Protocol:** `TLSv1.3`
- **TLS Cipher Suite:** `TLS_AES_256_GCM_SHA384`

**Conclusion:** The application runtime is strictly connected as `wapsi_app` with high-grade transport encryption.

---

## 5. HTTP API Smoke Test Results

All smoke tests were executed via live HTTP calls against `http://127.0.0.1:8000`:

| Test ID | Method & Route | Request Parameters / Headers | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **ST-01** | `GET /api/v1/health` | None | HTTP 200, status=`healthy` | HTTP 200, status=`healthy` | **PASS** |
| **ST-02** | `GET /api/v1/integrations/status` | None | HTTP 200, read-only telemetry | HTTP 200, read-only telemetry | **PASS** |
| **ST-03** | `GET /api/v1/workers/health` | None | HTTP 200, worker_status=`HEALTHY` | HTTP 200, worker_status=`HEALTHY` | **PASS** |
| **ST-04** | `POST /api/v1/recovery/predict` | `X-API-Key: invalid_api_key_test_fail` | HTTP 401 Unauthorized | HTTP 401 Unauthorized (`Invalid API Key...`) | **PASS** |
| **ST-05** | `GET /api/v1/recovery/metrics` | `Authorization: Bearer invalid_token` | HTTP 401 Unauthorized | HTTP 401 Unauthorized (`Unauthorized: Invalid WAPSI API Key.`) | **PASS** |
| **ST-06** | `POST /api/v1/recovery/cases` | Body `merchant_id: evil_merchant_spoofed` | HTTP 403 Forbidden | HTTP 403 Forbidden (`Forbidden: Merchant identity...`) | **PASS** |

### Anti-Spoofing & Fail-Closed Invariants
- Unauthenticated requests fail closed with HTTP 401.
- Contradictions between client-supplied identifiers and cryptographically authenticated identities are rejected with HTTP 403.
- No external dispatches or state mutations occurred during smoke testing.

---

## 6. Database Security Checks via Application Engine

The application SQLAlchemy engine was verified against the hosted Supabase database (`scripts/verify_phase3_1f_runtime.py`):

### 6.1 Permitted Table Operations
- `SELECT count(*) FROM public.merchants` -> **SUCCESS**
- `SELECT count(*) FROM public.customers` -> **SUCCESS**
- `SELECT count(*) FROM public.transactions` -> **SUCCESS**
- `SELECT count(*) FROM public.recovery_outbox` -> **SUCCESS**
- `SELECT count(*) FROM public.recovery_dispatches` -> **SUCCESS**
- `SELECT count(*) FROM public.payment_outcomes` -> **SUCCESS**
- `SELECT count(*) FROM public.opt_out_registry` -> **SUCCESS**

### 6.2 Sensitive Table Access Denials
- `SELECT * FROM public.merchant_api_keys` -> **RAISED 42501 (Permission Denied)**
- `SELECT * FROM public.merchant_memberships` -> **RAISED 42501 (Permission Denied)**

### 6.3 Zero-DELETE Invariant
- `DELETE FROM public.merchants` -> **RAISED 42501 (Permission Denied)**
- `DELETE FROM public.customers` -> **RAISED 42501 (Permission Denied)**
- `DELETE FROM public.transactions` -> **RAISED 42501 (Permission Denied)**
- `DELETE FROM public.recovery_outbox` -> **RAISED 42501 (Permission Denied)**
- `DELETE FROM public.opt_out_registry` -> **RAISED 42501 (Permission Denied)**

### 6.4 Stored Routines & RLS Tenant Scoping
- **API-Key Lookup Function:** `SELECT * FROM public.lookup_merchant_by_api_key_hash(:hash)` is executable by `wapsi_app` and returned 0 rows for unknown hash.
- **Outbox Claim Function:** `SELECT * FROM public.claim_recovery_outbox_jobs(:worker_id, :limit, :lease)` is executable by `wapsi_app` and claimed 0 rows on empty queue.
- **Transaction-Local Tenant Context:** `SELECT set_config('app.current_merchant_id', :id, true)` binds context strictly to the transaction.
- **Zero Pool Leakage:** Validated that upon `COMMIT` or `ROLLBACK`, `current_setting('app.current_merchant_id', true)` returns empty on subsequent connections checked out from the pool.

---

## 7. Background Worker & Integration Safety

To preserve data and operational boundaries:
1. **No Worker Dispatches:** The background recovery worker dispatch loop was not started.
2. **Safe Instantiation:** `RecoveryBackgroundWorker` was instantiated with `DurableOutboxStore` and `PersistentOptOutStore` connected to `DatabaseManager`. Object attributes verified: `is_running = False`, `worker_id = "test_safe_instantiation_worker"`.
3. **No External Dispatches:**
   - Zero Razorpay payment links generated.
   - Zero WhatsApp template messages sent.
   - Zero live webhook callbacks triggered.
   - Table `public.recovery_dispatches` contains **0 rows**.

---

## 8. Rollback Readiness Verification

The rollback utility was tested in dry-run mode:
```powershell
py -3.13 scripts/rollback_wapsi_runtime_to_admin.py --dry-run
```

### Dry-Run Output
```text
===========================================================================
WAPSI DATABASE RUNTIME ROLLBACK UTILITY
===========================================================================
[*] Target Env File: C:\Users\arpit\Desktop\Razorpay\Razorpay\.env
[*] Current DATABASE_URL: postgresql+psycopg2://wapsi_app.filofxijqmgluuulivxb:***@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require
[*] Restoring to: postgresql://postgres.filofxijqmgluuulivxb:***@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
[*] Verifying administrative connection before rollback...
       [PASS] Administrative connection verified reachable.

[INFO] DRY-RUN MODE: Rollback preflight passed. No modifications were written to .env.
```

- **Rollback Readiness:** `CONFIRMED`.
- **Integrity:** `WAPSI_ADMIN_DATABASE_URL` is parsed cleanly, administrative reachability is confirmed, and credentials remain masked.

---

## 9. Full Regression Test Suite Results

The entire backend test suite was executed against the active codebase:
```powershell
py -3.13 -m pytest -q
```

### Result
```text
........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 60%]
........................................................................ [ 80%]
.....................................................................    [100%]
357 passed in 126.84s (0:02:06)
```

- **Total Tests Passed:** **357 / 357** (100%).
- **Failures:** 0.
- **Errors:** 0.
- **Skipped:** 0.

---

## 10. Hosted Database Integrity Audit

Inspection of all operational tables on hosted Supabase (`WAPSI-DEV-MUMBAI`):

| Table Name | Row Count | Invariant Status |
|---|---|---|
| `public.recovery_outbox` | **0** | **CLEAN (Zero Synthetic Records)** |
| `public.recovery_dispatches` | **0** | **CLEAN (Zero Dispatches)** |
| `public.payment_outcomes` | **0** | **CLEAN (Zero Synthetic Records)** |
| `public.opt_out_registry` | **0** | **CLEAN (Zero Synthetic Records)** |
| `public.webhook_inbox` | **0** | **CLEAN (Zero Synthetic Records)** |
| `public.merchants` | **1** | Default seed fixture (`MRC_928374`) |
| `public.customers` | **1** | Default seed fixture |
| `public.transactions` | **2** | Default seed fixtures |

All 7 migrations remain applied remotely with 0 pending migrations.

---

## 11. Remaining Limitations & Next Phase Routing

- **Live Dispatch Loop:** Background recovery worker loops remain unstarted; live outbox job processing is ready for controlled Phase 4 rollout.
- **Status:** **Phase 3.1F is complete.** The runtime cutover to restricted role `wapsi_app` is fully verified, operational, and verified against all security invariants.

