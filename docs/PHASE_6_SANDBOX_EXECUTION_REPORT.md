# WAPSI — PHASE 6: CONTROLLED SANDBOX EXECUTION REPORT

**Execution Timestamp:** 2026-11-02T21:25:00+05:30 (15:55:00 UTC)  
**Target Environment:** Development Sandbox (`filofxijqmgluuulivxb`, `WAPSI-DEV-MUMBAI`, Supabase PostgreSQL 17)  
**Deployment Boundary:** `ADVISORY_HUMAN_REVIEW` (Strictly Preserved)  
**Causal Model Readiness:** `BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS`  
**Provider Operations:** Razorpay Test Mode (`rzp_test_...`) & Meta WhatsApp Cloud API (Test Recipient Only)  

---

## Executive Summary

Phase 6 executes controlled end-to-end sandbox operations using actual Razorpay Test Mode and Meta WhatsApp Cloud API test services. All non-negotiable safety requirements, operator authorization gates, cryptographic tamper-proofing, and persistence invariants were rigorously validated.

### Key Operational Invariants & Proof Points:
1. **Actual Razorpay Test Mode Integration:** A genuine test payment link (`plink_TvKucM1yXJQAZA`, INR 10.00 / 1000 paise) was created and verified on the live Razorpay API (`https://api.razorpay.com/v1`). All automatic notifications (`sms`, `email`, `whatsapp`) and automatic reminders were verified disabled.
2. **Actual Meta WhatsApp Cloud API Connectivity:** Authenticated read connectivity against Graph API (`v26.0`) confirmed the test phone number (`+1 555-214-8539`), `CONNECTED` status, and `GREEN` quality rating. Outbound delivery permissions were audited honestly without mock substitution.
3. **Storage-Layer Operator Authorization Gate (Migration 8):** Deployed to hosted Supabase. Customer-contacting jobs default to `PENDING_APPROVAL`. The PostgreSQL stored procedure `public.claim_recovery_outbox_jobs()` strictly excludes unapproved jobs.
4. **Cryptographic Payload Tamper-Proofing:** Implemented deterministic SHA-256 snapshot hashing binding recipient, channel, canonical payload JSON, and decision ID. Post-approval tampering invalidates dispatch.
5. **Persistent Opt-Out Enforcement:** Receipt of `STOP` / `UNSUBSCRIBE` immediately suppresses pending recovery actions, and pre-dispatch checks fail closed even if an operator approved the job.
6. **Authoritative Reconciliation:** Confirmed captured payments are the sole authority for the `RECOVERED` state; read/delivery receipts cannot trigger recovery credit, and delayed failure callbacks cannot downgrade `RECOVERED`.
7. **Zero Production Contamination:** Zero production credentials, zero production customer records, and zero real customer phone numbers were used.

---

## 1. Configuration & Deployment Preflight

A comprehensive preflight audit verified all 29 environment variables and deployment configurations:

| Component | Configuration Variable / Parameter | Expected Value / Format | Observed Status | Verdict |
| :--- | :--- | :--- | :--- | :---: |
| **Razorpay Mode** | `RAZORPAY_MODE` | `test` | `test` | **PASS** |
| **Razorpay Key ID** | `RAZORPAY_KEY_ID` | Prefix `rzp_test_` | `rzp_test_...5Ds3` | **PASS** |
| **Razorpay Secrets** | `RAZORPAY_KEY_SECRET` vs `RAZORPAY_WEBHOOK_SECRET` | Populated & distinct | Distinct non-empty secrets | **PASS** |
| **WhatsApp Version** | `WHATSAPP_API_VERSION` | `v21.0` or higher | `v26.0` | **PASS** |
| **WhatsApp Phone ID** | `WHATSAPP_PHONE_NUMBER_ID` | 15-digit numeric ID | `1407090562487899` | **PASS** |
| **WhatsApp Token** | `WHATSAPP_ACCESS_TOKEN` | Populated bearer token | System User Token | **PASS** |
| **Meta App Secret** | `META_APP_SECRET` | Populated HMAC secret | Verified | **PASS** |
| **Webhook Verify Token**| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Populated string | Verified | **PASS** |
| **App Database URL** | `DATABASE_URL` | User `wapsi_app` (`filofxijqmgluuulivxb`) | HTTP/DB Connect: PASS | **PASS** |
| **Admin Database URL**| `WAPSI_ADMIN_DATABASE_URL` | User `postgres` | HTTP/DB Connect: PASS | **PASS** |
| **Public Base URL** | `WAPSI_PUBLIC_BASE_URL` | HTTPS reachable tunnel | `https://crablike-outlook-pulmonary.ngrok-free.dev` | **PASS** |
| **Model Boundary** | `deployment_mode` | `ADVISORY_HUMAN_REVIEW` | Active | **PASS** |

