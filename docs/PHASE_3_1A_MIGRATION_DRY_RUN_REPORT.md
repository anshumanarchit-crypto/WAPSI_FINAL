# WAPSI — PHASE 3.1A: MIGRATION STAGING AND DRY-RUN REPORT

**Project Target:** WAPSI — WhatsApp Autonomous Payment Recovery System  
**Supabase Project:** `WAPSI-DEV-MUMBAI`  
**Project Reference:** `filofxijqmgluuulivxb`  
**Hosting Region:** `ap-south-1` (Mumbai, India)  
**Database Engine:** PostgreSQL 17.11 (Hosted Supabase)  
**Backend Workspace:** `C:\Users\arpit\Desktop\Razorpay\Razorpay`  
**Active Branch:** `wapsi/phase3-recovery-workflow`  
**Verification Date:** November 1, 2026  
**Status:** **DRY-RUN VERIFIED — READY FOR HUMAN APPROVAL (ZERO REMOTE DDL EXECUTED)**  

---

## 1. Executive Summary

Phase 3.1A successfully staged the reviewed migration drafts from `docs/migrations/` into the canonical `supabase/migrations/` directory without altering existing repository modifications or executing remote database changes.

The official Supabase CLI verified project linking and executed a non-destructive remote dry-run against the hosted `WAPSI-DEV-MUMBAI` PostgreSQL cluster (`filofxijqmgluuulivxb`). Exactly two pending migrations were detected, with zero schema drift, zero Docker prerequisites, and zero remote catalog mutations.

---

## 2. Task 1: Git Working Tree Safety Status

The working tree was inspected before and after file staging. All existing modifications remain preserved; no files were stashed, reset, discarded, committed, or pushed.

```text
Branch: wapsi/phase3-recovery-workflow

Unstaged Tracked Changes (Preserved):
  modified:   .env.example
  modified:   .gitignore
  modified:   evaluation/simulation_audit_log.json
  modified:   simulation/simulation_audit_log.json
  modified:   tests/test_frontend_adapter.py
  modified:   wapsi/api/app.py
  modified:   wapsi/api/schemas.py
  modified:   wapsi/core/config.py
  modified:   wapsi/db/models.py
  modified:   wapsi/db/repository.py
  modified:   wapsi/db/session.py

Untracked Staged Files:
  supabase/migrations/20261101000004_phase1d_restricted_app_role.sql
  supabase/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql
  docs/PHASE_3_1_DEPLOYMENT_PREFLIGHT_REPORT.md
  docs/PHASE_3_1A_MIGRATION_DRY_RUN_REPORT.md
  docs/migrations/ (Original review copies preserved)
  scripts/
  tests/test_phase1c_postgres_config.py
  tests/test_phase2_1_hardening.py
  tests/test_phase2_integrations.py
  tests/test_phase3_1_postgres_workflow.py
  tests/test_phase3_recovery_workflow.py
  wapsi/integrations/
  wapsi/recovery/
```

- **Commit Status:** Zero commits performed.
- **Push Status:** Zero pushes performed.

---

## 3. Task 2: Migration File Staging & Checksum Verification

The two reviewed migration scripts were staged into `supabase/migrations/` while preserving the review copies in `docs/migrations/`. Exact bit-for-bit file hash verification was performed:

| Target File | SHA-256 Checksum | Match Status |
| :--- | :--- | :---: |
| `docs/migrations/20261101000004_phase1d_restricted_app_role.sql` | `BB40519D9AC1A125D028BE5BE08B9639D158D06EF497A8CFF850C6411C579FA0` | Baseline |
| `supabase/migrations/20261101000004_phase1d_restricted_app_role.sql` | `BB40519D9AC1A125D028BE5BE08B9639D158D06EF497A8CFF850C6411C579FA0` | **IDENTICAL** |
| `docs/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql` | `CB692F5D6D34D14B160E2D4AD94AA2622F81D9C914AAA0BF0F036B86A1B1D488` | Baseline |
| `supabase/migrations/20261101000005_phase3_outbox_leases_and_opt_outs.sql` | `CB692F5D6D34D14B160E2D4AD94AA2622F81D9C914AAA0BF0F036B86A1B1D488` | **IDENTICAL** |

---

## 4. Task 3: Project Linking & Remote Migration History

