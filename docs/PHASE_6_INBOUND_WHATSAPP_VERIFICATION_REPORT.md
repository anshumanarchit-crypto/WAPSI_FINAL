# WAPSI — PHASE 6: INBOUND WHATSAPP MESSAGE PERSISTENCE & SESSION WINDOW REPORT

**Date:** 2026-11-03  
**Target Provider Message ID:** `wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBMjIzMzZFRUQ4MjNCOUREM0FBODZFNENBNjkyMTUA`  
**Provider Timestamp:** `1793644616` (2026-11-02 18:36:56 UTC / 2026-11-03 00:06:56 IST)  
**Message Text:** `"Test 2"`  
**Sender:** `+91 62600 *****` (Authorized Meta Test Recipient: Arpit Jham)  
**Meta Test Number:** `+1 555-214-8539` (Phone Number ID: `1407090562487899`)  
**WABA ID:** `969727602419694`  
**Verification Verdict:** **PASS / FULLY PERSISTED & VERIFIED**

---

## 1. Executive Summary

Following the remediation of the HMAC-SHA256 signature verification pipeline and tenant RLS session scoping, an authentic incoming WhatsApp message sent as **"Test 2"** from the registered Meta test handset (`+91 62600 *****`) was received at the public webhook endpoint:
`https://crablike-outlook-pulmonary.ngrok-free.dev/api/v1/webhooks/whatsapp`.

The event was authenticated via constant-time cryptographic HMAC-SHA256 verification against `META_APP_SECRET`, accepted by the running Uvicorn server with `HTTP 200 OK`, and durably persisted into the hosted PostgreSQL database (`wapsi_app` role).

All eight verification criteria specified for Phase 6 inbound processing have been verified via read-only inspection.

---

## 2. Inbound Webhook Authenticity & Cryptographic Verification

| Verification Dimension | Actual Provider Value | Configuration / Expected | Status |
| :--- | :--- | :--- | :--- |
| **Endpoint** | `POST /api/v1/webhooks/whatsapp` | `/api/v1/webhooks/whatsapp` | **PASS** |
| **Edge Request ID** | `airt_3LYx62PpKUE2zm4z5gfj1CZhJzT` | ngrok live edge log | **CONFIRMED** |
| **Remote Client IP** | `2a03:2880:10ff:e::` | Meta / Facebook Edge IPv6 | **AUTHENTIC META IP** |
| **User-Agent** | `facebookexternalua` | Meta Cloud Webhook Agent | **AUTHENTIC META UA** |
| **Received Signature** | `sha256=df7595e4684cbbc960d2010b17ec4d4e0ef037442fc47bc41491c5cc94cf90c8` | `X-Hub-Signature-256` header | **AUTHENTIC** |
| **Calculated HMAC-SHA256**| `sha256=df7595e4684cbbc960d2010b17ec4d4e0ef037442fc47bc41491c5cc94cf90c8` | `hmac.new(META_APP_SECRET, body, sha256)` | **EXACT MATCH** |
| **Signature Comparison** | `hmac.compare_digest() == True` | Constant-time evaluation | **PASS (VERIFIED)** |
| **HTTP Response** | `HTTP 200 OK` (144 bytes) | Status acknowledgment | **PASS** |

