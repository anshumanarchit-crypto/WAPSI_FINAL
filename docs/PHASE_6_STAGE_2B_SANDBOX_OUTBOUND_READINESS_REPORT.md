# WAPSI — PHASE 6 STAGE 2B: SANDBOX OUTBOUND TOKEN ROUTING & READINESS REPORT

**Document ID:** `WAPSI-REP-P6-S2B-001`  
**Date:** 2026-11-03  
**Stage:** Phase 6 Stage 2B — Sandbox Outbound Token Routing & Operational Gate Readiness  
**Target Outbox Job ID:** `5a6587ab-2601-4017-b396-48e3d2fc2fda`  
**Target Payment Link ID:** `plink_TvKucM1yXJQAZA`  
**Target WABA ID:** `969727602419694`  
**Target Phone Number ID:** `1407090562487899` (`+1 555-214-8539`)  
**Target Recipient:** `+91 62600 *****` (Authorized Meta Test Handset: Arpit Jham)  
**Overall Readiness Verdict:** **PASS — READY FOR OPERATOR APPROVAL & DISPATCH**

---

## 1. Executive Summary

During Phase 6 Stage 2, automated outbound WhatsApp messaging encountered `HTTP 400 OAuthException Code 10 ("Viewer cannot access the provided Paid Message Account 969727602419694")` when authenticating via the Meta System User token (`WHATSAPP_ACCESS_TOKEN`). 

Subsequent deep diagnostics (`docs/PHASE_6_ALTERNATIVE_META_WABA_DIAGNOSTIC_REPORT.md`) proved that:
1. The WABA container (`969727602419694`) is an App Sandbox Test Account owned by Meta Business Portfolio `1432528762386008`.
2. The System User (`122103630711527143`) lacks container-level assignment in Meta Business Manager (`OAuthException Code 100, Subcode 33`).
3. Conversely, the dashboard developer user token (`WHATSAPP_DIAGNOSTIC_TOKEN`, user `122098240857535324`) possesses full authorized access (`HTTP 200 OK`) across WABA container endpoints, phone numbers, and messaging capabilities.

**Phase 6 Stage 2B** has adapted the WAPSI integration to allow actual sandbox outbound operations using the dashboard developer token via explicit, fail-closed configuration routing (`WHATSAPP_AUTH_MODE=dashboard_sandbox`), while keeping the production architecture, System User configuration, and security gates strictly protected and unchanged.

---

## 2. Token-Selection Architecture & Safety Guards

### 2.1 Explicit Routing via `WHATSAPP_AUTH_MODE`

A centralized token resolution pattern was implemented in `wapsi.core.config.WapsiSettings.get_whatsapp_token_str()`. All downstream messaging components (`WhatsAppClient`, `RecoveryBackgroundWorker`, `PaymentRecoveryOrchestrator`, and verification scripts) resolve tokens through this single source of truth.

```
                      ┌───────────────────────────────────────────────┐
                      │          WapsiSettings.get_whatsapp_token_str()│
                      └──────────────────────┬────────────────────────┘
                                             │
                       Is WHATSAPP_AUTH_MODE == "dashboard_sandbox"?
                                            / \
                                    YES    /   \   NO ("system_user")
                                          /     \
    ┌────────────────────────────────────▼┐      └────────────────────────────┐
    │ FAIL-CLOSED PRODUCTION GUARD        │                                   │
    │ 1. WAPSI_ENV must be "development"  │                                   │
    │ 2. RAZORPAY_MODE must be "test"     │                                   │
    │ 3. WHATSAPP_DIAGNOSTIC_TOKEN set?   │                                   │
    └──────────────────┬──────────────────┘                                   │
                       │                                                      │
         ┌─────────────┴─────────────┐                                        │
         │ All checks pass           │ Any check fails                        │
         ▼                           ▼                                        ▼
┌────────────────────────┐  ┌────────────────────────┐       ┌────────────────────────┐
│ Returns                │  │ Raises ValueError /    │       │ Returns                │
│ WHATSAPP_DIAGNOSTIC_   │  │ ValidationError        │       │ WHATSAPP_ACCESS_TOKEN  │
│ TOKEN                  │  │ (Fail Closed — NO      │       │ (Standard Production   │
│                        │  │ silent fallback)       │       │  System User Token)    │
└────────────────────────┘  └────────────────────────┘       └────────────────────────┘
```

### 2.2 Strict Fail-Closed Safeguards

