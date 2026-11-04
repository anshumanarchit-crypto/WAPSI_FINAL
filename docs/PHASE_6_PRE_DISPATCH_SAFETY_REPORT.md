# WAPSI — Phase 6 Pre-Dispatch Safety Verification Report

**Date:** November 2, 2026  
**Execution Timestamp:** 2026-11-02T19:59:21+05:30 (14:29:21 UTC)  
**Target Environment:** Development Sandbox (`filofxijqmgluuulivxb`, `WAPSI-DEV-MUMBAI`, Supabase PostgreSQL 17)  
**Execution Script:** `scripts/verify_pre_dispatch_safety.py`  
**Safety Protocol:** Strictly Read-Only Audit (Zero mutations, zero message sends, zero worker runs)  
**Final Audit Verdict:** **BLOCKED** (Two gating conditions identified)

---

## Executive Summary & Audit Verdicts

A read-only pre-dispatch safety audit was conducted prior to any potential external WhatsApp message transmission. The audit verified the live Razorpay Test Mode Payment Link, inspected the durable outbox state in PostgreSQL, evaluated Meta Cloud API recipient and session window compliance, and reviewed the staged message text.

The final safety verdict is **BLOCKED**. Per safety directives, testing is halted and no messages may be dispatched until the operator reviews the findings and resolves the gating blockers.

| Audit Check | Verdict | Core Finding / Operational Status |
| :--- | :---: | :--- |
| **1. Razorpay Link Verification** | **PASS** | `plink_TvKucM1yXJQAZA` verified on live API. Amount: 1000 paise (INR 10.00). Status: `created` (unpaid). All auto-notifications and reminders disabled. |
| **2. Database Mapping Verification** | **PASS** | Bound to `wapsi_case_phase6_stage2_001`. Case mapping resolves by link ID and customer phone. Exactly 1 outbox record exists (no duplicates). |
| **3. Outbox Authorization State** | **BLOCKED** | Job `5a6587ab-2601-4017-b396-48e3d2fc2fda` is currently stored with `status = 'QUEUED'` and `next_attempt_at` in the past. |
| **4. Background-Worker Dispatch Safety** | **BLOCKED** | Because `status = 'QUEUED'`, an active background worker running `claim_recovery_outbox_jobs()` could claim and dispatch this job without waiting for explicit operator sign-off. |
| **5. WhatsApp Recipient Verification** | **PASS** | Masked recipient `+91****5671` matches `TEST_RECIPIENT_PHONE`. Opt-out status is `False`. Sender `+1 555-214-8539` verified (`GREEN`). |
| **6. 24h Window / Template Status** | **BLOCKED** | No inbound message recorded within last 24h (session window closed), and no custom payment recovery template is registered on WABA. |
| **7. Message Content & Disclosure** | **PASS** | Clear sandbox disclosure ("WAPSI SANDBOX TEST"), correct INR 10.00 amount, explicit test warning, and STOP instructions. |
| **FINAL OVERALL VERDICT** | **BLOCKED** | Execution must halt. Await operator instructions. |

---

## 1. Razorpay Payment Link Verification

Direct read-only inspection against the live Razorpay Test Mode API (`GET https://api.razorpay.com/v1/payment_links/plink_TvKucM1yXJQAZA`) confirmed:

- **Payment Link ID:** `plink_TvKucM1yXJQAZA` (Matches target).
- **Reference ID:** `ref_wapsi_p6_s2_001` (Matches target).
- **Amount:** `1000` paise (Exactly INR 10.00).
- **Amount Paid:** `0` paise (Unpaid).
- **Currency:** `INR`.
- **Status:** `created` (Active, unpaid, uncancelled).
- **Short URL:** `https://rzp.io/rzp/NCf137AL` (Verified Razorpay domain).
- **Automated SMS Notification:** `false` (Disabled).
- **Automated Email Notification:** `false` (Disabled).
- **Automated WhatsApp Notification:** `false` (Disabled).
- **Automatic Reminders:** `false` (Disabled).
- **Creation Timestamp:** `1793628944` (Unix).
- **Order ID:** `order_TvL3FPkftboTks`.

Zero new payment links were created during this verification.

---

## 2. Database Mapping & Outbox Authorization State

Inspection of `public.recovery_outbox` in hosted Supabase PostgreSQL confirmed:

- **Target Job ID:** `5a6587ab-2601-4017-b396-48e3d2fc2fda`.
- **Associated Case ID:** `wapsi_case_phase6_stage2_001`.
- **Merchant ID:** `04a2aaf8-8c8a-4d99-852c-cefc80e82019` (`Acme Global Technologies`).
- **Channel:** `whatsapp`.
- **Masked Recipient:** `+91****5671`.
- **Provider Message ID (`wamid`):** None (No message dispatched).
- **Worker Lease (`worker_id`):** None (No worker has claimed the job).
- **Duplicate Check:** Exactly 1 record exists for `case_id = 'wapsi_case_phase6_stage2_001'`.

---

