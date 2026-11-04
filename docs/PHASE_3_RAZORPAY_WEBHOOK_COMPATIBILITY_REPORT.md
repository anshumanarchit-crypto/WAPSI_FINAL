# WAPSI — Phase 3 Final Closure: Razorpay Webhook Endpoint Compatibility Report

**Environment:** Hosted Supabase (`WAPSI-DEV-MUMBAI` / `filofxijqmgluuulivxb`)  
**Runtime Role:** `wapsi_app`  
**Active Branch:** `wapsi/phase3-recovery-workflow`  
**FastAPI Status:** Running on `127.0.0.1:8000` (Restricted Application Role)  
**Date:** 2026-11-01  

---

## 1. Executive Summary

During restricted ngrok tunnel testing, genuine Razorpay webhook POST requests to `/api/v1/webhooks/razorpay` returned **HTTP 422 Unprocessable Entity**, reporting missing fields: `event`, `payment_id`, `amount`, `timestamp`, `nonce`.

This investigation diagnosed the root cause, implemented an architectural separation between internal benchmark testing and authentic Razorpay webhooks, hardened cryptographic raw-body signature validation, and confirmed 100% test passing across the 384-test backend regression suite.

---

## 2. Root Cause Analysis

### 2.1 The Issue: Dual-Decorated Internal Route with Strict Pydantic Schema

In `wapsi/api/app.py`, the endpoint handler `handle_webhook` was decorated with two route paths:
```python
# Before fix:
@app.post("/api/v1/webhook")
@app.post("/api/v1/webhooks/razorpay")
async def handle_webhook(payload: WebhookPayloadRequest, request: Request): ...
```

The parameter `payload: WebhookPayloadRequest` mandated a Pydantic schema originally designed for internal synthetic benchmark requests:
- Required top-level fields: `event`, `payment_id`, `amount`, `timestamp`, `nonce`.
- Pydantic validates incoming JSON bodies **before** the handler function executes.

### 2.2 Genuine Razorpay Webhook Payload Structure

Authentic webhooks emitted by Razorpay (e.g., `payment_link.paid`, `payment.captured`, `payment.failed`) do **not** use top-level `payment_id`, `amount`, or `nonce`. Instead:
1. Payment and payment link data are encapsulated inside `payload[entity_type][entity]`:
   - `payload["payment_link"]["entity"]["id"]`
   - `payload["payment"]["entity"]["id"]`
   - `payload["payment"]["entity"]["amount"]` (in paise)
2. Timestamps use `created_at` (epoch seconds).
3. The event identifier is optionally provided via header `X-Razorpay-Event-Id` and inside the payload as `event` (e.g., `"event": "payment_link.paid"`).
4. Signature is passed in header `X-Razorpay-Signature` computed over the exact UTF-8 byte representation of the raw HTTP request body.

Because the old handler relied on Pydantic to parse the body as `WebhookPayloadRequest`, FastAPI intercepted authentic Razorpay requests during deserialization and rejected them with **HTTP 422**, preventing signature validation from ever executing.

---

## 3. Corrected Route Architecture

We established a clean architectural separation between the internal simulation protocol and the authentic external webhook gateway:

```
                                  INCOMING TRAFFIC
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
    POST /api/v1/webhook                         POST /api/v1/webhooks/razorpay
(Internal Benchmark / Simulation)                 (Authentic Razorpay Gate)
                 │                                               │
  Validates WebhookPayloadRequest                 Raw body bytes extracted directly
  HMAC-SHA256 signature check                     Header X-Razorpay-Signature enforced
  Freshness check (<300s)                         Constant-time HMAC-SHA256 verification
  Anti-replay deduplication                      JSON parsed ONLY after signature passes
                 │                                Event normalized (payment / payment_link)
                 │                                Anti-replay & persistent inbox deduplication
                 ▼                                               ▼
    Simulation / Audit Ledger                    PaymentRecoveryOrchestrator
                                                 (State reconciliation to RECOVERED)
```