1. **Environment Sandboxing Only:** `WHATSAPP_AUTH_MODE=dashboard_sandbox` is strictly permitted **only** when `WAPSI_ENV=development` and `RAZORPAY_MODE=test`.
2. **Production / Live Rejection:** If `WAPSI_ENV=production` or `RAZORPAY_MODE=live` is configured with `WHATSAPP_AUTH_MODE=dashboard_sandbox`, Pydantic's `validate_production_safety` immediately raises a hard `ValidationError` at startup, preventing initialization.
3. **No Silent Fallback:** If `dashboard_sandbox` mode is enabled but `WHATSAPP_DIAGNOSTIC_TOKEN` is missing or empty, `get_whatsapp_token_str()` raises a `ValueError` immediately. It is strictly forbidden from falling back to `WHATSAPP_ACCESS_TOKEN`.
4. **Secret Redaction:** Neither token string nor app secrets are ever logged or exposed in `__repr__` or exception traces (`SecretStr` used throughout).

---

## 3. Files Modified & Source Differences

| File | Change Type | Purpose |
| :--- | :--- | :--- |
| `wapsi/core/config.py` | Modified | Added `whatsapp_diagnostic_token: Optional[SecretStr]`, `whatsapp_auth_mode: str = "system_user"`, fail-closed validation logic, and dynamic token resolution in `get_whatsapp_token_str()`. |
| `.env` | Modified | Set `WHATSAPP_AUTH_MODE=dashboard_sandbox`. Retained `WHATSAPP_ACCESS_TOKEN` intact. |
| `.env.example` | Modified | Documented `WHATSAPP_AUTH_MODE` options and `WHATSAPP_DIAGNOSTIC_TOKEN`. |
| `wapsi/recovery/webhook_processor.py` | Hardened | Added clean session rollback on error during inbox mark-processed under restricted database role. |
| `tests/test_phase6_stage2b_sandbox_token_routing.py` | Added | 10 dedicated regression tests covering token selection, production rejection, fail-closed guards, secret masking, and outbox gates. |

---

## 4. Meta Provider Access Verification (Read-Only)

Using the newly routed dashboard token (`WHATSAPP_DIAGNOSTIC_TOKEN`), live Graph API v26.0 read-only queries were executed against Meta Cloud API:

| Endpoint | Target Resource | HTTP Status | Response Evidence |
| :--- | :--- | :---: | :--- |
| `GET /v26.0/969727602419694` | WABA Container | **200 OK** | `{"id": "969727602419694", "name": "Test Messaging Account", "currency": "USD", "timezone_id": "1"}` |
| `GET /v26.0/969727602419694/phone_numbers` | WABA Phone Numbers | **200 OK** | Returns `1407090562487899` (`display_phone_number: "+1 555-214-8539"`, `verified_name: "Test Number"`) |
| `GET /v26.0/1407090562487899` | Phone Sender Detail | **200 OK** | `{"id": "1407090562487899", "status": "CONNECTED", "quality_rating": "GREEN", "code_verification_status": "VERIFIED"}` |
| `GET /v26.0/969727602419694/message_templates` | WABA Templates | **200 OK** | Returns available sandbox templates (including standard `hello_world`) |

**Result:** Outbound provider connectivity, identity authorization, and sender readiness are confirmed **100% operational**.

---

## 5. Dry-Run Dispatch Pre-Flight Verification

A strictly read-only inspection was executed against live hosted PostgreSQL and Razorpay Test API. **Zero mutations, zero message sends, and zero approvals occurred.**

### 5.1 Pre-Flight Check Summary

| Check # | Dimension | Expected Condition | Observed State | Status |
| :-: | :--- | :--- | :--- | :-: |
| **1** | **Target Recipient** | Configured `TEST_RECIPIENT_PHONE` (`+91 62600 *****`) | `+91 62600 *****` | **PASS** |
| **2** | **Opt-Out Check** | Recipient has not opted out (`is_opted_out() == False`) | `is_opted_out == False` in PostgreSQL & SQLite | **PASS** |
| **3** | **24h Customer Session Window** | Recipient initiated message within past 24 hours | `is_within_24h_window == True` (Inbound "Test 2" at `1793644616`) | **PASS** |
| **4** | **Payment Link Integrity** | `plink_TvKucM1yXJQAZA` active, unpaid, INR 10.00 | `status: "created"`, `amount: 1000`, `amount_paid: 0` | **PASS** |
| **5** | **Token Selection** | `WhatsAppClient().access_token` resolves dashboard token | Resolved token matches `WHATSAPP_DIAGNOSTIC_TOKEN` | **PASS** |
| **6** | **Outbox Authorization Gate** | Job `5a6587ab-...` remains `PENDING_APPROVAL`, unapproved | `status: PENDING_APPROVAL`, `approved_by: None`, `worker: None` | **PASS** |

### 5.2 Outbox Job Details (`5a6587ab-2601-4017-b396-48e3d2fc2fda`)

