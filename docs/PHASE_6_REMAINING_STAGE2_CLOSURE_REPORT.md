# WAPSI — PHASE 6 REMAINING STAGE 2 CLOSURE REPORT
## External Infrastructure Recovery, First Controlled Sandbox Dispatch, and Delivery Validation

**Execution Date:** 2026-11-03 06:05:00 UTC (11:35:00 IST)  
**Target Environment:** `development` (WAPSI-DEV-MUMBAI / Supabase Hosted PostgreSQL 17)  
**Merchant UUID:** `04a2aaf8-8c8a-4d99-852c-cefc80e82019` (`Acme Global Technologies`)  
**Deployment Boundary:** `ADVISORY_HUMAN_REVIEW` (Strictly Preserved)  
**Provider Operations:** Razorpay Test Mode & Meta WhatsApp Cloud API Sandbox  
**Status:** **STAGE 2 FULLY COMPLETE & VERIFIED**

---

## 1. Executive Summary

Phase 6 Stage 2 operational requirements have been successfully executed and concluded with the transmission of the first authentic, operator-approved outbound WhatsApp sandbox message.

All non-negotiable governance, security, and verification gates were satisfied:
1. **Fresh Sandbox Credentials Loaded:** The runtime was verified running under `WHATSAPP_AUTH_MODE=dashboard_sandbox` with the newly refreshed `WHATSAPP_DIAGNOSTIC_TOKEN`. Graph API `v26.0` read-only checks confirmed access to Phone Number ID `1407090562487899` and Sandbox WABA `969727602419694`.
2. **Infrastructure Verification:** FastAPI (port 8000) and the persistent ngrok tunnel (`https://crablike-outlook-pulmonary.ngrok-free.dev`) were verified active, healthy, and responsive to webhook verification challenges.
3. **Target Job State Reconciliation:** Outbox row `5a6587ab-2601-4017-b396-48e3d2fc2fda` was inspected under tenant context `04a2aaf8-8c8a-4d99-852c-cefc80e82019`. The original operator approval by `operator_arpit` and its cryptographic SHA-256 snapshot hash `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd` were confirmed 100% intact and unmutated.
4. **Existing Payment Link Validation:** Razorpay Payment Link `plink_TvKucM1yXJQAZA` was validated via read-only GET (`status: created`, `amount: 1000 paise`, `amount_paid: 0`, `currency: INR`). No duplicate link was generated.
5. **Exact-Job Outbound Dispatch:** `RecoveryBackgroundWorker` executed the exact job under Mode B (Direct Meta Payload). Meta Graph API accepted the message with **HTTP 200 OK**, returning message ID `wamid.HBgMOTE2MjYwMDU1NjcxFQIAERgSRUE0Q0I5RjUyQjI0QjZBNTE0AA==`.
6. **Real Webhook Delivery Validation:** Meta Cloud API dispatched real delivery webhooks to the public ngrok endpoint. FastAPI verified the raw-bytes HMAC-SHA256 signature (`X-Hub-Signature-256`) and persisted `whatsapp.sent` and `whatsapp.delivered` status receipts into `public.webhook_inbox` in hosted PostgreSQL.

---

## 2. Infrastructure & Credential Verification (Stage 2.1)

### A. Runtime Configuration & Token Audit
- **Environment:** `WAPSI_ENV=development`, `RAZORPAY_MODE=test`
- **Auth Mode:** `WHATSAPP_AUTH_MODE=dashboard_sandbox`
- **Active Token Selection:** `WHATSAPP_DIAGNOSTIC_TOKEN` (Masked: `EAANr4...ZDZD`)
- **Token Verification (`/debug_token`):**
  - `is_valid`: `True`
  - `application`: `"WAPSI Payment Recovery"` (App ID: `963047183124334`)
  - `type`: `USER`
  - `scopes`: `["whatsapp_business_management", "whatsapp_business_messaging", "public_profile"]`
  - `expires_at`: `1793689200` (Valid active session)

