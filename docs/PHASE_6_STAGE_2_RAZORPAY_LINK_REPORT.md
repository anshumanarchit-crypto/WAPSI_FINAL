# WAPSI — Phase 6 Stage 2: External Provider Integration Report

**Date:** November 2, 2026  
**Execution Timestamp:** 2026-11-02T19:49:54+05:30 (14:19:54 UTC)  
**Target Environment:** Development Sandbox (`filofxijqmgluuulivxb`, `WAPSI-DEV-MUMBAI`, Supabase PostgreSQL 17)  
**Execution Script:** `scripts/execute_phase6_stage_2.py`  
**Deployment Boundary:** `ADVISORY_HUMAN_REVIEW` (Preserved)  
**Provider Mode:** Razorpay Test Mode (`rzp_test_...`) & Meta WhatsApp Cloud API (Test Recipient)  

---

## Executive Summary & Stage 2 Verdicts

Phase 6 Stage 2 has completed with 100% adherence to all non-negotiable safety constraints.

An actual, genuine Razorpay Test Mode Payment Link was created on the live Razorpay API without using mocks. The provider-generated Payment Link ID and metadata were persisted to the database and mapped to internal case tracking. The WhatsApp message payload was prepared and staged in the durable outbox under `ADVISORY_HUMAN_REVIEW` mode.

In strict compliance with the Stage 2 gate, **ZERO WhatsApp messages were dispatched**, **ZERO automated SMS/email notifications were triggered by Razorpay**, and **ZERO payments were executed**.

| Dimension | Result | Evidence / Operational Details |
| :--- | :---: | :--- |
| **Safety Preflight Checks** | **PASS** | Mode is `test`, Key ID prefix `rzp_test_`, public tunnel reachable, WhatsApp token valid (`GREEN`). |
| **Actual Razorpay API Call** | **PASS** | HTTP request completed against `https://api.razorpay.com/v1/payment_links`. |
| **Payment Link ID** | **VERIFIED** | `plink_TvKucM1yXJQAZA` (Status: `created`). |
| **Test Amount & Currency** | **VERIFIED** | INR 10.00 (`1000` paise), Currency: `INR`. |
| **Automated Notifications** | **DISABLED** | Razorpay `notify`: `{"sms": false, "email": false, "whatsapp": false}`, `reminder_enable: false`. |
| **WhatsApp Dispatch** | **HELD** | Staged payload prepared; held pending operator approval (`message_dispatched: false`). |
| **Database Persistence** | **PASS** | Case mapping registered; Outbox Job `5a6587ab-2601-4017-b396-48e3d2fc2fda` enqueued in PostgreSQL. |
| **Idempotency Safeguard** | **VERIFIED** | Reference ID `ref_wapsi_p6_s2_001` checked before creation to prevent duplicate links. |

---

## 1. Preflight Results

Prior to issuing any external request, the complete preflight suite was executed:

| Check | Expected | Observed | Verdict |
| :--- | :--- | :--- | :---: |
| **Razorpay Mode** | `test` | `test` | **PASS** |
| **Razorpay Key ID Prefix** | Starts with `rzp_test_` | `rzp_test_...bdqI` | **PASS** |
| **Environment Boundary** | `development` (Non-production) | `development` | **PASS** |
| **Meta WhatsApp Access Token** | Active, valid Graph API session | HTTP 200, Verified Name: True, Quality: `GREEN` | **PASS** |
| **Test Recipient Phone** | Populated & Authorized | `+91****5671` | **PASS** |
| **Public Base URL** | Reachable HTTPS endpoint | `https://crablike-outlook-pulmonary.ngrok-free.dev` (Active ngrok tunnel) | **PASS** |
| **Governance Boundary** | `ADVISORY_HUMAN_REVIEW` | Active | **PASS** |

---

## 2. Actual External Razorpay Request & Response

A controlled payment link request was issued to the live Razorpay Test Mode API endpoint:

- **HTTP Method & Path:** `POST https://api.razorpay.com/v1/payment_links`
- **Authentication Scheme:** HTTP Basic Auth (`rzp_test_...`)
- **Request Payload Parameters:**
  - `amount`: `1000` (paise)
  - `currency`: `"INR"`
  - `description`: `"WAPSI Sandbox Test Recovery Link (Phase 6 Stage 2)"`
  - `reference_id`: `"ref_wapsi_p6_s2_001"`
  - `notify`: `{"sms": false, "email": false, "whatsapp": false}`
  - `reminder_enable`: `false`
  - `notes`: `{"case_id": "wapsi_case_phase6_stage2_001", "reference_id": "ref_wapsi_p6_s2_001", "environment": "sandbox_test_mode", "phase": "phase6_stage2", "autonomous_engine": "WAPSI-v2.0"}`
  - `callback_url`: `"https://crablike-outlook-pulmonary.ngrok-free.dev/api/v1/recovery/callback"`
