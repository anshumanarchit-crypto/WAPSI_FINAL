# WAPSI — PHASE 3.1B: ZERO-DELETE OPT-OUT HARDENING REPORT

**Project Target:** WAPSI — WhatsApp Autonomous Payment Recovery System  
**Supabase Project:** `WAPSI-DEV-MUMBAI`  
**Project Reference:** `filofxijqmgluuulivxb`  
**Hosting Region:** `ap-south-1` (Mumbai, India)  
**Database Engine:** PostgreSQL 17.11 (Hosted Supabase) / PostgreSQL 17.9 (Isolated Local Verification Cluster)  
**Backend Workspace:** `C:\Users\arpit\Desktop\Razorpay\Razorpay`  
**Active Branch:** `wapsi/phase3-recovery-workflow`  
**Verification Date:** November 1, 2026  
**Status:** **ZERO-DELETE HARDENING VERIFIED — READY FOR HUMAN APPROVAL (ZERO REMOTE DDL EXECUTED)**  

---

## 1. Executive Summary

Phase 3.1B eliminates the unrestricted `DELETE` privilege on `public.opt_out_registry` and implements a compliant, persistent, auditable opt-out lifecycle using status-based deactivation (`is_active = FALSE`, `revoked_at` timestamp).

This change establishes the database security invariant: **`wapsi_app` has ZERO DELETE privileges across the entire database.**

All 325 regression, integration, and zero-delete unit tests passed cleanly. Checksums between `docs/migrations/` and `supabase/migrations/` match bit-for-bit. The Supabase CLI verified linked migration status and executed a non-destructive dry-run proposing only Migrations 4 and 5. Zero DDL was executed on hosted Supabase, and all 15 public schema tables remain at **0 synthetic rows**.

---

## 2. Exact Files Modified & Created

| File Path | Action | Description |
| :--- | :---: | :--- |
| `supabase/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql` | Modified | Added `is_active` and `revoked_at` to `opt_out_registry`, added partial index `idx_opt_out_active`, replaced `GRANT ... DELETE` with `GRANT SELECT, INSERT, UPDATE`. |
| `docs/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql` | Modified | Exact bit-for-bit duplicate of the staged Migration 5. |
| `wapsi/db/models.py` | Modified | Added `is_active: Mapped[bool]` and `revoked_at: Mapped[Optional[datetime]]` to `OptOutRegistryModel`. |
| `wapsi/db/repository.py` | Modified | Updated `OptOutRepository.is_opted_out` (filters on `is_active is True`), `record_opt_out` (handles reactivation & duplicates), and `revoke_opt_out` (updates `is_active = False` without physical DELETE). |
| `wapsi/recovery/opt_out_store.py` | Modified | Updated SQLite schema evolution, `is_opted_out` query, `record_opt_out` reactivation, and `revoke_opt_out` soft deactivation. |
| `tests/test_phase3_1_postgres_workflow.py` | Modified | Added zero-delete lifecycle verification to test 6 and added `test_postgres_wapsi_app_has_no_delete_privilege_on_opt_out_registry` (9 tests total). |
| `tests/test_phase1b5_mumbai_readiness.py` | Modified | Updated `test_migration_seed_separation` assertion to recognize staged migrations 4 and 5. |
| `tests/test_phase3_1b_zero_delete_opt_out.py` | Created | Comprehensive unit test suite covering full SQLite zero-delete lifecycle, process restarts, and eligibility suppression logic. |
| `docs/PHASE_3_1B_ZERO_DELETE_HARDENING_REPORT.md` | Created | Comprehensive engineering and audit report. |

---

## 3. Final Opt-Out Lifecycle Architecture

### 3.1 Lifecycle State Transitions