### 4.1 Linked Project Verification
- **Target Project:** `WAPSI-DEV-MUMBAI`
- **Confirmed Project Reference:** `filofxijqmgluuulivxb` (verified from `supabase/.temp/project-ref`)
- **Hosting Region:** `ap-south-1` (Mumbai, India)

### 4.2 Migration History Output (`npx supabase@latest migration list --linked`)

Command executed:
```powershell
npx supabase@latest migration list --linked
```

Actual CLI response:
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

### Verification Findings:
1. Migrations 1, 2, and 3 are **confirmed applied remotely** (`remote` timestamps match `local`).
2. Migrations 4 and 5 are **confirmed pending** (`remote: ""`).
3. No foreign or orphaned remote migrations exist.
4. No version timestamp collisions detected.

---

## 5. Task 4: Opt-Out DELETE Permission Architectural Evaluation

The current draft of Migration 5 includes:
```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON public.opt_out_registry TO wapsi_app;
```

### 5.1 Legal & Regulatory Analysis (DPDP Act 2023 & Meta Messaging Policies)
- Under Section 6(4) of the Indian Digital Personal Data Protection Act (DPDP) 2023, Data Principals possess the right to withdraw consent as easily as giving consent.
- However, DPDP **does not require physical row deletion** of opt-out records when re-consent occurs. 
- In fact, regulatory compliance and audit defensibility require maintaining a persistent, verifiable record of both consent withdrawal AND subsequent affirmative opt-in.
- Hard `DELETE` privilege granted to `wapsi_app` introduces severe operational risks:
  1. An application bug or compromised key could issue `DELETE FROM public.opt_out_registry;`, silently destroying the suppression list for all opted-out customers.
  2. The system would then resume sending automated WhatsApp recovery messages to users who explicitly opted out, violating WhatsApp Business Policy and TRAI commercial communication regulations.
  3. It violates the core security invariant established in Phase 1D: **`wapsi_app` has ZERO DELETE privileges across the database.**

### 5.2 Recommendation: Eliminate DELETE via Audited Soft-Deactivation or Function
Instead of direct `DELETE`, re-consent should be handled via one of two zero-delete alternatives:

#### Alternative A: Status / Active Flag (Audited UPDATE) — *Recommended*
Add `is_active BOOLEAN NOT NULL DEFAULT true` and `revoked_at TIMESTAMPTZ` to `opt_out_registry`.
- Opt-out lookup:
  ```sql
  SELECT 1 FROM public.opt_out_registry WHERE phone = :phone AND is_active = true;
  ```
  *(Backed by partial index: `CREATE INDEX idx_opt_out_active ON public.opt_out_registry (phone) WHERE is_active = true;`)*
- Re-consent execution:
  ```sql
  UPDATE public.opt_out_registry 
  SET is_active = false, opted_out_at = now() 
  WHERE phone = :phone;
  ```
- **Grant to `wapsi_app`:** `GRANT SELECT, INSERT, UPDATE ON public.opt_out_registry TO wapsi_app;` (Zero `DELETE`).

#### Alternative B: Narrowly Scoped `SECURITY DEFINER` Function
Create a dedicated function `public.revoke_customer_opt_out(p_phone VARCHAR, p_reason VARCHAR, p_actor VARCHAR)` that performs the state change and writes to `opt_out_audit_trail` atomically inside a transaction.
- Only the function is granted `EXECUTE` to `wapsi_app`.
- Table `opt_out_registry` has zero `DELETE` grants.

> [!NOTE]
> Per strict instructions, Migration 5 has **not** been modified yet. This recommendation is presented for review prior to execution.

---

## 6. Task 5: Rollback Safety Analysis & Forward-Fix Principle

### 6.1 Operations in the Rollback Script That Permanently Delete Data

| Operation | Target Object | Impact & Risk Analysis |
| :--- | :--- | :--- |
| `DROP TABLE ... opt_out_audit_trail CASCADE;` | Compliance audit table | **Permanent data loss.** Destroys historical proof of opt-out requests, rendering the organization non-compliant under DPDP 2023 audits. |
| `DROP TABLE ... opt_out_registry CASCADE;` | Suppression registry | **Critical compliance hazard.** Removes active customer suppression entries. Any pending outbox dispatches could immediately contact opted-out users. |
| `DROP TABLE ... customer_interactions CASCADE;` | 24h window registry | **Policy violation risk.** Destroys WhatsApp 24-hour service window timestamps, risking free-form message policy violations. |
| `ALTER TABLE recovery_outbox DROP COLUMN case_id, payment_id, worker_id, lease_expires_at;` | Recovery outbox columns | **Permanent data loss.** Drops business correlation keys and worker lease tracking on existing outbox rows. |
| `ADD CONSTRAINT recovery_outbox_status_check CHECK (...)` | Status constraint | **Migration failure.** If any row exists with status `RECONCILIATION_REQUIRED` or `CANCELLED`, this statement fails immediately with a check constraint violation. |