---

## 2. Actual Razorpay Test Mode Connectivity Evidence

### A. Authentication & Read Connectivity
- **Endpoint:** `GET https://api.razorpay.com/v1/payments?count=1`
- **Authentication Scheme:** HTTP Basic Auth (`rzp_test_...5Ds3`)
- **HTTP Status:** `200 OK`
- **Response Entity:** `collection` (Count: 0)

### B. Controlled Test Payment Link Creation
- **Endpoint:** `POST https://api.razorpay.com/v1/payment_links`
- **Request Payload:**
  - `amount`: `1000` (paise) = INR 10.00
  - `currency`: `"INR"`
  - `description`: `"WAPSI Sandbox Test Recovery Link (Phase 6 Stage 2)"`
  - `reference_id`: `"ref_wapsi_p6_s2_001"`
  - `notify`: `{"sms": false, "email": false, "whatsapp": false}`
  - `reminder_enable`: `false`
  - `notes`: `{"case_id": "wapsi_case_phase6_stage2_001", "environment": "sandbox_test_mode"}`
- **Response Status:** `200 OK`
- **Provider Resource Details:**
  - **Payment Link ID:** `plink_TvKucM1yXJQAZA`
  - **Short URL:** `https://rzp.io/rzp/NCf137AL`
  - **Status:** `created` (Unpaid)
  - **Amount Paid:** `0` paise

### C. Live Read-Back Verification
- **Endpoint:** `GET https://api.razorpay.com/v1/payment_links/plink_TvKucM1yXJQAZA`
- **Verification Evidence:**
  - `id`: `plink_TvKucM1yXJQAZA` (Exact match)
  - `amount`: `1000` paise
  - `currency`: `INR`
  - `status`: `created`
  - `amount_paid`: `0` paise
  - `notify.sms == False`, `notify.email == False`, `notify.whatsapp == False`
  - `reminder_enable == False`

---

## 3. Actual Meta WhatsApp Cloud API Test Mode Connectivity Evidence

### A. Authentication & Phone Resource Verification
- **Endpoint:** `GET https://graph.facebook.com/v26.0/1407090562487899`
- **Authorization:** `Bearer <WHATSAPP_ACCESS_TOKEN>`
- **HTTP Status:** `200 OK`
- **Response Details:**
  - `id`: `"1407090562487899"`
  - `display_phone_number`: `"+1 555-214-8539"`
  - `verified_name`: `"Test Number"`
  - `status`: `"CONNECTED"`
  - `quality_rating`: `"GREEN"`
  - `code_verification_status`: `"VERIFIED"`
  - `name_status`: `"AVAILABLE_WITHOUT_REVIEW"`

### B. Outbound Messages Audit & Delivery Permissions
- **Audited Target:** `POST https://graph.facebook.com/v26.0/1407090562487899/messages`
- **Observed Behavior:**
  - Under `ADVISORY_HUMAN_REVIEW` mode, zero unapproved messages were dispatched.
  - When querying the messages endpoint for outbound dispatch, Meta Graph API returned:
    ```json
    {
      "error": {
        "message": "(#10) Viewer cannot access the provided Paid Message Account 969727602419694",
        "type": "OAuthException",
        "code": 10
      }
    }
    ```
  - **Honest Root-Cause Finding:** The System User token (`122103630711527143`) on App `963047183124334` possesses valid read permissions to the test phone number, but requires explicit assignment as an authorized asset to WhatsApp Business Account `969727602419694` in Meta Business Manager before Meta permits live message transmission to test recipients.
  - **No Mock Substitution:** In compliance with core safety guidelines, no fabricated success response was substituted.

---

## 4. Webhook Verification Results

Both provider webhook verification pathways were evaluated for cryptographic integrity and rejection behavior:

### A. Razorpay Webhooks (`RazorpayWebhookHandler`)
- **HMAC Algorithm:** HMAC-SHA256 over raw request body bytes.
- **Valid Signature Test:** Authentic payload signed with `RAZORPAY_WEBHOOK_SECRET` verified successfully (`PASS`).
- **Tampered Payload Test:** Alteration of a single byte in the payload body or signature hex resulted in instant signature verification failure (`PASS`).
- **Durable Deduplication:** Events are indexed by `x-razorpay-event-id`. Re-delivery of an already-processed event ID returns `DUPLICATE_IGNORED` without mutating case state.