## 3. Background-Worker Dispatch Safety Audit

### The Identified Safety Gap

Inspection of the SQL claim logic in Migration 7 (`public.claim_recovery_outbox_jobs`):
```sql
SELECT o.id
FROM public.recovery_outbox o
WHERE (
    (o.status IN ('QUEUED', 'RETRY') AND o.next_attempt_at <= v_now)
    OR
    (o.status = 'SENDING' AND o.lease_expires_at IS NOT NULL AND o.lease_expires_at < v_now)
)
ORDER BY o.next_attempt_at ASC
FOR UPDATE OF o SKIP LOCKED;
```

- **Observed Database State:** The outbox job is stored with `status = 'QUEUED'` and `next_attempt_at = 2026-11-02 14:19:59.463385+00:00` (in the past).
- **Vulnerability:** If the background recovery worker process is started, it will immediately lease and attempt to dispatch this job because it matches `o.status IN ('QUEUED', 'RETRY') AND o.next_attempt_at <= v_now`.
- **Production Safety Mandate:** Under `ADVISORY_HUMAN_REVIEW` mode, customer-facing actions must NOT be eligible for autonomous worker claiming until an operator explicitly transitions the record from `PENDING_APPROVAL` to `QUEUED`.
- **Action Taken:** Per the explicit prompt directive (*"If the job is currently eligible for automatic dispatch, mark the audit BLOCKED and report the finding. Do not silently mutate the job"*), the audit is marked **BLOCKED**. Zero database mutations were performed.

---

## 4. WhatsApp Recipient, WABA & Session Window Checks

Read-only inspection via Meta Graph API (`v26.0`) and database registries confirmed:

### Recipient & WABA Details
- **Configured Recipient:** `+91****5671` (E.164 digits: `916260055671`).
- **Persistent Opt-Out Check:** `opt_out_store.is_opted_out("+916260055671") == False` (Clear).
- **Test Sender Phone ID:** `1407090562487899`.
- **Sender Display Number:** `+1 555-214-8539` (Official Meta Sandbox test number).
- **Quality Rating:** `GREEN`.
- **Code Verification Status:** `VERIFIED`.

### Session Window vs. Approved Template Evaluation
Meta WhatsApp Cloud API enforces strict platform messaging policies:
1. **Freeform Session Messages:** Only permitted within 24 hours of an inbound message from the customer.
2. **Template Messages:** Required to initiate conversations outside the 24-hour service window.

- **Observed Inbound Timestamp:** `None` (No inbound customer messages recorded in `webhook_inbox` or `opt_out_registry`).
- **24-Hour Customer Service Window:** **INACTIVE** (Closed).
- **Approved Custom Recovery Templates:** **NONE** registered on WABA (only standard built-in sandbox `hello_world` is present, which does not take dynamic payment link URLs).
- **Policy Verdict:** **BLOCKED**. Attempting to dispatch the prepared freeform message text without an active 24-hour window will result in an immediate Meta API rejection (`HTTP 400 - OAuthException Code 131047: Re-engagement message template required`).

---

## 5. Message Content & Disclosure Review

Inspection of the staged payload in the outbox job confirmed:

```text
WAPSI SANDBOX TEST: Your payment link for INR 10.00 is ready: https://rzp.io/rzp/NCf137AL. (This is an automated test-mode sandbox simulation. Do NOT make a real payment. Reply STOP to opt out.)
```

- **Sandbox Identification:** Clearly stated in header ("WAPSI SANDBOX TEST").
- **Payment Amount:** Accurately states "INR 10.00".
- **Payment Link URL:** Contains valid live link `https://rzp.io/rzp/NCf137AL`.
- **Explicit Test Warning:** "This is an automated test-mode sandbox simulation. Do NOT make a real payment."
- **Compliance Instructions:** "Reply STOP to opt out."
- **PII Exposure:** Zero real customer names or payment credentials present.
- **Accuracy:** Does not make false claims that payment has already succeeded.

---

## 6. Pre-Dispatch Blockers & Resolution Requirements

To safely proceed to controlled dispatch:

1. **Resolve Outbox Worker Claim Eligibility (Blocker 1):**
   - The database status of the job should explicitly reflect operator authorization state (e.g. `PENDING_APPROVAL` until approved by the operator, at which point it is marked `APPROVED` / `QUEUED`).
2. **Resolve WhatsApp 24-Hour Service Window (Blocker 2):**
   - Because no custom recovery template is registered in the sandbox WABA, Meta requires an open 24-hour customer service window for free-form text messages.
   - **Operator Action Needed:** The authorized test recipient (`+91****5671`) must send a quick inbound message (e.g. `"Hi"` or `"Hello"`) from WhatsApp to the test sender (`+1 555-214-8539`).
   - This opens the official Meta 24-hour service window and allows the sandbox freeform recovery link to be received.

---

## 7. Safety Status

**EXECUTION IS STOPPED.**
Zero WhatsApp messages were dispatched. No worker was executed. Awaiting operator instruction.

