# PHASE 6 STAGE 2E: FINAL SANDBOX DISPATCH PREFLIGHT REPORT

**Preflight Date**: November 3, 2026  
**Auditor**: Antigravity Autonomous Security & Recovery Subsystem  
**Target Environment**: Development / Sandbox (Hosted Supabase PostgreSQL)  
**Target Outbox Job ID**: `5a6587ab-2601-4017-b396-48e3d2fc2fda`  
**Target Merchant UUID**: `04a2aaf8-8c8a-4d99-852c-cefc80e82019` (`Acme Global Technologies`)  
**Target Razorpay Link ID**: `plink_TvKucM1yXJQAZA` (Status: Unpaid, INR 10.00)  
**Target Recipient**: `+91 62600 *****` (Authorized Meta Test Handset: Arpit Jham)  
**Target Sender Phone Number ID**: `1407090562487899` (`+1 555-214-8539`)  
**Target WABA ID**: `969727602419694`  
**Auth Mode**: `WHATSAPP_AUTH_MODE=dashboard_sandbox`  
**Preflight Verdict**: **BLOCKED_WITH_REASONS**

---

## 1. Executive Preflight Summary

Prior to initiating the first real outbound WhatsApp message in the Meta sandbox, a strict, end-to-end read-only preflight verification was executed across the database, Razorpay API, Meta Graph API, webhook infrastructure, and CLI runner.

While the database schema, exact-job isolation, payment link, 24-hour customer window, and message payload are in an impeccable state, two external operational prerequisites currently prevent successful dispatch:
1. **BLOCKER 1 (Meta Token Expired)**: The active `WHATSAPP_DIAGNOSTIC_TOKEN` resolved by `WHATSAPP_AUTH_MODE=dashboard_sandbox` expired at `Monday, 02-Nov-26 13:00:00 PST` (Code 190). Meta Graph API calls using this token currently fail with HTTP 401.
2. **BLOCKER 2 (Webhook Listener Inactive)**: The local FastAPI server on port 8000 and its ngrok forwarding tunnel are currently not running, causing ngrok to return HTTP 404 for incoming Meta delivery status updates.

No state mutations, operator approvals, or message transmissions occurred.

---

## 2. Detailed Verification Matrix

| Section | Audit Domain | Target / Requirement | Observed Status | Verdict |
|:-------:|:-------------|:---------------------|:----------------|:-------:|
| **A** | **Environment & Token** | `WAPSI_ENV=development`<br>`RAZORPAY_MODE=test`<br>`WHATSAPP_AUTH_MODE=dashboard_sandbox`<br>Token validity via Meta Graph API | Environment settings verified.<br>`WHATSAPP_DIAGNOSTIC_TOKEN` selected (281 chars).<br>**Meta API Error (HTTP 401, Code 190)**: *Session has expired on Monday, 02-Nov-26 13:00:00 PST*. | **FAIL (BLOCKED)** |
| **B** | **Razorpay Payment Link** | `plink_TvKucM1yXJQAZA`<br>Amount: INR 10.00 (1000 paise)<br>Status: `created`<br>Amount paid: 0 | ID: `plink_TvKucM1yXJQAZA`<br>Amount: 1000 paise (INR 10.00)<br>Status: `created`<br>Amount paid: 0<br>URL: `https://rzp.io/rzp/NCf137AL` | **PASS** |
| **C** | **WhatsApp Service Window** | Latest inbound event in PostgreSQL<br>Provider timestamp + 24h > current UTC | Inbound message `wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhgWM0VCMEMyMjExQjFFODc0MEVEQ0QyMgA=`<br>Provider TS: `1793650733` (`2026-11-02 20:18:53 UTC`)<br>Expiry: `2026-11-03 20:18:53 UTC`<br>Current: `2026-11-03 03:08:55 UTC`<br>**Time Remaining: 17h 09m 57s** | **PASS** |
| **D** | **Outbox Job State** | Job `5a6587ab-2601-4017-b396-48e3d2fc2fda`<br>Merchant `04a2aaf8-8c8a-4d99-852c-cefc80e82019`<br>Status: `PENDING_APPROVAL`<br>Null approvals & leases<br>Payload hash integrity<br>Dual predicate claim | Status: `PENDING_APPROVAL`<br>`requires_operator_approval`: `True`<br>`approved_by_operator_id`: `None`<br>`approved_at`: `None`<br>`approval_snapshot_hash`: `None`<br>`worker_id`: `None`<br>Retry count: 0, Wamids: 0<br>Recipient matches `TEST_RECIPIENT_PHONE`<br>Opt-out status: `False`<br>Payload hash: `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd` (Exact match)<br>Calls `process_single_job_by_id(job_id, merchant_id)` | **PASS** |
| **E** | **Webhook Readiness** | FastAPI running on port 8000<br>Ngrok tunnel forwarding<br>Public base URL reachable | Local port 8000: Connection refused (Server stopped)<br>Public URL `https://crablike-outlook-pulmonary.ngrok-free.dev`: HTTP 404 (Tunnel detached) | **FAIL (BLOCKED)** |
| **F** | **Intended Message Body** | Retrieved from live outbox payload<br>Explicit sandbox warning present | Body verified: Includes warning *"Do NOT make a real payment."*<br>Payment URL: `https://rzp.io/rzp/NCf137AL` | **PASS** |
| **G** | **Runner Safety Audit** | Dry-run default<br>Asserted operator identity<br>Single-job concurrency isolation | Script verified: default is dry-run.<br>`--operator-id` documented as asserted identity attribute.<br>Exact-job execution path only. | **PASS** |