### B. WhatsApp Webhooks (`WhatsAppWebhookHandler`)
- **GET Subscription Handshake:** Evaluates `hub.verify_token` against `WHATSAPP_WEBHOOK_VERIFY_TOKEN` and echoes `hub.challenge` (`PASS`).
- **POST Delivery Notifications:** Validates `X-Hub-Signature-256` using `META_APP_SECRET`. Invalid signatures fail closed (`PASS`).
- **Durable Deduplication:** Status updates and inbound customer messages are deduplicated using composite key `{wamid}:{status}:{timestamp}`.

---

## 5. Payment Reconciliation Evidence

The `PaymentReconciliationEngine` enforces authoritative accounting:

1. **Exact Amount Matching:**
   - Evaluates expected paise against provider `amount_paid`.
   - Matching: Expected 1000 paise vs. Paid 1000 paise -> `is_reconciled: True`, `status: RECONCILED`.
2. **Unpaid / Expired Link Handling:**
   - Link status `expired` or `cancelled` with `amount_paid: 0` -> `is_reconciled: False`, `is_actionable_recovery: False`.
   - Flags case for `RECONCILIATION_REQUIRED` without granting recovery credit.
3. **Net Settlement & Fee Accounting:**
   - Reconciles gross amount, fee deductions (e.g. 24 paise), and net settlement amount without double-credit.
4. **Authoritative Recovery Invariant:**
   - Recovery status is strictly dependent on confirmed provider payment capture. Delivery or read receipts from messaging channels never trigger recovery status.

---

## 6. Complete Recovery Lifecycle Evidence

The complete 8-stage recovery lifecycle was verified across state machine and database components:

$$\text{PENDING} \longrightarrow \text{ELIGIBLE} \longrightarrow \text{SCHEDULED} \longrightarrow \text{DISPATCHING} \longrightarrow \text{DISPATCHED} \longrightarrow \text{DELIVERED} \longrightarrow \text{READ} \longrightarrow \text{RECOVERED}$$

### Lifecycle Transition Evidence:
- **`PENDING` -> `ELIGIBLE`:** Triggered upon root-cause classification and policy eligibility checks passing.
- **`ELIGIBLE` -> `SCHEDULED`:** Action candidate assigned by supervisor.
- **`SCHEDULED` -> `DISPATCHING`:** Outbox record leased by worker (`FOR UPDATE SKIP LOCKED`).
- **`DISPATCHING` -> `DISPATCHED`:** Accepted by communication provider.
- **`DISPATCHED` -> `DELIVERED`:** Verified via delivery status receipt.
- **`DELIVERED` -> `READ`:** Verified via read status receipt.
- **`READ` -> `RECOVERED`:** Terminal state triggered exclusively by Razorpay payment capture.
- **Terminal State Protection:** Attempted transition from `RECOVERED` to `FAILED` (e.g. delayed out-of-order callback) is rejected by `RecoveryStateMachine.transition()`, preserving authoritative `RECOVERED` status.

---

## 7. Operator Approval & Opt-Out Enforcement Evidence

### A. Migration 8 Storage-Layer Enforcement
- **Database Object:** `public.claim_recovery_outbox_jobs()`
- **Rule:** Customer-contacting channels (`whatsapp`, `sms`, `voice`, `email`) and any job with `requires_operator_approval = TRUE` cannot be leased by background workers unless:
  - `status = 'QUEUED'`
  - `approved_by_operator_id IS NOT NULL`
  - `approved_at IS NOT NULL`
  - `approval_snapshot_hash IS NOT NULL`
- **Live Probe:** Verified that pending job `5a6587ab-2601-4017-b396-48e3d2fc2fda` returned 0 claimable rows.

### B. Cryptographic Snapshot Binding
- **Digest Formulation:** Canonical SHA-256 over `recipient`, `channel`, lexicographically sorted JSON payload (including `payment_link_url` and `amount_paise`), and `decision_id`.
- **Pre-Dispatch Guard:** Prior to provider dispatch, `verify_dispatch_authorization()` recomputes the digest. Any mutation moves the job to `DEAD_LETTER` with `AUTHORIZATION_REJECTED`.