```
                    ┌────────────────────────┐
                    │   Customer Inbound     │
                    │   (Initial State)      │
                    └───────────┬────────────┘
                                │ STOP / UNSUBSCRIBE
                                ▼
                    ┌────────────────────────┐
   ┌───────────────►│  is_active = TRUE      │◄──────────────┐
   │                │  revoked_at = NULL     │               │
   │                │  (Suppresses Outbox)   │               │
   │                └───────────┬────────────┘               │
   │                            │                            │
   │ Duplicate STOP             │ Re-consent with            │ Subsequent STOP
   │ (Logs DUPLICATE_OPT_OUT)   │ Verified Proof             │ (Reactivates Row;
   │                            ▼                            │  Logs OPT_OUT)
   │                ┌────────────────────────┐               │
   └────────────────┤  is_active = FALSE     ├───────────────┘
                    │  revoked_at = UTC Now  │
                    │  (Eligible for Recovery│
                    │   ZERO PHYSICAL DELETE)│
                    └────────────────────────┘
```

1. **STOP / UNSUBSCRIBE Keyword Received:**
   - **New Customer:** Inserts row into `opt_out_registry` with `is_active = TRUE`, `opted_out_at = now()`, `revoked_at = NULL`. Appends `OPT_OUT` event to `opt_out_audit_trail`.
   - **Already Opted-Out Customer:** Idempotent no-op on registry row. Appends `DUPLICATE_OPT_OUT` event to `opt_out_audit_trail`.
   - **Previously Revoked Customer:** Reactivates existing row: sets `is_active = TRUE`, updates `opted_out_at = now()`, clears `revoked_at = NULL`. Appends `OPT_OUT` event to `opt_out_audit_trail`.
2. **Re-Consent / Revocation:**
   - Requires explicit, verified consent proof (min length 5 chars; raises `ValueError` if missing or whitespace).
   - If active record exists: sets `is_active = FALSE`, sets `revoked_at = now()`.
   - **Zero Physical Delete:** The row is never deleted from `opt_out_registry`.
   - Appends `REVOCATION` event to `opt_out_audit_trail` with `action="REVOCATION"`, `reason="EXPLICIT_RE_CONSENT"`, `source="reopt_in_flow"`, and `consent_proof`.
3. **Outbox Eligibility Evaluation:**
   - Evaluates `is_opted_out(phone)`:
     - PostgreSQL: `WHERE phone = :p AND is_active = TRUE`
     - SQLite: `WHERE phone = ? AND is_active = 1`
   - Only active opt-outs suppress recovery nudges. Inactive (revoked) opt-outs do not suppress eligible customers.

---

## 4. Migration 5 Grant & Schema Amendments

### 4.1 Schema DDL (`opt_out_registry`)
```sql
CREATE TABLE IF NOT EXISTS public.opt_out_registry (
    phone VARCHAR(32) PRIMARY KEY,
    reason VARCHAR(128) NOT NULL DEFAULT 'STOP_KEYWORD',
    source VARCHAR(64) NOT NULL DEFAULT 'inbound_whatsapp',
    opted_out_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor VARCHAR(128),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_opt_out_phone ON public.opt_out_registry (phone);
CREATE INDEX IF NOT EXISTS idx_opt_out_active ON public.opt_out_registry (phone) WHERE is_active = TRUE;
```

### 4.2 Least-Privilege Grant Update
```sql
-- BEFORE:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON public.opt_out_registry TO wapsi_app;

-- AFTER (Zero DELETE):
GRANT SELECT, INSERT, UPDATE ON public.opt_out_registry TO wapsi_app;
GRANT SELECT, INSERT, UPDATE ON public.customer_interactions TO wapsi_app;
GRANT SELECT, INSERT ON public.opt_out_audit_trail TO wapsi_app;
```

### 4.3 Database Security Invariant Enforced
- `wapsi_app` has **NO DELETE privilege** on `public.opt_out_registry`.
- Any attempt by `wapsi_app` to execute `DELETE FROM public.opt_out_registry WHERE ...` is rejected at the PostgreSQL catalog permission level with error code `42501 (insufficient_privilege)`.
- Verified in live PostgreSQL integration test: `test_postgres_wapsi_app_has_no_delete_privilege_on_opt_out_registry`.

---

## 5. PostgreSQL and SQLite Consistency Verification

The zero-delete lifecycle was tested for parity across both persistence engines:

| Feature / Behavior | PostgreSQL Engine | SQLite Engine | Parity Status |
| :--- | :--- | :--- | :---: |
| **Active Flag** | `is_active BOOLEAN NOT NULL DEFAULT TRUE` | `is_active INTEGER NOT NULL DEFAULT 1` | **MATCH** |
| **Revocation Timestamp** | `revoked_at TIMESTAMPTZ` | `revoked_at REAL` | **MATCH** |
| **Fast Lookup Filter** | `WHERE phone = :p AND is_active = TRUE` | `WHERE phone = ? AND is_active = 1` | **MATCH** |
| **Duplicate STOP** | Logs `DUPLICATE_OPT_OUT` audit row | Logs `DUPLICATE_OPT_OUT` audit row | **MATCH** |
| **Re-Consent Deactivation** | `UPDATE ... SET is_active = False, revoked_at = now()` | `UPDATE ... SET is_active = 0, revoked_at = ?` | **MATCH** |
| **Physical Row Deletion** | **ZERO DELETE** (`session.delete` removed) | **ZERO DELETE** (`DELETE FROM` removed) | **MATCH** |
| **Re-Opt-Out Reactivation** | `UPDATE ... SET is_active = True, revoked_at = None` | `UPDATE ... SET is_active = 1, revoked_at = NULL` | **MATCH** |
| **Audit Trail Ordering** | `OPT_OUT` $\rightarrow$ `DUPLICATE` $\rightarrow$ `REVOCATION` $\rightarrow$ `OPT_OUT` | Identical chronological sequence | **MATCH** |

---

## 6. Test Suite Execution & Verification Results

### 6.1 Test Summary Table

| Test Suite File | Tests | Passed | Execution Time | Scope / Target |
| :--- | :---: | :---: | :---: | :--- |
| `tests/test_phase3_1b_zero_delete_opt_out.py` | 3 | 3 | 0.70s | Zero-delete lifecycle, process restart survival, eligibility check |
| `tests/test_phase3_1_postgres_workflow.py` | 9 | 9 | 13.59s | Isolated PostgreSQL 17 cluster: concurrent claims, zero-delete lifecycle, `wapsi_app` no-DELETE grant enforcement |
| `tests/test_phase3_recovery_workflow.py` | 22 | 22 | 11.24s | Recovery workflow engine, webhook processing, timeline events, outbox cancellation |
| `tests/test_phase2_1_hardening.py` | 15 | 15 | 2.14s | Monetary precision, raw body HMAC verification |
| `tests/test_phase2_integrations.py` | 22 | 22 | 3.42s | Razorpay & WhatsApp Cloud API sandboxes |
| `tests/test_phase1b5_mumbai_readiness.py` | 5 | 5 | 0.62s | Mumbai configuration, staged migration validation |
| `tests/test_phase1c_postgres_config.py` | 6 | 6 | 0.53s | Live PostgreSQL connection settings (read-only) |
| **All Other Causal / Explainer Suites** | 243 | 243 | ~185s | Pretrained production causal AI & bandit models |
| **TOTAL TEST SUITE** | **325** | **325** | **217.43s** | **100% PASSING (Zero Failures)** |

---

## 7. Migration Checksums & Integrity

Exact SHA-256 hash calculation confirms both copies are identical:

| Migration File | Directory | SHA-256 Checksum | Parity |
| :--- | :--- | :--- | :---: |
| `20261101000004_phase1d_restricted_app_role.sql` | `docs/migrations/` | `BB40519D9AC1A125D028BE5BE08B9639D158D06EF497A8CFF850C6411C579FA0` | Baseline |
| `20261101000004_phase1d_restricted_app_role.sql` | `supabase/migrations/` | `BB40519D9AC1A125D028BE5BE08B9639D158D06EF497A8CFF850C6411C579FA0` | **IDENTICAL** |
| `20261101000005_phase3_outbox_leases_and_opt_outs.sql` | `docs/migrations/` | `1F942A88F87212F461531057F082D22125A149AE2BA0D9D7536764C182FF6A92` | Updated |
| `20261101000005_phase3_outbox_leases_and_opt_outs.sql` | `supabase/migrations/` | `1F942A88F87212F461531057F082D22125A149AE2BA0D9D7536764C182FF6A92` | **IDENTICAL** |

