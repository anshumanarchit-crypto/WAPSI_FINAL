# WAPSI — PHASE 7 READINESS HANDOFF DOCUMENT
**Transitioning Autonomous Payment Recovery to Live Production & Enterprise Scale**

- **Date / Timestamp:** 2026-11-03T06:33:00Z / 2026-11-03 12:03:00 IST
- **Target Audience:** Phase 7 Lead Engineers, Platform SREs, and Security Operations
- **Source Artifact:** Phase 6 Master Finalization (`PHASE_6_FINAL_CLOSURE_AND_RELEASE_AUDIT.md`)
- **Handed-Off Core Test Suite:** 163 Tests Passed (100% Pass Rate)

---

## 1. System Overview & Delivered Capabilities

Phase 6 has established a fully functional, mathematically sound, cryptographically governed, and load-tested foundation for WAPSI (WhatsApp Autonomous Payment Stream Intelligence). All core recovery mechanisms have transitioned from simulation to live execution:

1. **Recovery Workflow Engine (`wapsi/recovery/`):**
   - Formal deterministic state machine (`wapsi/recovery/state_machine.py`) enforcing acyclic progression to terminal `RECOVERED` or `CANCELLED`.
   - Eligibility evaluation engine (`wapsi/recovery/eligibility.py`) incorporating failure soft/hard taxonomy and risk scoring.
   - Intelligent scheduling (`wapsi/recovery/scheduler.py`) adhering to recipient communication windows.
   - Financial reconciliation engine (`wapsi/recovery/reconciliation.py`) using integer paise accounting.

2. **Durable Multi-Tenant Outbox (`wapsi/recovery/outbox.py`, `wapsi/db/`):**
   - Backed by PostgreSQL with Row-Level Security (RLS) and Migration 8/9/10 stored procedures.
   - Distributed worker lease locking using `SELECT ... FOR UPDATE SKIP LOCKED`.
   - Automatic reclamation of expired leases from crashed workers.
   - Fail-closed tenant context validation via `app.current_merchant_id`.

3. **Human-in-the-Loop Governance (`wapsi/recovery/outbox.py`, `wapsi/api/`):**
   - Mandatory operator approval for customer-contacting actions (`requires_operator_approval = TRUE`).
   - Cryptographic approval hash calculation binding operator attribution to message payload and recipient phone.
   - Pre-dispatch verification preventing execution if payloads have been modified.

4. **Multi-Channel Provider Integrations (`wapsi/integrations/`):**
   - Meta WhatsApp Cloud API client (`WhatsAppClient`) supporting Graph API v26.0, direct payload mode, and automatic phone sanitization.
   - Razorpay payment link manager (`RazorpayPaymentLinkManager`) with idempotent link reuse.
   - Durable webhook inbox (`DurableWebhookInbox`) with raw-bytes HMAC-SHA256 signature verification and composite deduplication.

5. **Frontend API & Compatibility Adapter (`wapsi/api/frontend_adapter.py`):**
   - Full compatibility with the WAPSI React dashboard (`/health`, `/recovery/cases`, `/recovery/cases/{id}/approve`, `/decide`, `/integrations/status`).

---

## 2. Phase 7 Production Cutover Checklist

To transition from the current sandbox/development stage into live production, execute the following operational steps:

### A. Environment Configuration (`.env`)
```bash
# 1. Environment & Mode
WAPSI_ENV=production
RAZORPAY_MODE=live
WHATSAPP_AUTH_MODE=system_user

# 2. Production Meta WhatsApp Credentials
WHATSAPP_ACCESS_TOKEN=<PERMANENT_SYSTEM_USER_ACCESS_TOKEN>
WHATSAPP_PHONE_NUMBER_ID=<PRODUCTION_PHONE_NUMBER_ID>
WHATSAPP_BUSINESS_ACCOUNT_ID=<PRODUCTION_WABA_ID>
WHATSAPP_API_VERSION=v26.0
META_APP_SECRET=<PRODUCTION_META_APP_SECRET>
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<PRODUCTION_VERIFY_TOKEN>

# 3. Production Razorpay Credentials
RAZORPAY_KEY_ID=<PRODUCTION_KEY_ID>
RAZORPAY_KEY_SECRET=<PRODUCTION_KEY_SECRET>
RAZORPAY_WEBHOOK_SECRET=<PRODUCTION_WEBHOOK_SECRET>

# 4. Host & Domain Configuration
WAPSI_PUBLIC_BASE_URL=https://api.yourdomain.com
```

### B. Production Cutover Sequence
1. **Meta Business Manager Setup:**
   - Ensure the System User has `whatsapp_business_messaging` and `whatsapp_business_management` permissions assigned to the Production WABA.
   - Register and pre-approve production message templates in Meta WhatsApp Manager if outbound contact initiates outside the 24-hour service window.
2. **Webhook Endpoint Registration:**
   - Configure Meta App Webhook URL: `https://api.yourdomain.com/api/v1/webhooks/whatsapp`.
   - Subscribe to `messages` field.
   - Configure Razorpay Dashboard Webhook URL: `https://api.yourdomain.com/api/v1/webhooks/razorpay`.
   - Subscribe to `payment.captured`, `payment.failed`, `payment_link.paid`, `payment_link.cancelled`, `payment_link.expired`.
3. **Database Migration Status:**
   - Verify all migrations (001 through 010) are applied to the production PostgreSQL cluster.
   - Ensure `app.current_merchant_id` session setting permissions are granted to the application database user.
4. **Worker Daemon Deployment:**
   - Deploy `RecoveryBackgroundWorker` as a monitored systemd service, Kubernetes deployment, or Celery task.
   - Recommended scale: 2 to 4 worker replicas per availability zone. Concurrency lease locking (`SKIP LOCKED`) guarantees zero duplicate dispatch across replicas.

---

## 3. Operational Invariants & Safeguards

The Phase 7 team must maintain these core architectural invariants:
- **Never bypass `compute_approval_hash`:** Outbox jobs marked for operator approval must never be claimed or dispatched if the approval hash is missing or mismatched.
- **Never mutate terminal states:** Once a recovery case reaches `RECOVERED`, it is authoritative. Delayed failure callbacks must be recorded in the audit timeline but must never revert `RECOVERED`.
- **Integer Paise Accounting:** All financial logic must operate strictly on integer paise (e.g. `1000` paise = `INR 10.00`). Never introduce floating-point arithmetic for amounts.
- **Fail-Closed Multi-Tenancy:** Always execute database queries within `tenant_session_scope(merchant_uuid)` to enforce PostgreSQL tenant context.

---

## 4. Phase 7 Architecture & Verification Sign-Off

All components, test suites, reports, and live evidence from Phase 6 are sealed and archived. The codebase is clean, robust, and fully prepared for live deployment.

**Phase 6 is COMPLETE. The system is ready for Phase 7 execution.**