### Verified Inbound Payload Excerpt
```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "969727602419694",
      "changes": [
        {
          "field": "messages",
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "15552148539",
              "phone_number_id": "1407090562487899"
            },
            "contacts": [
              {
                "profile": { "name": "Arpit Jham" },
                "wa_id": "916260055671",
                "user_id": "IN.1481829960534905"
              }
            ],
            "messages": [
              {
                "from": "916260055671",
                "from_user_id": "IN.1481829960534905",
                "id": "wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBMjIzMzZFRUQ4MjNCOUREM0FBODZFNENBNjkyMTUA",
                "timestamp": "1793644616",
                "text": { "body": "Test 2" },
                "type": "text"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

---

## 3. Account & Phone Resource Matching

- **WABA ID in Payload:** `969727602419694`
- **WABA ID in `.env` (`WHATSAPP_BUSINESS_ACCOUNT_ID`):** `969727602419694`
- **Match Status:** **EXACT MATCH**

- **Phone Number ID in Payload:** `1407090562487899`
- **Phone Number ID in `.env` (`WHATSAPP_PHONE_NUMBER_ID`):** `1407090562487899`
- **Match Status:** **EXACT MATCH**

---

## 4. Durable Persistence Inspection (Hosted PostgreSQL)

A read-only inspection was executed using the restricted application role `wapsi_app` with tenant session context `SET app.current_merchant_id = '04a2aaf8-8c8a-4d99-852c-cefc80e82019';`.

### 4.1 `webhook_inbox` Persistence & Deduplication
Two transactional records were identified in `webhook_inbox` representing the event ingestion and payload audit trail:

1. **Processing / Deduplication Record:**
   - **ID:** `588d7168-65d4-4374-a9cf-80b605bedf78`
   - **Merchant ID:** `04a2aaf8-8c8a-4d99-852c-cefc80e82019`
   - **Provider:** `whatsapp_meta`
   - **Environment:** `test`
   - **Event ID:** `inbound_wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBMjIzMzZFRUQ4MjNCOUREM0FBODZFNENBNjkyMTUA`
   - **Event Type:** `whatsapp.inbound_message`
   - **Signature Verified:** `True`
   - **Status:** `RECEIVED`
   - **Received At:** `2026-11-02 18:37:01.338536+00:00`
   - **Payload Sanitized:** `{"from": "916260055671", "message_id": "wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBMjIzMzZFRUQ4MjNCOUREM0FBODZFNENBNjkyMTUA"}`

2. **Full Raw Webhook Audit Record:**
   - **ID:** `8c60501d-2657-4a15-84a7-1b02647b1573`
   - **Merchant ID:** `04a2aaf8-8c8a-4d99-852c-cefc80e82019`
   - **Provider:** `whatsapp_meta`
   - **Environment:** `test`
   - **Event ID:** `whatsapp_meta_5767f535bd70ac7c9a306e077ab38ed4_wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBMjIzMzZFRUQ4MjNCOUREM0FBOD`
   - **Event Type:** `inbound_message`
   - **Payment / Target ID:** `wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBMjIzMzZFRUQ4MjNCOUREM0FBODZFNENBNjkyMTUA`
   - **Signature:** `sha256=df7595e4684cbbc960d2010b17ec4d4e0ef037442fc47bc41491c5cc94cf90c8`
   - **Signature Verified:** `True`
   - **Status:** `RECEIVED`
   - **Received At:** `2026-11-02 18:37:03.752709+00:00`
   - **Payload Sanitized:** Complete sanitized Meta payload containing `"Test 2"`, sender MSISDN, WABA ID, and Phone Number ID.

### 4.2 `customer_interactions` Persistence
A dedicated record in `customer_interactions` was queried:
- **Phone (Masked):** `9162****71`
- **`last_interaction_at`:** `2026-11-02 18:36:56+00:00` (`2026-11-03 00:06:56 IST`)
- **Row Count:** Exactly **1 row** exists for this customer.
- **Deduplication:** When Meta retried transmission (`airt_3LYx62PpKUE2zm4z5gfj1CZhJzT`), `inbox.check_or_record()` identified the existing event ID and flagged `DUPLICATE_IGNORED` (`messages_duplicate: 1`). No redundant rows or duplicate side-effects were created.

---

## 5. Timestamp Preservation & 24-Hour Session Window

### 5.1 Original Timestamp Fidelity
- **Meta Provider Timestamp in Payload:** `"1793644616"` (Unix epoch seconds)
- **Database Timestamp (`customer_interactions.last_interaction_at`):**  
  `2026-11-02 18:36:56+00:00` (UTC)  
  `2026-11-03 00:06:56+05:30` (IST)
- **Fidelity:** Exact mathematical match down to the second ($1793644616 \text{ s} \equiv \text{2026-11-02 18:36:56 UTC}$).

### 5.2 24-Hour Customer-Service Window Calculation
Under Meta WhatsApp Cloud API rules, customer-initiated messages open a 24-hour service window:

$$\text{Window Start} = 1793644616 \quad (\text{2026-11-02 18:36:56 UTC} \,/\, \text{2026-11-03 00:06:56 IST})$$

$$\text{Window Expiry} = 1793644616 + 86400 = 1793731016 \quad (\text{2026-11-03 18:36:56 UTC} \,/\, \text{2026-11-04 00:06:56 IST})$$

### 5.3 Local Policy Engine Evaluation
Querying `PersistentOptOutStore` via the live PostgreSQL database manager confirmed:
- `is_opted_out("+91 62600 55671")`: **`False`**
- `is_within_24h_window("+91 62600 55671")`: **`True`**
- Both Meta Cloud infrastructure and WAPSI's local policy engine now recognize that an active 24-hour customer service window is open.

---

## 6. Durable Outbox Authorization & Isolation Safety Audit

The existing recovery job created during Stage 2 was re-audited to verify strict isolation and human approval gating:

| Outbox Job Attribute | Verified Database Value | Safety Requirement | Status |
| :--- | :--- | :--- | :--- |
| **Job ID** | `5a6587ab-2601-4017-b396-48e3d2fc2fda` | Target sandbox job | **MATCH** |
| **Case ID** | `wapsi_case_phase6_stage2_001` | Sandbox Case 001 | **MATCH** |
| **Merchant ID** | `04a2aaf8-8c8a-4d99-852c-cefc80e82019` | Sandbox tenant | **MATCH** |
| **Channel** | `whatsapp` | WhatsApp outbound | **MATCH** |
| **Action** | `WHATSAPP_ONE_CLICK_LINK` | Razorpay payment recovery | **MATCH** |
| **Recipient (Masked)** | `+91****5671` | Authorized test recipient | **MATCH** |
| **Status** | `PENDING_APPROVAL` | Must NOT be queued or claimed | **PASS (FROZEN)** |
| **`requires_operator_approval`**| `True` | Strict human review gate | **PASS (ENFORCED)**|
| **`approved_by_operator_id`** | `None` (NULL) | No approval granted | **PASS (UNAPPROVED)**|
| **`approved_at`** | `None` (NULL) | No approval timestamp | **PASS** |
| **`worker_id`** | `None` (NULL) | Unclaimed by any worker | **PASS (UNCLAIMED)** |
| **`lease_expires_at`** | `None` (NULL) | No worker lease active | **PASS** |
| **Retry Count** | `0` (Max: 3) | Zero dispatch attempts | **PASS** |
| **Associated Payment Link** | `plink_TvKucM1yXJQAZA` | Amount: INR 10.00, unpaid | **PASS** |

---

## 7. Verification Checklist Summary

| # | User Verification Item | Observed Evidence | Verdict |
| :-: | :--- | :--- | :-: |
| **1** | Valid `X-Hub-Signature-256` authentication | Constant-time HMAC match (`df7595e4...`), HTTP 200 returned | **PASS** |
| **2** | WABA and Phone Number ID match | `969727602419694` and `1407090562487899` exact match | **PASS** |
| **3** | Message persisted in `webhook_inbox` | 2 records persisted in PostgreSQL (`588d7168...` & `8c60501d...`) | **PASS** |
| **4** | Customer interaction in `customer_interactions` | 1 record persisted (`9162****71`, `2026-11-02 18:36:56+00:00`) | **PASS** |
| **5** | Exactly one logical message record exists | Exactly 1 interaction row; deduplication verified on retry | **PASS** |
| **6** | Original Meta timestamp preserved | Unix `1793644616` preserved as `2026-11-02 18:36:56 UTC` | **PASS** |
| **7** | 24-hour session window calculated correctly | Start: `1793644616`, Expiry: `1793731016`. Window active: `True` | **PASS** |
| **8** | Outbox job remains `PENDING_APPROVAL` and unclaimed | Status: `PENDING_APPROVAL`, approver: NULL, worker: NULL | **PASS** |

---

## 8. Conclusion

The inbound WhatsApp verification for **"Test 2"** (`wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBMjIzMzZFRUQ4MjNCOUREM0FBODZFNENBNjkyMTUA`) has completely succeeded across all 8 checkpoints with zero errors, zero side-effects, and zero bypass of human review.