---

## 3. Section A: Meta Token & Environment Verification

### Graph API Diagnostic Call
Executing read-only inspection with the active `WHATSAPP_DIAGNOSTIC_TOKEN`:
```
GET https://graph.facebook.com/v21.0/1407090562487899
Status: 401 Unauthorized
Response: {"error":{"message":"Error validating access token: Session has expired on Monday, 02-Nov-26 13:00:00 PST. The current time is Monday, 02-Nov-26 19:02:48 PST.","type":"OAuthException","code":190}}
```

### Analysis
Developer dashboard temporary access tokens generated in the Meta App Developer Dashboard expire after 24 hours. Because the token expired at 13:00:00 PST on November 2, dispatch cannot succeed until a fresh token is pasted into `.env` under `WHATSAPP_DIAGNOSTIC_TOKEN`.

*(Note: The permanent System User token `WHATSAPP_ACCESS_TOKEN` is currently valid with `expires_at: 0` and successfully accesses `GET /1407090562487899` with GREEN quality rating, but was previously isolated from WABA container endpoints).*

---

## 4. Section B: Razorpay Payment Link Verification

Direct read-only inspection via `RazorpayClient.get_payment_link("plink_TvKucM1yXJQAZA")`:
- **Payment Link ID**: `plink_TvKucM1yXJQAZA`
- **Amount**: 1000 paise (`INR 10.00`)
- **Amount Paid**: `0` (Unpaid)
- **Currency**: `INR`
- **Status**: `created`
- **Short URL**: `https://rzp.io/rzp/NCf137AL`
- **Description**: `WAPSI Sandbox Test Recovery Link (Phase 6 Stage 2)`
- **Duplicate Links**: Zero. Exactly one link exists.

---

## 5. Section C: WhatsApp 24-Hour Customer Window Calculation

Querying `customer_interactions` and `webhook_inbox` in hosted PostgreSQL under merchant `04a2aaf8-8c8a-4d99-852c-cefc80e82019`:
- **Persisted Inbound Event ID**: `5806c68e-f605-4306-82d7-88ee930405f7`
- **Inbound Wamid**: `wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhgWM0VCMEMyMjExQjFFODc0MEVEQ0QyMgA=`
- **Provider Unix Timestamp**: `1793650733`
- **Provider UTC Timestamp**: `2026-11-02 20:18:53 UTC`
- **24-Hour Window Expiry**: `2026-11-03 20:18:53 UTC`
- **Current Audit Time**: `2026-11-03 03:08:55 UTC`
- **Time Remaining**: **17 hours 09 minutes 57 seconds**
- **Session Status**: **ACTIVE (User-Initiated Conversation Window Open)**

---

## 6. Section D: Outbox Job & Authorization Prerequisites