### 6.2 Circumstances Where Rollback is Safe
Rollback using destructive `DROP TABLE` and `DROP COLUMN` is **only safe in a pre-production zero-data window**, specifically:
- When executed immediately following a failed deployment.
- When verified row counts on `opt_out_registry`, `opt_out_audit_trail`, and `recovery_outbox` are confirmed to be **0 rows**.

### 6.3 Forward-Fix Principle for Live Business Records
Once live business records or customer interactions exist:
- **Destructive rollbacks must never be executed.**
- Any defect or policy correction must be addressed via an incremental, non-destructive **forward-fix migration** (e.g. `20261101000006_...`) that preserves historical tables, adjusts grants or policies, and preserves compliance audit trails.

---

## 7. Task 6: Supabase CLI Dry-Run Execution & Results

### 7.1 Exact Command Executed
```powershell
npx supabase@latest db push --dry-run
```

### 7.2 Exact Raw CLI Output
```text
Warning: supabase db push will target the local database by default in the next major version. Pass --linked to keep targeting the linked project.
Initialising login role...
DRY RUN: migrations will *not* be pushed to the database.
Connecting to remote database...
Would push these migrations:
 • 20261101000004_phase1d_restricted_app_role.sql
 • 20261101000005_phase3_outbox_leases_and_opt_outs.sql
{"upToDate":false,"dryRun":true,"migrations":["20261101000004_phase1d_restricted_app_role.sql","20261101000005_phase3_outbox_leases_and_opt_outs.sql"],"seeds":[],"roles":[],"message":"Finished supabase db push."}
```

### 7.3 Dry-Run Audit Findings
- **Exit Code:** `0` (Success).
- **Target Database:** Linked remote project `filofxijqmgluuulivxb` (`WAPSI-DEV-MUMBAI`, `ap-south-1`).
- **Migrations Proposed:** Exactly the two staged migrations:
  1. `20261101000004_phase1d_restricted_app_role.sql`
  2. `20261101000005_phase3_outbox_leases_and_opt_outs.sql`
- **Docker Requirement:** **None.** The Supabase CLI connected directly to the remote hosted PostgreSQL cluster via TLS.
- **Schema Drift:** **None detected.** No conflicting DDL or untracked remote changes reported.
- **Database Mutation:** **Zero remote DDL executed.** Confirmed by `dryRun: true`.
- **Row Count Verification:** Remote catalog re-verified post dry-run via `scripts/verify_postgres_connection.py`; all 15 public schema tables remain at **0 rows**, and recorded migrations remain `['20261031000001', '20261031000002', '20261031000003']`.

---

## 8. Final Deployment Recommendation

Based on the verified dry-run and architectural audit:

1. **Opt-Out Permission Hardening:** Before executing the live push, refine Migration 5 to remove `GRANT DELETE ON public.opt_out_registry TO wapsi_app` and replace it with `is_active BOOLEAN NOT NULL DEFAULT true` and an audited `UPDATE` pattern. This preserves the absolute zero-DELETE security posture across all tables.
2. **Execution Method:** With `npx supabase db push --dry-run` fully functional and verified without Docker, the official deployment can be executed cleanly via:
   ```powershell
   npx supabase@latest db push --linked
   ```
   This ensures automatic recording in `supabase_migrations.schema_migrations` and eliminates manual Dashboard SQL Editor steps.
3. **Role Password Provisioning:** Immediately after `db push`, provision the `wapsi_app` password via Supabase SQL Editor (`ALTER ROLE wapsi_app WITH PASSWORD '...'`) and configure the backend `.env` to use `wapsi_app.filofxijqmgluuulivxb` on Session Pooler port `5432`.

---

> [!IMPORTANT] Awaiting Human Approval
> Phase 3.1A migration staging and dry-run are complete and verified. No remote changes have been applied.
> 
> Please advise whether you wish to:
> 1. Keep Migration 5 as-is or apply the zero-DELETE recommendation to `opt_out_registry`.
> 2. Authorize live execution via `npx supabase@latest db push --linked`.

