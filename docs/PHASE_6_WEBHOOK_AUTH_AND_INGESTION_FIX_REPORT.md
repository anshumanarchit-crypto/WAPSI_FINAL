# WAPSI — PHASE 6: WEBHOOK AUTHENTICATION AND DURABLE INGESTION FIX REPORT

**Date:** 2026-11-02  
**Target Module:** Meta WhatsApp Cloud API Inbound Webhooks (`POST /api/v1/webhooks/whatsapp`)  
**Status:** **REMEDIATION COMPLETE / TESTS PASSING**  
**Database Identity:** PostgreSQL 17.11 (`wapsi_app` role, Supabase Transaction Pooler, Mumbai ap-south-1)

---

## 1. Executive Summary

Following the Phase 6 inbound verification audit, the WhatsApp webhook ingestion pipeline was systematically remediated to resolve the two identified defects:
1. **Unconditional Signature Verification:** Enforced cryptographic HMAC-SHA256 signature verification over exact raw request body bytes for every HTTP POST webhook across all environments, eliminating the development mode bypass (`verify=is_production`).
2. **Durable Database Ingestion Pipeline:** Ensured that the running FastAPI webhook endpoint delegates strictly to the Phase 4 `DurableWebhookEventProcessor` and `WebhookInboxRepository` with proper PostgreSQL tenant session scoping (`04a2aaf8-8c8a-4d99-852c-cefc80e82019`), preventing RLS permission errors and guaranteeing durable persistence in `webhook_inbox` and `customer_interactions`.
3. **Application Reload:** Terminated the stale Uvicorn worker (PID 11960) and launched an active server process with live source-watching reload enabled (`--reload`).

All 92 relevant unit, integration, and security regression tests passed without errors. Outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` remains strictly in `PENDING_APPROVAL`.

---

## 2. Files Modified

| File | Component | Nature of Changes |
| :--- | :--- | :--- |
| `wapsi/core/config.py` | Configuration | Removed `meta_app_secret_dev_demo` fallback; fail closed on unconfigured `META_APP_SECRET`; added `default_merchant_id`. |
| `wapsi/integrations/whatsapp/webhook.py` | Signature Verification & Parsing | Added `import time`; implemented strict HMAC verification with `hmac.compare_digest`; distinguished missing, malformed, and invalid signatures. |
| `wapsi/recovery/webhook_processor.py` | Durable Processor & Inbox | Added default `DatabaseManager` instantiation for PostgreSQL; added tenant session scope for RLS compatibility on `webhook_inbox`. |
| `wapsi/recovery/opt_out_store.py` | Interaction & Opt-Out Store | Defaulted `DatabaseManager` fallback to PostgreSQL cluster; updated interaction timestamps. |
| `wapsi/db/repository.py` | Persistence Repository | Added length guards ($\le 128$ chars) on `event_id`, `payment_id`, `nonce` in `WebhookInboxRepository` to prevent PostgreSQL `StringDataRightTruncation`. |
| `wapsi/api/app.py` | FastAPI Gateway | Re-architected `handle_whatsapp_webhook` to enforce strict ordering, fail closed on unconfigured secret, validate WABA & Phone ID, persist transactionally with tenant scope, and return HTTP 500 on database failure. |
| `tests/test_phase4_whatsapp_webhook_integration.py` | Phase 4 Tests | Aligned test fixture configuration with strict WABA and Phone ID checks. (13/13 passing) |
| `tests/test_phase6_webhook_authentication_and_ingestion.py` | Phase 6 Tests | **NEW** comprehensive test suite verifying signature enforcement, raw byte preservation, WABA validation, deduplication, retryable HTTP 500, and outbox isolation. (12/12 passing) |

---

## 3. Webhook Signature Verification Changes

In compliance with production security standards, `POST /api/v1/webhooks/whatsapp` now enforces:

1. **Exact Raw Request Body Bytes:**  
   The signature is computed directly over `await request.body()`. JSON deserialization occurs *only after* cryptographic validation succeeds.
2. **Fail-Closed on Missing Secret:**  
   If `META_APP_SECRET` is not populated in configuration, the endpoint fails closed immediately, returning `HTTP 500 Internal Server Error` without accepting unverified traffic.
3. **Strict Header Validation:**  
   - Missing `X-Hub-Signature-256` header $\rightarrow$ `HTTP 401 Unauthorized` (`detail="Missing X-Hub-Signature-256 header."`).
   - Malformed header (not starting with `sha256=` or empty hash) $\rightarrow$ `HTTP 401 Unauthorized` (`detail="Malformed X-Hub-Signature-256 header: must start with 'sha256='."`).
   - Signature hash mismatch $\rightarrow$ `HTTP 401 Unauthorized` (`detail="Invalid X-Hub-Signature-256: Meta cryptographic verification failed."`).
4. **Timing Attack Protection:**  
   Computed HMAC-SHA256 hex is compared against the provided header using constant-time comparison via Python's `hmac.compare_digest`.
5. **No Environment Bypass:**  
   The `verify_sig = is_production or ...` conditional was removed. Verification is mandatory regardless of `WAPSI_ENV`.
6. **Zero Secret/Signature Leakage:**  
   Logs only record signature presence and length (e.g., `len=71`), never raw secrets or hash values.
7. **Handshake Preservation:**  
   The existing `GET /api/v1/webhooks/whatsapp` endpoint continues to handle Meta's `hub.mode=subscribe` verification handshake without modification.

---

## 4. Durable Inbound Processing and Database Persistence Changes

The execution order of the incoming webhook handler was aligned with the transactional specification:

```
Receive Raw Body Bytes
        │
        ▼