### 3.1 Preserved Internal Benchmark Endpoint (`/api/v1/webhook`)
- Preserved specifically for internal WAPSI automated benchmark harnesses, stress suites, and synthetic test events.
- Retains `WebhookPayloadRequest` schema with `nonce` and `timestamp`.

### 3.2 Dedicated External Razorpay Endpoint (`/api/v1/webhooks/razorpay`)
- Defined with `async def handle_razorpay_webhook(request: Request)`.
- **Zero Pydantic Pre-Validation:** Inspects raw HTTP socket bytes before any JSON deserialization.
- **Fail-Closed Header Gate:** Rejects requests missing `X-Razorpay-Signature` immediately with **HTTP 401 Unauthorized**.
- **Cryptographic Signature Verification:** Computes HMAC-SHA256 over raw request body using constant-time comparison (`hmac.compare_digest`). Fails with **HTTP 401 Unauthorized** if the signature is invalid.
- **JSON Parsing Gate:** Deserializes JSON only *after* cryptographic verification succeeds. If the JSON payload is malformed, returns **HTTP 400 Bad Request**.
- **Event Extraction & Normalization:** Employs `RazorpayWebhookHandler.parse_event` to safely extract entity data across both `payment_link` and `payment` payload envelopes.
- **Deduplication:**
  1. In-memory `anti_replay_cache` keyed on `X-Razorpay-Event-Id` (or deterministic composite key).
  2. Persistent PostgreSQL webhook inbox table (`webhook_events`) via `PersistenceService.record_webhook_event`.
  3. Returns **HTTP 200 OK** with `idempotency_status: "duplicate_ignored"` on duplicate deliveries.
- **Orchestration Dispatch:** Routes normalized event to `PaymentRecoveryOrchestrator.handle_razorpay_webhook_event(event)` to trigger authoritative case transitions (e.g., `DISPATCHED` -> `RECOVERED`).

---

## 4. Cryptographic Raw-Body Signature Implementation

In `wapsi/integrations/razorpay/webhook.py`:
```python
@classmethod
def verify_signature(
    cls,
    raw_body: Union[str, bytes],
    signature: str,
    secret: Optional[Union[str, bytes]] = None,
) -> bool:
    if not signature or not raw_body:
        return False

    raw_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    sec_bytes = None
    if secret:
        sec_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    else:
        try:
            sec_bytes = get_settings().get_webhook_secret_bytes()
        except Exception as e:
            logger.error(f"Webhook secret unavailable for signature verification: {e}")
            return False

    if not sec_bytes:
        return False

    expected_sig = hmac.new(sec_bytes, raw_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature.strip())
```

---

## 5. Verification & Test Results

### 5.1 Dedicated Compatibility Test Suite
We created `tests/test_phase3_razorpay_webhook_compatibility.py` containing 14 targeted test cases verifying all acceptance criteria:

| # | Test Name | Target Behavior | Result |
|---|-----------|-----------------|:------:|
| 1 | `test_razorpay_webhook_valid_signature` | Valid signature on raw body -> HTTP 200 processed | **PASSED** |
| 2 | `test_razorpay_webhook_invalid_signature` | Corrupted signature -> HTTP 401 Unauthorized | **PASSED** |
| 3 | `test_razorpay_webhook_modified_raw_body` | Tampered body after signing -> HTTP 401 Unauthorized | **PASSED** |
| 4 | `test_razorpay_webhook_missing_signature_header` | Request without header -> HTTP 401 Unauthorized | **PASSED** |
| 5 | `test_razorpay_webhook_malformed_json_after_valid_signature` | Valid sig on invalid JSON -> HTTP 400 Bad Request | **PASSED** |
| 6 | `test_razorpay_webhook_payment_link_paid` | `payment_link.paid` triggers case `RECOVERED` transition | **PASSED** |
| 7 | `test_razorpay_webhook_payment_captured` | `payment.captured` triggers payment link reconciliation | **PASSED** |
| 8 | `test_razorpay_webhook_duplicate_event_id` | Duplicate `X-Razorpay-Event-Id` -> HTTP 200 `duplicate_ignored` | **PASSED** |
| 9 | `test_razorpay_webhook_missing_event_id_header` | Deterministic fallback keying without header -> HTTP 200 | **PASSED** |
| 10 | `test_razorpay_webhook_out_of_order_preserves_recovered` | Delayed `payment.failed` after `RECOVERED` preserves terminal state | **PASSED** |
| 11 | `test_razorpay_webhook_invalid_amount_or_currency` | Non-numeric amount or non-INR currency handled gracefully | **PASSED** |
| 12 | `test_razorpay_webhook_mismatched_payment_link_id` | Webhook with unknown IDs logged safely without crashing | **PASSED** |
| 13 | `test_internal_webhook_endpoint_still_operational` | `/api/v1/webhook` backward compatibility preserved | **PASSED** |
| 14 | `test_whatsapp_webhook_endpoints_still_operational` | WhatsApp webhook GET/POST routes completely intact | **PASSED** |