### B. Meta Resource Reachability (Read-Only GET)
- **Phone Number Check:** `GET /v26.0/1407090562487899` -> `HTTP 200 OK`
  - `display_phone_number`: `"+1 555-214-8539"`
  - `verified_name`: `"Test Number"`
  - `quality_rating`: `"GREEN"`
  - `status`: `"CONNECTED"`
- **WABA Check:** `GET /v26.0/969727602419694` -> `HTTP 200 OK`
  - `name`: `"Test Messaging Account"`
  - `id`: `"969727602419694"`
- **WABA Phone Numbers:** `GET /v26.0/969727602419694/phone_numbers` -> `HTTP 200 OK`

### C. Services & Webhook Handshake
- **FastAPI Core:** `http://127.0.0.1:8000/health` -> `HTTP 200 OK` (`models_loaded: true`, DB latency: 190ms)
- **Ngrok Public Tunnel:** `https://crablike-outlook-pulmonary.ngrok-free.dev` -> Forwarding to `127.0.0.1:8000`
- **Local Webhook Challenge:** `GET http://127.0.0.1:8000/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.challenge=test_challenge_abc` -> `HTTP 200 OK`
- **Public Webhook Challenge:** `GET https://crablike-outlook-pulmonary.ngrok-free.dev/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.challenge=test_challenge_abc` -> `HTTP 200 OK`

---

## 3. Approved Target Job Reconciliation (Stage 2.2)

Target record in `public.recovery_outbox`:
```json
{
  "id": "5a6587ab-2601-4017-b396-48e3d2fc2fda",
  "merchant_id": "04a2aaf8-8c8a-4d99-852c-cefc80e82019",
  "case_id": "wapsi_case_phase6_stage2_001",
  "channel": "whatsapp",
  "recipient_masked": "+91****5671",
  "requires_operator_approval": true,
  "approved_by_operator_id": "operator_arpit",
  "approved_at": "2026-11-03 04:06:37.554877+00:00",
  "approval_snapshot_hash": "dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd",
  "idempotency_key": "idemp_p6_s2_plink_TvKucM1yXJQAZA",
  "retry_count": 1
}
```

### Governance Verification:
1. **Hash Verification:** Canonical payload hash computed over recipient `+91****5671`, channel `whatsapp`, operator `operator_arpit`, and message body:
   - Stored Hash: `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd`
   - Recomputed Hash: `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd`
   - **Verdict:** `MATCH_VERIFIED` (Zero tampering).
2. **Opt-Out Check:** Recipient phone checked against `PersistentOptOutStore` -> `is_opted_out: False`.
3. **24-Hour Customer Service Window:** Inbound event timestamp `2026-11-02 20:18:53 UTC` -> Expiry `2026-11-03 20:18:53 UTC` (~14.3 hours remaining). **Active**.
4. **Payment Link Existence:** Razorpay `GET /v1/payment_links/plink_TvKucM1yXJQAZA`:
   - Amount: `1000` paise (INR 10.00)
   - Status: `created`
   - Amount paid: `0` paise
   - Currency: `INR`
   - Short URL: `https://rzp.io/rzp/NCf137AL` (Present verbatim in approved message body).

---

## 4. Controlled Outbound Message Execution (Stage 2.3 & 2.4)

### Execution Trace:
- **Command:** `python scripts/dispatch_approved_sandbox_job.py --dispatch`
- **Claim Function:** `public.claim_specific_recovery_outbox_job(p_job_id, p_merchant_id, p_worker_id, 60)` under tenant session `04a2aaf8-8c8a-4d99-852c-cefc80e82019`.
- **Worker Claim:** Worker `worker_1f7bbf98` claimed exact job `5a6587ab-2601-4017-b396-48e3d2fc2fda`.
- **Mode B Detection:** Pre-formed Meta Cloud API message object detected.
- **Payment Link Validation:** Read-only GET verified existing link `plink_TvKucM1yXJQAZA`. Zero new payment links created.
- **Provider Request:**
  - Method: `POST https://graph.facebook.com/v26.0/1407090562487899/messages`
  - Authorization: `Bearer <WHATSAPP_DIAGNOSTIC_TOKEN>`
  - Recipient: `916260055671`
  - Body:
    ```text
    WAPSI SANDBOX TEST: Your payment link for INR 10.00 is ready: https://rzp.io/rzp/NCf137AL. (This is an automated test-mode sandbox simulation. Do NOT make a real payment. Reply STOP to opt out.)
    ```