Retrieved outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` under tenant context `04a2aaf8-8c8a-4d99-852c-cefc80e82019`:
- **Job ID**: `5a6587ab-2601-4017-b396-48e3d2fc2fda`
- **Merchant ID**: `04a2aaf8-8c8a-4d99-852c-cefc80e82019`
- **Status**: `PENDING_APPROVAL` (Frozen)
- **Requires Operator Approval**: `True`
- **Approved By Operator ID**: `None`
- **Approved At**: `None`
- **Approval Snapshot Hash**: `None`
- **Worker ID**: `None`
- **Retry Count**: `0`
- **Existing Dispatches / Wamids**: `0`
- **Recipient Sanitization**: `WhatsAppClient.sanitize_phone_number(TEST_RECIPIENT_PHONE)` produces `916260055671`, matching `payload["to"]` digit-for-digit.
- **Opt-Out Check**: `PersistentOptOutStore.is_opted_out("+916260055671")` returned `False`.
- **Payload Hash Recomputation**:
  `compute_approval_hash(recipient_masked="+91****5671", channel="whatsapp", message_payload=job.message_payload)`
  yields exactly `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd`.

---

## 7. Section E: Webhook Readiness Inspection

- **Local FastAPI Health**:
  `GET http://127.0.0.1:8000/health` → `[WinError 10061] Connection refused`.
  The FastAPI process is currently not running.
- **Ngrok Public Tunnel**:
  `GET https://crablike-outlook-pulmonary.ngrok-free.dev/health` → `HTTP 404`.
  The ngrok tunnel is detached or pointing to an offline port.
- **Impact**: While dispatch can succeed independently, delivery status webhooks (`sent`, `delivered`, `read`) will not be ingested until the listener is restarted.

---

## 8. Section F: Exact Intended WhatsApp Message for Review

Extracted verbatim from live outbox payload:

```text
================================================================================
RECIPIENT: +91 62600 ***** (Arpit Jham - Authorized Test Handset)
SENDER:    +1 555-214-8539 (Phone Number ID: 1407090562487899, WABA: 969727602419694)
AMOUNT:    INR 10.00
LINK:      https://rzp.io/rzp/NCf137AL (Razorpay Test Mode)
================================================================================

MESSAGE BODY:
WAPSI SANDBOX TEST: Your payment link for INR 10.00 is ready: https://rzp.io/rzp/NCf137AL. (This is an automated test-mode sandbox simulation. Do NOT make a real payment. Reply STOP to opt out.)
================================================================================
```

---

## 9. Section G: Execution Command Audit & Instructions

Inspection of [`scripts/dispatch_approved_sandbox_job.py`](file:///C:/Users/arpit/Desktop/Razorpay/Razorpay/scripts/dispatch_approved_sandbox_job.py) verified:
- Default execution is strictly read-only dry-run (`--dry-run` or no flags).
- Approval requires explicit `--approve --operator-id <id>`.
- The operator ID is documented and logged as an asserted identity attribute.
- Worker dispatch is isolated strictly to `TARGET_JOB_ID` via `worker.process_single_job_by_id(...)`.
- Preflight guards abort before approval if the recipient opted out or payload was tampered.

### Exact PowerShell Execution Command (Prepared — DO NOT EXECUTE YET)
```powershell
cd Razorpay
$env:PYTHONPATH="."
.venv\Scripts\python scripts/dispatch_approved_sandbox_job.py --approve --operator-id "operator_arpit" --dispatch
```

---

## 10. Conclusion & Unblocking Checklist

### Verdict: **`BLOCKED_WITH_REASONS`**

Before executing the dispatch command above, the following two operational steps are required:

1. **Refresh `WHATSAPP_DIAGNOSTIC_TOKEN`**:
   - Open Meta for Developers Dashboard → App `963047183124334` → WhatsApp → API Setup.
   - Click **Generate access token**.
   - Update `WHATSAPP_DIAGNOSTIC_TOKEN=<fresh_token>` in `Razorpay/.env`.
2. **Start FastAPI and Ngrok Listener**:
   - Terminal 1: `.venv\Scripts\uvicorn wapsi.api.app:app --host 127.0.0.1 --port 8000`
   - Terminal 2: `ngrok http 8000 --url=crablike-outlook-pulmonary.ngrok-free.dev`

Once these two items are active, the system is fully unblocked and ready for immediate human authorization.