### 5.2 Full Backend Regression Suite
- Total tests executed: **384**
- Passed: **384**
- Failed: **0**
- Duration: 145.39s (2m 25s)
- **Zero regressions detected across all existing WAPSI modules.**

### 5.3 Live Localhost HTTP Probes (Port 8000)
Direct probes against the freshly restarted FastAPI daemon confirmed:
1. **Invalid Signature Probe:**
   - Request: `POST http://127.0.0.1:8000/api/v1/webhooks/razorpay` with `X-Razorpay-Signature: invalid_hex_sig_here`
   - Response: `HTTP 401 Unauthorized` (`Invalid X-Razorpay-Signature: cryptographic HMAC-SHA256 verification failed.`)
   - *Confirmation: HTTP 422 is completely eliminated.*
2. **Valid Signature Probe:**
   - Request: `POST http://127.0.0.1:8000/api/v1/webhooks/razorpay` with HMAC-SHA256 computed on raw bytes
   - Response: `HTTP 200 OK` (`idempotency_status: "processed"`, `signature_verified: True`)
3. **Replay / Duplicate Probe:**
   - Request: Identical payload and signature re-submitted
   - Response: `HTTP 200 OK` (`idempotency_status: "duplicate_ignored"`, `signature_verified: True`)
4. **Missing Signature Header Probe:**
   - Request: Payload without `X-Razorpay-Signature`
   - Response: `HTTP 401 Unauthorized` (`Missing X-Razorpay-Signature header on webhook request.`)
5. **Malformed Body Probe:**
   - Request: Valid HMAC signature on raw bytes `b"not a json {{{"`
   - Response: `HTTP 400 Bad Request` (`Invalid JSON webhook body: Expecting value: line 1 column 1 (char 0)`)
6. **Internal Route Backward Compatibility Probe:**
   - Request: `POST http://127.0.0.1:8000/api/v1/webhook` with synthetic benchmark payload
   - Response: `HTTP 200 OK` (`idempotency_status: "processed"`, `signature_verified: True`)

---

## 6. Ngrok Tunnel & Webhook Configuration Guidance

With the endpoint fix in place, configure Razorpay Test Mode webhooks:

1. **Webhook URL:** `https://<YOUR_NGROK_DOMAIN>/api/v1/webhooks/razorpay`
2. **Secret:** Match the value in `RAZORPAY_WEBHOOK_SECRET` in `.env`.
3. **Active Events to Subscribe:**
   - `payment_link.paid`
   - `payment_link.cancelled`
   - `payment_link.expired`
   - `payment.captured`
   - `payment.failed`
4. **Alert Email:** Operator notification email.

---

## 7. Operational Safety Declarations

- **Zero Live Payments:** No live charges or real customer transactions were initiated.
- **Zero Secrets Leakage:** No API keys, database passwords, or webhook secrets were printed or committed.
- **Restricted Database Role Maintained:** FastAPI runs under `wapsi_app` Session Pooler port 5432.
- **Zero Continuous Workers Started:** Background recovery loop remains off awaiting explicit operator authorization.
- **Git Hygiene:** Changes isolated to working tree; zero unstaged code pushed to remote.