- Migration 4: Unmodified.
- Migration 5: Updated in place in both locations; identical checksums.

---

## 8. Supabase CLI Remote Verification

### 8.1 Remote Migration List (`npx supabase@latest migration list --linked`)
```json
{
  "migrations": [
    {"local": "20261031000001", "remote": "20261031000001", "time": "2026-10-31 00:00:01"},
    {"local": "20261031000002", "remote": "20261031000002", "time": "2026-10-31 00:00:02"},
    {"local": "20261031000003", "remote": "20261031000003", "time": "2026-10-31 00:00:03"},
    {"local": "20261101000004", "remote": "", "time": "2026-11-01 00:00:04"},
    {"local": "20261101000005", "remote": "", "time": "2026-11-01 00:00:05"}
  ],
  "message": "Migrations listed"
}
```
*Confirmed:* Remote database has migrations 1–3 applied; migrations 4 and 5 remain pending.

### 8.2 Dry-Run Verification (`npx supabase@latest db push --dry-run --linked`)
```text
Initialising login role...
DRY RUN: migrations will *not* be pushed to the database.
Connecting to remote database...
Would push these migrations:
 • 20261101000004_phase1d_restricted_app_role.sql
 • 20261101000005_phase3_outbox_leases_and_opt_outs.sql
{"upToDate":false,"dryRun":true,"migrations":["20261101000004_phase1d_restricted_app_role.sql","20261101000005_phase3_outbox_leases_and_opt_outs.sql"],"seeds":[],"roles":[],"message":"Finished supabase db push."}
```
*Confirmed:* Exactly the two reviewed migrations are scheduled for push. Zero remote DDL was executed.

### 8.3 Hosted Supabase Integrity Check (`scripts/verify_postgres_connection.py`)
```text
[PASS] Connection established in 930.42 ms
       - Server: PostgreSQL 17.11
       - Connected User: postgres
       - Public tables found: 15/15
       - Recorded migrations: ['20261031000001', '20261031000002', '20261031000003']
       - Row counts across all 15 public tables: 0 rows
```
*Confirmed:* The hosted Supabase cluster remains completely untouched and unpolluted.

---

## 9. Rollback Guidance (Forward-Fix Policy)

> [!CAUTION] Production Policy: No Destructive Rollbacks
> As documented in Task 5 of Phase 3.1A, destructive rollback (`DROP TABLE ... CASCADE` or `ALTER TABLE ... DROP COLUMN`) permanently destroys customer consent records and correlation keys.
> 
> - **Pre-deployment / Zero-data:** Rollback script from Preflight Report may be used if deployment aborts before completion.
> - **Post-deployment / Live traffic:** Destructive rollback is **strictly prohibited**. Any post-deployment defect or adjustment must be deployed via forward-fix migration `20261101000006_...`.

---

## 10. Strict Preflight Checklist & Approval Status

- [x] Unrestricted `DELETE` grant on `public.opt_out_registry` completely removed.
- [x] Zero-DELETE privilege invariant verified for `wapsi_app`.
- [x] Status-based deactivation (`is_active = FALSE`, `revoked_at`) implemented and verified.
- [x] Both SQLite and PostgreSQL implementations tested and 100% consistent.
- [x] Full regression suite passing: **325/325 tests passed**.
- [x] Migration 4 untouched; Migration 5 checksums verified identical.
- [x] Remote dry-run verified proposing only migrations 4 and 5.
- [x] Zero remote DDL or data written to hosted Supabase.
- [x] Zero Git commits or pushes executed.

---

> [!IMPORTANT] Awaiting Human Authorization
> Phase 3.1B Zero-DELETE hardening is fully implemented, verified, and dry-run tested.
> 
> The database migrations are ready for deployment via:
> ```powershell
> npx supabase@latest db push --linked
> ```
> 
> **No live deployment has been executed.** Please provide your authorization to proceed with deployment.

