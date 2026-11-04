# WAPSI — PHASE 6 STAGE 2C: CONTROLLED OPERATOR APPROVAL PREPARATION REPORT

**Document ID:** `WAPSI-REP-P6-S2C-001`  
**Date:** 2026-11-03  
**Stage:** Phase 6 Stage 2C — Controlled Operator Approval Preparation  
**Target Outbox Job ID:** `5a6587ab-2601-4017-b396-48e3d2fc2fda`  
**Target Payment Link ID:** `plink_TvKucM1yXJQAZA`  
**Target Recipient:** `+91 62600 *****` (Authorized Meta Test Handset: Arpit Jham)  
**Target Sender:** `+1 555-214-8539` (Phone Number ID: `1407090562487899`, WABA: `969727602419694`)  
**Overall Readiness Verdict:** **PASS — PREPARED & LOCKED AWAITING OPERATOR AUTHORIZATION**

---

## 1. Executive Summary

Following the successful implementation of fail-closed sandbox token routing in Phase 6 Stage 2B, **Phase 6 Stage 2C** has completed all technical and governance preparations for the controlled approval of the staged WhatsApp recovery message.

All inspection, verification, and preparation requirements have been executed under strict read-only constraints:
- **Zero mutations** were performed on the database outbox records.
- **Zero approvals** were executed.
- **Zero background worker processes** were run.
- **Zero outbound WhatsApp messages** (`POST /messages`) were transmitted.
- **Zero new payment links** were created.

The staged recovery job (`5a6587ab-2601-4017-b396-48e3d2fc2fda`) remains frozen in `PENDING_APPROVAL` status, verified by database queries and guarded by Migration 8 stored procedures and application security gates.

---

## 2. Approval Architecture & Defect Remediation

### 2.1 Inspection of the Existing Approval Mechanisms

An end-to-end inspection of the WAPSI codebase revealed the approval lifecycle components:

1. **Database Schema Gate (Migration 8):**
   `public.recovery_outbox` enforces `requires_operator_approval = TRUE`. The SECURITY DEFINER procedure `public.claim_recovery_outbox_jobs()` strictly excludes any customer-contacting job where `status = 'PENDING_APPROVAL'` or where `approved_by_operator_id IS NULL`, `approved_at IS NULL`, or `approval_snapshot_hash IS NULL`.
2. **Outbox Store Service (`DurableOutboxStore.approve_job()`):**
   Transitions status from `PENDING_APPROVAL` to `QUEUED`, records `approved_by_operator_id`, records `approved_at` timestamp, and calculates/persists the canonical `approval_snapshot_hash`.
3. **Pre-Dispatch Verification (`DurableOutboxStore.verify_dispatch_authorization()`):**
   Defensively executed by the worker immediately before provider contact:
   - Verifies `approved_by_operator_id`, `approved_at`, and `approval_snapshot_hash` exist.
   - Recomputes the SHA-256 hash over the live job attributes and matches it against `approval_snapshot_hash` (tamper detection).
   - Re-checks that the customer has not opted out in the persistent registry.

### 2.2 Defect Identified & Repaired: PostgreSQL RLS Tenant Scoping

**Root Cause:**  
Under PostgreSQL RLS (`wapsi_app` role), `recovery_outbox` enforces:
```sql
merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::UUID
```
In `wapsi/recovery/outbox.py`, `DurableOutboxStore.approve_job()`, `reject_job()`, and `get_job()` executed `with self.db_manager.session_scope() as session:` without setting transaction-local merchant context. Under the restricted `wapsi_app` role, SQLAlchemy's `session.get(RecoveryOutboxModel, j_uuid)` returned `None`, which would have caused programmatic approval to fail silently.

**Remediation:**  
1. Updated `DurableOutboxStore.approve_job()`, `reject_job()`, and `get_job()` to use `self.db_manager.tenant_session_scope(merchant_id)` whenever `merchant_id` is provided.
2. Updated `PaymentRecoveryEngine` and `get_outbox_store()` to default to `get_db_manager()` from `wapsi.db.session`, ensuring runtime connectivity to PostgreSQL with proper RLS context.
3. Added `get_outbox_job()`, `approve_outbox_job()`, and `reject_outbox_job()` service methods to `PaymentRecoveryEngine`.

### 2.3 Exposed Application HTTP API Endpoints

To provide a fully supported, production-grade approval interface beyond programmatic scripts, dedicated FastAPI endpoints were implemented in `wapsi/api/app.py`:

- **`GET /api/v1/recovery/outbox/{job_id}`**: Retrieves outbox job state with authenticated tenant scoping.
- **`POST /api/v1/recovery/outbox/{job_id}/approve`**: Explicitly approves a pending job. Requires non-empty `operator_id` (minimum 3 characters, maximum 128 characters), verifies `PENDING_APPROVAL` status, computes snapshot hash, records approval metadata, and atomically transitions status to `QUEUED`.
- **`POST /api/v1/recovery/outbox/{job_id}/reject`**: Explicitly rejects a pending job, transitioning status to `REJECTED` with an audit reason so workers never claim it.

All endpoints strictly enforce API key authentication via `_verify_recovery_auth(request)`.