- **Tenant / Merchant ID:** `04a2aaf8-8c8a-4d99-852c-cefc80e82019`
- **Case ID:** `wapsi_case_phase6_stage2_001`
- **Payment ID:** `pay_sandbox_p6_s2_001`
- **Action:** `WHATSAPP_ONE_CLICK_LINK`
- **Channel:** `whatsapp`
- **Recipient (Masked):** `+91****5671`
- **Current Status:** `PENDING_APPROVAL`
- **`requires_operator_approval`:** `True` (Migration 8 gate active)
- **`approved_by_operator_id`:** `None` (NULL)
- **`worker_id`:** `None` (NULL — unclaimable by workers)
- **`retry_count`:** `0` (Max: 3)
- **Message Content:**
  ```text
  WAPSI SANDBOX TEST: Your payment link for INR 10.00 is ready: https://rzp.io/rzp/NCf137AL. (This is a test recovery notification. Do NOT make a real payment.) Reply STOP to opt out.
  ```
- **Disclosures Present:**
  - `WAPSI SANDBOX TEST` prefix: **YES**
  - Explicit warning `Do NOT make a real payment`: **YES**
  - Unambiguous payment link `https://rzp.io/rzp/NCf137AL`: **YES**
  - Correct amount `INR 10.00`: **YES**
  - Statutory opt-out disclosure `Reply STOP to opt out`: **YES**

---

## 6. Regression Test Suite Results

A comprehensive automated test suite was executed against the implementation:

### 6.1 Phase 6 Stage 2B Dedicated Suite (`tests/test_phase6_stage2b_sandbox_token_routing.py`)

1. `test_1_development_dashboard_sandbox_selects_diagnostic_token` — **PASSED**
2. `test_2_production_always_selects_system_user_access_token` — **PASSED**
3. `test_3_dashboard_token_rejected_in_production` — **PASSED**
4. `test_4_missing_dashboard_token_fails_closed` — **PASSED**
5. `test_5_invalid_environment_combinations_fail_closed` — **PASSED**
6. `test_6_secrets_never_appear_in_logs_or_repr` — **PASSED**
7. `test_7_existing_webhook_functionality_unimpaired` — **PASSED**
8. `test_8_authorization_and_opt_out_gates_remain_enforced` — **PASSED**
9. `test_9_provider_client_uses_existing_api_integration` — **PASSED**
10. `test_10_no_customer_contact_without_operator_approval` — **PASSED**

**Stage 2B Suite Result:** **10 passed in 1.74s (100% pass rate)**

---

## 7. Exact Remaining Action for Actual Sandbox Dispatch

To transition from dry-run readiness to actual live delivery of the test message, the human operator must execute the single authorization action:

1. **Approve the Outbox Job:**
   Invoke `DurableOutboxStore.approve_job()` or execute:
   ```sql
   UPDATE recovery_outbox
   SET status = 'QUEUED',
       approved_by_operator_id = 'operator_admin_001',
       approved_at = NOW()
   WHERE id = '5a6587ab-2601-4017-b396-48e3d2fc2fda'
     AND status = 'PENDING_APPROVAL';
   ```
2. **Execute Worker Dispatch:**
   Once approved, the `RecoveryBackgroundWorker` or dispatch runner will claim the job, dispatch the WhatsApp message via Meta Cloud API using the routed `WHATSAPP_DIAGNOSTIC_TOKEN`, receive the provider `wamid`, and update the outbox status to `SENT`.

---

## 8. Summary Table: Sandbox Outbound Readiness Gate

| Dimension | Readiness Gate | Observed Status | Verdict |
| :--- | :--- | :--- | :---: |
| **Token Routing** | `WHATSAPP_AUTH_MODE=dashboard_sandbox` | Active & Verified | **PASS** |
| **Fail-Closed Guards** | Rejected in prod/live, no silent fallbacks | Validated in unit tests | **PASS** |
| **Meta Graph API** | WABA `969727602419694`, Phone `1407090562487899` | HTTP 200 OK | **PASS** |
| **Recipient Policy** | 24h Customer Service Window Active | `is_within_24h_window == True` | **PASS** |
| **Opt-Out Registry** | Recipient not opted out | `is_opted_out == False` | **PASS** |
| **Razorpay Link** | Link created, unpaid, INR 10.00 | Verified via API | **PASS** |
| **Message Payload** | Contains sandbox disclosures & opt-out | Verified | **PASS** |
| **Human Gate** | Job `5a6587ab-...` unapproved & unclaimed | `PENDING_APPROVAL` | **FROZEN (SAFE)** |

**Conclusion:** All pre-dispatch engineering and security requirements for Phase 6 Stage 2B are satisfied. Outbound dispatch is held safely behind the operator approval gate.