- **Response Status:** `HTTP 200 OK` (Live Razorpay API response)

---

## 3. Payment Link ID & Details

The live provider-generated response details:

- **Payment Link ID:** `plink_TvKucM1yXJQAZA`
- **Short URL:** `https://rzp.io/rzp/NCf137AL`
- **Provider Status:** `created`
- **Amount:** INR 10.00 (`1000` paise)
- **Currency:** `INR`
- **Reference ID:** `ref_wapsi_p6_s2_001`
- **Razorpay Notifications Sent:** Exactly 0 (SMS: False, Email: False, WhatsApp: False)
- **Automatic Reminders:** Disabled (`reminder_enable: false`)

---

## 4. Test Case & Mapping

The created payment link was bound to a controlled sandbox recovery case:

- **Internal Case ID:** `wapsi_case_phase6_stage2_001`
- **Merchant ID:** `04a2aaf8-8c8a-4d99-852c-cefc80e82019` (`Acme Global Technologies`)
- **Case Initial State:** `SCHEDULED`
- **Case-to-Provider Mapping:** Registered in `DurableWebhookEventProcessor`
  - Lookup by Payment Link ID `plink_TvKucM1yXJQAZA` -> `wapsi_case_phase6_stage2_001`
  - Lookup by Customer Phone `+91****5671` -> `wapsi_case_phase6_stage2_001`

---

## 5. WhatsApp Dispatch Preparation (Held Pending Approval)

The WhatsApp message was prepared but strictly withheld from transmission:

- **Target Recipient:** `+91****5671` (Masked). Digit length: 12 (E.164 without leading `+`).
- **Persistent Opt-Out Status:** Checked against `PersistentOptOutStore`: `is_opted_out = False`.
- **Model Readiness Status:** `BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS`
- **Deployment Mode:** `ADVISORY_HUMAN_REVIEW`
- **Prepared Message Body:**
  ```text
  WAPSI SANDBOX TEST: Your payment link for INR 10.00 is ready: https://rzp.io/rzp/NCf137AL. (This is an automated test-mode sandbox simulation. Do NOT make a real payment. Reply STOP to opt out.)
  ```
- **Dispatch Gate Status:** `HELD_PENDING_OPERATOR_APPROVAL`
- **Actual Message Dispatched:** **FALSE** (Zero requests sent to Meta Graph API messages endpoint).

---

## 6. Database Persistence & Outbox Evidence

All state was persisted to the hosted Supabase PostgreSQL database using the restricted `wapsi_app` role:

- **Outbox Job ID:** `5a6587ab-2601-4017-b396-48e3d2fc2fda`
- **Outbox Table:** `public.recovery_outbox`
- **Status:** `QUEUED`
- **Channel:** `whatsapp`
- **Idempotency Key:** `idemp_p6_s2_plink_TvKucM1yXJQAZA`
- **Decision Snapshot Hash:** `0329d2e8f5b5d56c65c0b678382ec1527fd0e8adea90e77d5d3e3f3c70520ff7`

---

## 7. Confirmation of Safety Invariants

1. **Zero Automated Notifications:** Confirmed from Razorpay API response that `notify.sms == False`, `notify.email == False`, and `notify.whatsapp == False`.
2. **Zero WhatsApp Messages Dispatched:** Confirmed that `WhatsAppClient.send_text_message()` or `send_template_message()` was NOT called.
3. **Zero Real Customer Contact:** Only the designated `TEST_RECIPIENT_PHONE` was referenced in the prepared payload.
4. **Zero Payments Executed:** Payment Link remains in `created` (unpaid) state.
5. **No Duplicate Links Created:** Re-execution safely detected existing link `ref_wapsi_p6_s2_001` and returned the existing entity without duplicates.

---

## 8. Failures, Blockers, and Next Steps

- **Known Blockers:** None.
- **Current Gate State:** **STOPPED**. Execution is halted per protocol.
- **Next Required Step:** Operator reviews the generated Payment Link (`https://rzp.io/rzp/NCf137AL`) and explicitly authorizes proceeding to Stage 3 (Controlled WhatsApp test dispatch).