---

## 3. Operator Authentication & Identity Resolution

In accordance with strict system security principles:
1. **Tenant Authentication:** The caller must authenticate with a valid WAPSI API key in the `X-API-Key` or `Authorization: Bearer <key>` header.
2. **Real Operator Identity:** The approving human operator identity must be passed explicitly in the request body as `operator_id` (e.g. `"operator_arpit_jham"` or `"operator_archit_anshuman"`).
3. **No Fabricated Identities:** The system does not invent, hardcode, or assume a default operator identity. An empty or whitespace `operator_id` is rejected with `HTTP 422 Unprocessable Entity` at the API boundary and raises `ValueError` in the service store.
4. **Audit Trail:** The provided `operator_id` is permanently written into `recovery_outbox.approved_by_operator_id` and recorded into `recovery_timeline` as an `OPERATOR_APPROVAL_GRANTED` event.

---

## 4. Cryptographic Approval Snapshot Hash

To guarantee zero payload tampering between operator approval and provider transmission, a deterministic SHA-256 snapshot hash is computed:

$$\text{Canonical Content} = \text{recipient\_masked} \parallel \text{":"} \parallel \text{channel.lower()} \parallel \text{":"} \parallel \text{canonical\_payload\_json} \parallel \text{":"} \parallel \text{decision\_id}$$

$$\text{approval\_snapshot\_hash} = \text{SHA-256}(\text{Canonical Content})$$

### Pre-Computed Hash for Target Job `5a6587ab-2601-4017-b396-48e3d2fc2fda`:
- **Recipient (Masked):** `+91****5671`
- **Channel:** `whatsapp`
- **Canonical Payload JSON:**
  ```json
  {"messaging_product":"whatsapp","recipient_type":"individual","text":{"body":"WAPSI SANDBOX TEST: Your payment link for INR 10.00 is ready: https://rzp.io/rzp/NCf137AL. (This is an automated test-mode sandbox simulation. Do NOT make a real payment. Reply STOP to opt out.)","preview_url":true},"to":"916260055671","type":"text"}
  ```
- **Deterministic SHA-256 Hash:**  
  `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd`

Any post-approval alteration to recipient, text, link, or amount will result in immediate rejection by `verify_dispatch_authorization()` before external network transmission.

---

## 5. Live Pending Job Verification (Hosted PostgreSQL)

A direct, read-only query against hosted PostgreSQL under tenant context `04a2aaf8-8c8a-4d99-852c-cefc80e82019` verified all 11 target conditions:

| Parameter / Condition | Expected Value | Observed Database State | Verification |
| :--- | :--- | :--- | :---: |
| **Job ID** | `5a6587ab-2601-4017-b396-48e3d2fc2fda` | `5a6587ab-2601-4017-b396-48e3d2fc2fda` | **EXACT MATCH** |
| **Status** | `PENDING_APPROVAL` | `PENDING_APPROVAL` | **FROZEN** |
| **Channel** | `whatsapp` | `whatsapp` | **MATCH** |
| **Recipient (Masked)** | `+91****5671` | `+91****5671` (matches `TEST_RECIPIENT_PHONE`) | **MATCH** |
| **Payment Link ID** | `plink_TvKucM1yXJQAZA` | `https://rzp.io/rzp/NCf137AL` embedded in payload | **MATCH** |
| **Monetary Amount** | `INR 10.00` | `"INR 10.00"` stated in message body | **MATCH** |
| **Explicit Sandbox Warning** | Warning against real payment | `"Do NOT make a real payment"` present | **PASS** |
| **Opt-Out Status** | `False` | `is_opted_out() == False` in DB & SQLite | **CLEAR** |
| **24h Customer Window** | Active session window | `is_within_24h_window() == True` (from `"Test 2"`) | **ACTIVE** |
| **Worker Lease** | No active lease or claim | `worker_id: None`, `lease_expires_at: None` | **UNCLAIMED** |
| **Provider Message ID** | No previous dispatch | No `wamid` or `message_id` in payload | **NO DISPATCH** |

---

## 6. Active Sandbox Token Routing Verification

Provider authorization using the routed dashboard token (`WHATSAPP_DIAGNOSTIC_TOKEN`) was verified:

| Verification Check | Required Configuration | Live Runtime Value | Status |
| :--- | :--- | :--- | :---: |
| **`WAPSI_ENV`** | `development` | `development` | **PASS** |
| **`RAZORPAY_MODE`** | `test` | `test` | **PASS** |
| **`WHATSAPP_AUTH_MODE`** | `dashboard_sandbox` | `dashboard_sandbox` | **PASS** |
| **Client Token Resolution** | Resolves `WHATSAPP_DIAGNOSTIC_TOKEN` | Verified (`1c2120d5...`, len 281) | **PASS** |
| **Meta Graph API Phone Check** | `GET /v26.0/1407090562487899` | **HTTP 200 OK** (`VERIFIED`, `GREEN`) | **PASS** |
| **Secret Masking** | Zero credentials logged or exposed | 100% redacted | **PASS** |

---

## 7. Controlled Execution Procedures

