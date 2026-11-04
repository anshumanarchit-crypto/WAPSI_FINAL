# WAPSI — Phase 3 Final Closure: Public Webhook URL Configuration Report

**Target Project:** WAPSI-DEV-MUMBAI (`filofxijqmgluuulivxb`)  
**Runtime Role:** `wapsi_app` (Session Pooler Port 5432)  
**Branch:** `wapsi/phase3-recovery-workflow`  
**FastAPI Status:** Running on `127.0.0.1:8000`  
**Public Base URL:** `https://crablike-outlook-pulmonary.ngrok-free.dev`  
**Date:** 2026-11-01  

---

## 1. Executive Summary

During the Phase 3 recovery execution readiness audit, the E2E dry-run reported:
```
Callback Base URL:    http://127.0.0.1:8000
Externally Reachable: False
```

The running ngrok HTTPS tunnel is:
`https://crablike-outlook-pulmonary.ngrok-free.dev`

This task investigated the exact configuration mechanics, introduced the centralized configuration variable `WAPSI_PUBLIC_BASE_URL` into `WapsiSettings`, updated `.env` without modifying any existing database or provider credentials, corrected the external reachability probe in `scripts/e2e_recovery_sandbox_runner.py` to evaluate allowed webhook endpoints (rather than non-webhook routes blocked by ngrok policy), and validated live end-to-end reachability.

---

## 2. Configuration Inspection & Variable Identification

### 2.1 Runner Inspection
In `scripts/e2e_recovery_sandbox_runner.py`, the callback URL was evaluated via:
```python
backend_base_url = os.environ.get("WAPSI_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
```
When `WAPSI_PUBLIC_BASE_URL` was unset in `.env`, the runner fell back to localhost, marking `Externally Reachable: False`.

### 2.2 Pydantic Configuration Alignment
In `wapsi/core/config.py`, the `WapsiSettings` class previously lacked a dedicated field for the public base URL. We declared:
```python
public_base_url: str = Field(default="http://127.0.0.1:8000", alias="WAPSI_PUBLIC_BASE_URL")
```
along with convenience properties:
- `is_public_base_url_configured: bool`
- `razorpay_webhook_url: str` (`{base_url}/api/v1/webhooks/razorpay`)
- `whatsapp_webhook_url: str` (`{base_url}/api/v1/webhooks/whatsapp`)

### 2.3 Exact Configuration Variable Used
- **Variable Name:** `WAPSI_PUBLIC_BASE_URL`
- **Configured Value:** `https://crablike-outlook-pulmonary.ngrok-free.dev`

---

## 3. Files Modified

| File | Change Description |
|------|--------------------|
| `.env` | Appended `WAPSI_PUBLIC_BASE_URL=https://crablike-outlook-pulmonary.ngrok-free.dev`. Preserved all existing database and provider secrets intact. |
| `.env.example` | Documented `WAPSI_PUBLIC_BASE_URL=https://your-tunnel-subdomain.ngrok-free.dev` under Application Server configuration. |
| `wapsi/core/config.py` | Added `public_base_url` field and webhook URL helper properties to `WapsiSettings`. |
| `scripts/e2e_recovery_sandbox_runner.py` | Integrated `probe_external_webhook_reachability()` to actively verify external tunnel accessibility via allowed webhook routes; aligned URL resolution with `settings.public_base_url`. |
| `scripts/verify_public_webhook_tunnel.py` | Added standalone validation script testing tunnel reachability, policy shielding, and cryptographic fail-closed behavior. |

---

## 4. External Reachability Probe Implementation

### 4.1 Traffic Policy Constraints
The ngrok Traffic Policy intentionally enforces a perimeter defense shield:
- **Denied Routes (HTTP 404):** `/api/v1/health`, root `/`, documentation `/docs`, and all administrative routes.
- **Permitted Routes:** 
  - `GET /api/v1/webhooks/whatsapp`
  - `POST /api/v1/webhooks/whatsapp`
  - `POST /api/v1/webhooks/razorpay`

If a reachability probe pings `/` or `/api/v1/health`, ngrok returns HTTP 404, which would falsely report the tunnel as broken.

### 4.2 Probe Architecture
The corrected probe function (`probe_external_webhook_reachability`) tests allowed webhook endpoints:
1. **WhatsApp Handshake Probe (`GET /api/v1/webhooks/whatsapp`):**
   - Dispatches a request without valid Meta verification tokens.
   - FastAPI responds with **HTTP 403 Forbidden** (`Meta webhook subscription verification failed. Invalid hub.verify_token.`).
   - Receiving HTTP 403 proves the request traversed the public ngrok tunnel and reached the FastAPI application.
2. **Razorpay Webhook Probe (`POST /api/v1/webhooks/razorpay`):**
   - Dispatches an empty POST request without `X-Razorpay-Signature`.
   - FastAPI responds with **HTTP 401 Unauthorized** (`Missing X-Razorpay-Signature header on webhook request.`).
   - Receiving HTTP 401 proves the request traversed the public ngrok tunnel and reached the FastAPI application.