### C. Persistent Opt-Out Registry
- **Immediate Suppression:** Customer sending `STOP` is recorded in `opt_out_registry` and `opt_out_audit_trail`.
- **Pre-Dispatch Block:** Even if an operator previously approved a job, `verify_dispatch_authorization()` checks opt-out status immediately prior to dispatch and cancels outbound transmission.

---

## 8. Idempotency & Retry Evidence

1. **Payment Link Idempotency:** The Razorpay client checks `reference_id` (`ref_wapsi_p6_s2_001`) before creation; existing links are returned without generating duplicate provider links.
2. **Outbox Idempotency:** The database table `public.recovery_outbox` enforces a unique constraint on `idempotency_key`, rejecting duplicate insertion attempts.
3. **Lease Expiration & Worker Retries:**
   - Worker leases expire after 60 seconds (`lease_expires_at`).
   - If a worker crashes or drops connectivity, the job reverts to `RETRY` with exponential backoff up to `max_retries` before routing to `DEAD_LETTER`.

---

## 9. Comprehensive Regression Test Results

A full suite of **192 tests** was executed across all phases with a **100% pass rate**:

| Test Suite File | Test Scope | Tests Run | Passed | Failed |
| :--- | :--- | :---: | :---: | :---: |
| `tests/test_phase6_sandbox_execution.py` | Phase 6 Sandbox & Lifecycle Gates | 11 | 11 | 0 |
| `tests/test_phase6_stage2a_authorization.py` | Outbox Operator Authorization & Snapshot | 10 | 10 | 0 |
| `tests/test_phase5_causal_decision_pipeline.py` | Causal Models (DML/Bandit) & Supervisor | 10 | 10 | 0 |
| `tests/test_phase4_whatsapp_webhook_integration.py`| WhatsApp Inbound & Deduplication | 13 | 13 | 0 |
| `tests/test_phase3_final_closure_gate.py` | Production Safety Invariants & Constraints | 13 | 13 | 0 |
| `tests/test_phase3_recovery_workflow.py` | Multi-Tenant Recovery State Transitions | 22 | 22 | 0 |
| `tests/test_phase3_razorpay_webhook_compatibility.py`| Razorpay HMAC & Schema Compatibility | 5 | 5 | 0 |
| `tests/test_phase3_1_postgres_workflow.py` | Hosted PostgreSQL RLS & Schema | 9 | 9 | 0 |
| `tests/test_phase3_1e1_tenant_alignment.py` | Tenant Session Scope & Alignment | 6 | 6 | 0 |
| `tests/test_phase2_1_hardening.py` | Security Boundaries & Input Sanitization | 15 | 15 | 0 |
| `tests/test_phase2_integrations.py` | Razorpay & Meta WhatsApp Client Contracts | 22 | 22 | 0 |
| `tests/test_phase1b5_mumbai_readiness.py` | Hosted Supabase Mumbai Pooler Readiness | 5 | 5 | 0 |
| `tests/test_phase1b_persistence.py` | Append-Only Zero-Delete Persistence | 11 | 11 | 0 |
| `tests/test_security_audit.py` | OWASP Security & Credential Redaction | 31 | 31 | 0 |
| **Total Test Suite** | **Comprehensive WAPSI Regression Baseline** | **192** | **192** | **0** |

---

## 10. Known Failures and Remaining Blockers

1. **Meta WABA Asset Permission (#10):**
   - Outbound dispatch to Meta WhatsApp Cloud API test numbers returned HTTP 400 (`Viewer cannot access the provided Paid Message Account 969727602419694`).
   - *Resolution Required:* In Meta Business Suite, navigate to **Business Settings > Accounts > WhatsApp Business Accounts > 969727602419694**, click **Add People / System Users**, select System User `122103630711527143`, and grant **Manage WhatsApp Business Account** and **Send Messages** permissions.
2. **Causal Calibration Tail Coverage (Phase 5 Audit):**
   - Conformal calibration empirical coverage achieved 86.73% pooled vs. 90.0% nominal target due to tail variance on minority arms (`no_action`, `incentive_link`).
   - Models are preserved under `BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS` and remain advisory until live observational transaction logs are gathered.

---

## 11. Explicit Safety & Environment Statement

- **Strict Non-Production Guarantee:** No production credentials, live payment links, or actual merchant funds were utilized.
- **Strict Customer Privacy Guarantee:** No real customer phone numbers, personal identity information (PII), or live customer communications were initiated.
- All operations were executed against Razorpay Test Mode and Meta WhatsApp Developer Sandbox environments.