Validate META_APP_SECRET Exists (HTTP 500 if missing)
        │
        ▼
Validate X-Hub-Signature-256 Header (HTTP 401 if missing/malformed)
        │
        ▼
Compute HMAC-SHA256 & Constant-Time Compare (HTTP 401 if mismatch)
        │
        ▼
Validate WABA ID & Phone Number ID against Configuration (HTTP 400 if mismatch)
        │
        ▼
Parse JSON Payload & Extract Statuses / Inbound Messages
        │
        ▼
Persist Inbound Customer Interaction (customer_interactions table, unlocks 24h window)
        │
        ▼
Durable Webhook Inbox Ingestion & Idempotent Deduplication (webhook_inbox table)
        │
        ▼
Commit Database Transaction
        │
        ▼
Acknowledge HTTP 200 OK
```

### PostgreSQL Row-Level Security (RLS) Alignment
Under the restricted `wapsi_app` role:
- Direct access to `webhook_inbox` requires `(merchant_id = current_active_merchant_id())`.
- Ingestion now operates inside a tenant session scope using the active sandbox merchant UUID `04a2aaf8-8c8a-4d99-852c-cefc80e82019`.
- If durable persistence fails at any stage, the endpoint raises `HTTP 500 Internal Server Error`, ensuring Meta receives a retryable server error and redelivers rather than logging a false positive acknowledgment.

---

## 5. Application Reload and Runtime Verification

1. **Stale Process Termination:**  
   The obsolete Uvicorn worker (PID 11960, started before Phase 4) was terminated.
2. **Live Auto-Reload Server Started:**  
   Launched Uvicorn with `--reload` watching `C:\Users\arpit\Desktop\Razorpay\Razorpay`:
   ```powershell
   uvicorn wapsi.api.app:app --host 127.0.0.1 --port 8000 --reload
   ```
3. **Live Server Verification:**
   - `GET /health` $\rightarrow$ `HTTP 200 OK` (`dialect=postgresql`, `connected=True`, `models_loaded=True`).
   - `GET /api/v1/webhooks/whatsapp?hub.mode=subscribe&...` $\rightarrow$ `HTTP 200 OK` (challenge accepted).
   - `POST /api/v1/webhooks/whatsapp` without signature $\rightarrow$ `HTTP 401 Unauthorized` (`Missing X-Hub-Signature-256 header.`).
   - `POST /api/v1/webhooks/whatsapp` with bad signature $\rightarrow$ `HTTP 401 Unauthorized` (`Invalid X-Hub-Signature-256: Meta cryptographic verification failed.`).

---

## 6. Test Results

### 6.1 Phase 6 Webhook Authentication & Ingestion Suite
`tests/test_phase6_webhook_authentication_and_ingestion.py`
- `test_correct_signature_accepted_development_mode` — **PASSED**
- `test_incorrect_signature_rejected_with_401` — **PASSED**
- `test_missing_signature_rejected_with_401` — **PASSED**
- `test_malformed_signature_rejected_with_401` — **PASSED**
- `test_missing_app_secret_fails_closed_in_development` — **PASSED**
- `test_raw_bytes_used_without_json_reserialization` — **PASSED**
- `test_waba_and_phone_number_id_validation_rejects_mismatch` — **PASSED**
- `test_genuine_inbound_persists_in_webhook_inbox_and_interactions` — **PASSED**
- `test_customer_interaction_persisted_exactly_once` — **PASSED**
- `test_duplicate_wamid_is_deduplicated` — **PASSED**
- `test_database_failure_returns_retryable_500_not_false_success` — **PASSED**
- `test_no_inbound_message_automatically_approves_outbox_job` — **PASSED**
**Result: 12 / 12 PASSED**

### 6.2 Phase 4 Inbound Webhook Integration Suite
`tests/test_phase4_whatsapp_webhook_integration.py`
**Result: 13 / 13 PASSED**

### 6.3 Phase 6 Sandbox Execution & Authorization Suites
- `tests/test_phase6_sandbox_execution.py` — **11 / 11 PASSED**
- `tests/test_phase6_stage2a_authorization.py` — **10 / 10 PASSED**

### 6.4 Security Regressions Suite
- `tests/test_security.py`
- `tests/test_phase1a_security.py`
- `tests/test_security_audit.py`
**Result: 46 / 46 PASSED**

**Overall Test Suite Result: 92 / 92 PASSED (100%)**

---

## 7. Safety Invariants Audit

| Invariant | Target Value | Observed Value | Verdict |
| :--- | :--- | :--- | :--- |
| **Outbox Job Status** | `PENDING_APPROVAL` | `PENDING_APPROVAL` | **PASS (FROZEN)** |
| **Operator Approval Flag** | `True` | `True` | **PASS (ENFORCED)** |
| **Approved Operator ID** | `None` | `None` | **PASS (UNAPPROVED)** |
| **Background Worker Claim** | 0 jobs claimed | 0 jobs claimed | **PASS (UNCLAIMABLE)** |
| **Outbound Messages Sent** | 0 | 0 | **PASS (ZERO SEND)** |
| **Payment Links Created** | 0 new links | `plink_TvKucM1yXJQAZA` (unpaid) | **PASS (UNCHANGED)** |
| **Causal Model Autonomy** | Advisory only | Advisory / Human review | **PASS (ADVISORY)** |

---

## 8. Remaining Blockers

1. **Meta App Secret Synchronization in `.env`:**  
   Because signature verification is now strictly enforced without exception, incoming webhooks from Meta's cloud platform must be signed using the secret configured in `.env`.
   - **Action Required:** Update `META_APP_SECRET` in `.env` with the App Secret from Meta Developer Dashboard (*Meta App 963047183124334 $\rightarrow$ App settings $\rightarrow$ Basic $\rightarrow$ App secret*).
   - Once saved, the running Uvicorn server will automatically reload via `StatReload`.
2. **Handset Transmission Verification:**  
   Once `META_APP_SECRET` is synchronized, sending a message from `+91 62600 55671` will immediately validate HMAC, persist into PostgreSQL `webhook_inbox` and `customer_interactions`, and record the active 24-hour customer window.