3. **Policy Shield Check (`GET /api/v1/health`):**
   - Confirms that non-webhook routes remain denied with **HTTP 404**.
4. **Policy Invariant:**
   - HTTP 404 policy denials on webhooks count as failure.
   - Deliberate HTTP 401 or 403 application errors count as reachability confirmation.

---

## 5. Live HTTP Verification Results

Running `scripts/verify_public_webhook_tunnel.py` against the live ngrok tunnel:

```
================================================================================
WAPSI PHASE 3: PUBLIC WEBHOOK TUNNEL & ROUTE REACHABILITY VERIFICATION
================================================================================

[*] 1. Configuration Validation:
       + WAPSI_PUBLIC_BASE_URL:    https://crablike-outlook-pulmonary.ngrok-free.dev
       + Is HTTPS:                 True
       + Razorpay Webhook URL:     https://crablike-outlook-pulmonary.ngrok-free.dev/api/v1/webhooks/razorpay
       + WhatsApp Webhook URL:     https://crablike-outlook-pulmonary.ngrok-free.dev/api/v1/webhooks/whatsapp
       [PASS] Configuration correctly specifies public HTTPS tunnel base URL.

[*] 2. WhatsApp Webhook External Reachability Probe (GET):
       + Status: HTTP 403
       + Response Body: {"error":"HTTP Error","detail":"Meta webhook subscription verification failed. Invalid hub.verify_token."...
       [PASS] Request traversed ngrok tunnel and reached FastAPI (HTTP 403 verify token check).

[*] 3. Razorpay Webhook External Reachability Probe (POST):
       + Status: HTTP 401
       + Response Body: {"error":"HTTP Error","detail":"Missing X-Razorpay-Signature header on webhook request."...
       [PASS] Request traversed ngrok tunnel and reached FastAPI (HTTP 401 signature header check).

[*] 4. ngrok Traffic Policy Enforcement Probes (Non-Webhook Routes):
       + Path '/api/v1/health': HTTP 404 [PASS - Blocked by ngrok traffic policy]
       + Path '/': HTTP 404 [PASS - Blocked by ngrok traffic policy]
       + Path '/docs': HTTP 404 [PASS - Blocked by ngrok traffic policy]

[*] 5. Cryptographic Signature Fail-Closed Check:
       + Status: HTTP 401 (Invalid signature rejected)
       + Response: {"error":"HTTP Error","detail":"Invalid X-Razorpay-Signature: cryptographic HMAC-SHA256 verification...
       [PASS] Cryptographic HMAC-SHA256 signature verification is fail-closed.

[*] 6. Zero Provider Operations Safety Guarantee:
       + Razorpay Payment Links Created: 0 (No API calls dispatched)
       + WhatsApp Messages Sent:         0 (No API calls dispatched)
       + Database Role:                  wapsi_app (Session Pooler port 5432)
       + Credentials Changed:            NONE (Strictly preserved)
       [PASS] Absolute safety constraints verified.

================================================================================
[SUCCESS] All public webhook URL reachability and policy requirements verified.
================================================================================
```

---

## 6. Runner Dry-Run Audit Results

Executing `inspect_configuration_readiness()` from `scripts/e2e_recovery_sandbox_runner.py`:

```
[*] 4. Webhook Reachability & Signature Verification:
       + Callback Base URL:       https://crablike-outlook-pulmonary.ngrok-free.dev
       + Razorpay Webhook URL:    https://crablike-outlook-pulmonary.ngrok-free.dev/api/v1/webhooks/razorpay
       + WhatsApp Webhook URL:    https://crablike-outlook-pulmonary.ngrok-free.dev/api/v1/webhooks/whatsapp
       + Externally Reachable:    True
       + Local HMAC Validation:   True
       + Live Probe Status:       Public tunnel verified: WhatsApp endpoint reachable (HTTP 403), Razorpay endpoint reachable (HTTP 401), Policy shield: active (HTTP 404 non-webhook blocked).
       [PASS] Externally reachable HTTPS callback URL verified via live probe.
```

---

## 7. Safety & Credential Integrity Confirmation

We authoritatively confirm:
- **`DATABASE_URL`:** Unchanged (points to `wapsi_app` on Supabase Session Pooler port 5432).
- **`WAPSI_ADMIN_DATABASE_URL`:** Unchanged (preserves administrative recovery connection).
- **`RAZORPAY_KEY_ID`:** Unchanged.
- **`RAZORPAY_KEY_SECRET`:** Unchanged.
- **`RAZORPAY_WEBHOOK_SECRET`:** Unchanged.
- **`WHATSAPP_ACCESS_TOKEN`:** Unchanged.
- **`WHATSAPP_PHONE_NUMBER_ID`:** Unchanged.
- **Database Permissions:** Restricted `wapsi_app` role with zero DELETE privileges maintained.
- **No Provider Dispatches:** Zero payment links created, zero WhatsApp messages dispatched, and the E2E runner was not executed.