- **Provider Response:** `HTTP 200 OK`
  - **Provider Message ID (`wamid`):** `wamid.HBgMOTE2MjYwMDU1NjcxFQIAERgSRUE0Q0I5RjUyQjI0QjZBNTE0AA==`
- **Postgres Outbox State Transition:**
  - `status`: `SENT`
  - `worker_id`: `worker_1f7bbf98`
  - `updated_at`: `2026-11-03 06:02:06.838022+00:00`
  - Execution Result: `COMPLETED` (Error: None)

---

## 5. Webhook Delivery Receipt Validation (Stage 2.5)

Immediately following transmission, Meta Cloud API dispatched real webhook callbacks to ngrok:

### Inbound Delivery Event 1: `whatsapp.sent`
- **Event ID:** `wamid.HBgMOTE2MjYwMDU1NjcxFQIAERgSRUE0Q0I5RjUyQjI0QjZBNTE0AA==:sent:1793685730`
- **Provider Timestamp:** `1793685730`
- **Signature:** Valid `X-Hub-Signature-256` HMAC verified.
- **FastAPI Ingestion Status:** `HTTP 200 OK` (`statuses_processed: 1`).
- **PostgreSQL Persistence:** Stored in `public.webhook_inbox`.

### Inbound Delivery Event 2: `whatsapp.delivered`
- **Event ID:** `wamid.HBgMOTE2MjYwMDU1NjcxFQIAERgSRUE0Q0I5RjUyQjI0QjZBNTE0AA==:delivered:1793685731`
- **Provider Timestamp:** `1793685731`
- **Status:** `delivered`
- **Pricing Category:** `free_customer_service` (`subtype: free_tier`)
- **FastAPI Ingestion Status:** `HTTP 200 OK` (`statuses_processed: 1`).
- **PostgreSQL Persistence:** Stored in `public.webhook_inbox` at `2026-11-03 06:02:14.147997 UTC`.

---

## 6. Safety & Operational Invariants Summary

| Invariant | Guaranteed Behavior | Observed Evidence |
|:---|:---|:---:|
| **Zero Production Payments** | No real money charged; test link unpaid. | `amount_paid: 0` verified on Razorpay API. |
| **No Duplicate Payment Links** | Existing link resolved and reused. | `plink_TvKucM1yXJQAZA` reused; 0 new links created. |
| **No Unapproved Dispatches** | Customer contact requires operator approval. | `operator_arpit` approval verified cryptographically before send. |
| **Tamper Detection** | Post-approval modification halts send. | Canonical hash matched stored hash bit-for-bit. |
| **Exact-Job Claim Isolation** | Claiming by ID touches only requested job. | Worker claimed strictly `5a6587ab`, zero other jobs affected. |
| **Fail-Closed Tenant Isolation** | Missing/mismatched merchant context fails closed. | Migration 11 dual predicate enforced in PostgreSQL. |
| **Post-Dispatch Outbox Completion** | Job moves to `SENT` upon receipt of wamid. | Outbox row updated to `SENT` with wamid persisted. |

---

## 7. Stage 2 Final Verdict

**STAGE 2 STATUS: COMPLETE & FULLY VERIFIED**  
- Razorpay test link created and validated: **DONE**
- Meta WhatsApp sandbox authorization resolved: **DONE**
- Pre-dispatch preflight gates: **PASSED**
- Single controlled outbound message transmitted: **DONE** (`wamid.HBgMOTE2MjYwMDU1NjcxFQIAERgSRUE0Q0I5RjUyQjI0QjZBNTE0AA==`)
- Delivery webhook received and persisted: **DONE** (`whatsapp.delivered`)