A dedicated, controlled execution runner has been prepared:
[`scripts/dispatch_approved_sandbox_job.py`](file:///c:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/dispatch_approved_sandbox_job.py)

The operator may execute approval and dispatch via either of two supported paths:

### Path A: Single-Command CLI Runner (Recommended)

When authorized, the operator executes:
```powershell
cd Razorpay
.venv\Scripts\python scripts/dispatch_approved_sandbox_job.py --approve --operator-id "operator_arpit_jham" --dispatch
```

**Step Breakdown:**
1. **Pre-Flight Validation:** Inspects job state, confirms `PENDING_APPROVAL`, checks opt-out status, and verifies the 24h customer window.
2. **Approval Phase:** Invokes `store.approve_job()`, setting `approved_by_operator_id = "operator_arpit_jham"`, `approved_at = NOW()`, `approval_snapshot_hash = "dd0bcf49..."`, and transitioning status to `QUEUED`.
3. **Dispatch Phase:** Launches `RecoveryBackgroundWorker.process_batch(batch_size=1)`. The worker acquires a lease on job `5a6587ab-...`, verifies the cryptographic hash against `verify_dispatch_authorization()`, executes `POST /v26.0/1407090562487899/messages` via `WhatsAppClient`, receives the provider `wamid`, updates status to `SENT`, and logs the sanitized dispatch receipt.

### Path B: HTTP REST API + Worker

1. **Approve via API:**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/recovery/outbox/5a6587ab-2601-4017-b396-48e3d2fc2fda/approve" \
     -H "X-API-Key: rzp_test_wapsi_key_2026" \
     -H "Content-Type: application/json" \
     -d '{"operator_id": "operator_arpit_jham", "reason": "Authorized Phase 6 Stage 2C Sandbox single-message dispatch"}'
   ```
2. **Execute Worker Dispatch:**
   ```powershell
   cd Razorpay
   .venv\Scripts\python scripts/dispatch_approved_sandbox_job.py --dispatch
   ```

---

## 8. Automated Test Suite Results

A comprehensive 10-test suite was added to validate all Stage 2C approval gates:
[`tests/test_phase6_stage2c_operator_approval_preparation.py`](file:///c:/Users/arpit/Desktop/Razorpay/Razorpay/tests/test_phase6_stage2c_operator_approval_preparation.py)

| Test Identifier | Scenario Tested | Result |
| :--- | :--- | :---: |
| `test_1_get_outbox_job_requires_authentication` | Unauthenticated requests rejected with 401 | **PASSED** |
| `test_2_get_outbox_job_returns_details_when_authenticated` | Authenticated request returns pending job state | **PASSED** |
| `test_3_approve_outbox_job_endpoint_validates_operator_id` | Missing/empty operator_id rejected with 422 | **PASSED** |
| `test_4_outbox_store_approve_job_requires_operator_id` | Store raises ValueError on empty operator_id | **PASSED** |
| `test_5_compute_approval_hash_is_deterministic` | SHA-256 hash calculation is deterministic & tamper-sensitive | **PASSED** |
| `test_6_verify_dispatch_authorization_checks_operator_evidence` | Unapproved job fails dispatch authorization | **PASSED** |
| `test_7_tampered_payload_rejected_after_approval` | Payload modification post-approval fails verification | **PASSED** |
| `test_8_customer_opt_out_blocks_authorization_even_if_approved` | Opt-out blocks dispatch even if job is approved | **PASSED** |
| `test_9_unapproved_job_blocked_from_worker_claim` | Unapproved job claimable by 0 workers | **PASSED** |
| `test_10_target_sandbox_job_remains_frozen_in_pending_approval` | Hosted target job remains strictly untouched | **PASSED** |

**Regression Suite Result:**
- Stage 2C Dedicated Suite: **10 passed, 0 failed in 13.67s**
- Combined Full Phase 6 Suite: **42 passed, 0 failed in 15.13s (100% pass rate)**

---

## 9. Remaining Risks & Pre-Dispatch Summary

| Risk Dimension | Current Assessment | Mitigation in Place |
| :--- | :--- | :--- |
| **Accidental Autonomous Send** | **ZERO RISK** | Job is `PENDING_APPROVAL`; stored procedure requires approval metadata before claiming. |
| **Payload Tampering** | **ZERO RISK** | `approval_snapshot_hash` (`dd0bcf49...`) verified before message transmission. |
| **Customer Contact Violation** | **ZERO RISK** | Opt-out check (`is_opted_out == False`) and 24h customer window (`is_within_24h_window == True`) confirmed open. |
| **Financial / Link Error** | **ZERO RISK** | Payment Link `plink_TvKucM1yXJQAZA` (INR 10.00, unpaid) verified intact on Razorpay Test API. |
| **Token Invalidation** | **LOW RISK** | Dashboard token verified active with Meta Graph API (`HTTP 200 OK`). Valid for ~24 hours from generation. |

---

## 10. Conclusion

All engineering, security, and governance preparations for **Phase 6 Stage 2C** are complete. 

The outbox job remains safely frozen in `PENDING_APPROVAL`. **No messages have been sent.**

The system is now halted and awaits explicit operator authorization to execute the dispatch command.

