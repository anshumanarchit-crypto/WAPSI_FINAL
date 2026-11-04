# WAPSI Phase 4 — WhatsApp Inbound Webhook Integration Report

**Date:** 2026-11-02  
**Target Project:** WAPSI-DEV-MUMBAI (`filofxijqmgluuulivxb`)  
**Branch:** `phase4/whatsapp-inbound-integration`  
**Status:** COMPLETE & VERIFIED (104/104 Core Tests Passing)

---

## Executive Summary

Phase 4 bridges the FastAPI WhatsApp Cloud API webhook routes (`GET` and `POST /api/v1/webhooks/whatsapp`) with the durable Phase 3 webhook infrastructure (`DurableWebhookEventProcessor`, `DurableWebhookInbox`, `PersistentOptOutStore`, `DurableOutboxStore`, and `RecoveryTimelineStore`).

All 9 required verification scenarios have been implemented and verified with zero regression to Phase 1, Phase 2, and Phase 3 components.

---

## 1. Files Changed & Implemented

| File | Change Summary |
|------|----------------|
| `wapsi/recovery/webhook_processor.py` | Added application singleton accessors (`get_durable_webhook_processor`, `set_durable_webhook_processor`), dynamic default merchant resolution under Supabase RLS, `register_case_mapping()` accepting string statuses, delivery progression hierarchy guard, and memory synchronization with orchestrator cases on opt-out. |
| `wapsi/integrations/whatsapp/opt_out.py` | Bridged `OptOutManager` (`is_opted_out`, `record_opt_out`, `revoke_opt_out`, `record_customer_interaction`, `is_within_24h_window`) to query and update `PersistentOptOutStore` for global singleton while supporting standalone test instances. |
| `wapsi/recovery/opt_out_store.py` | Added `set_persistent_opt_out_store()` and `clear()` method for isolated SQLite testing environments. |
| `wapsi/recovery/state_machine.py` | Added `DISPATCHING` and `DISPATCHED` transitions from `PENDING` to `_ALLOWED_TRANSITIONS`. |
| `wapsi/integrations/whatsapp/webhook.py` | Removed in-memory mutation side-effects from `parse_event()`, making it pure deserialization. Added `"mixed"` event type support for payloads containing both `statuses` and `messages`. Reinforced `WhatsAppAuthError` on missing/bad signatures. |
| `wapsi/integrations/orchestration/recovery_orchestrator.py` | Added `get_durable_webhook_processor().register_case_mapping()` on `initiate_recovery()`. In `handle_whatsapp_delivery_event()`, added delivery hierarchy guard to prevent late status regressions. |
| `wapsi/recovery/engine.py` | Accepted `webhook_processor` parameter, defaulting to `get_durable_webhook_processor()`. |
| `wapsi/api/app.py` | Wired `handle_whatsapp_webhook` to durable processor. Added fail-closed check for missing `META_APP_SECRET` in production (HTTP 500), returned HTTP 401 on bad/missing signature, returned HTTP 500 on database failure, returned detailed duplicate counts. Wired case mapping registration to `/api/v1/recovery/payment-link`. |
| `wapsi/db/service.py` | Fixed `UnboundLocalError` in `persist_causal_decision()`. |
| `tests/test_phase4_whatsapp_webhook_integration.py` | Comprehensive test suite covering all 9 required verification scenarios (13/13 passing). |
| `tests/test_phase3_razorpay_webhook_compatibility.py` | Fixed `WapsiSettings` monkeypatch fixture and `RecoveryDispatchReceipt` constructor arguments (14/14 passing). |
| `tests/test_phase2_integrations.py` | Updated `test_inbound_opt_out_keyword_detection` to invoke processor, updated verify handshake to accept dev fallback, and isolated test phone opt-out (22/22 passing). |

---

## 2. Architecture & Design Decisions

### A. Pure Deserialization vs Authoritative Processing
Previously, `WhatsAppWebhookHandler.parse_event()` had mutation side effects: it directly invoked `opt_out_manager.record_customer_interaction()` and `opt_out_manager.record_opt_out()`.
- **Problem:** If parsing succeeded but request authentication or database transaction failed downstream, the in-memory opt-out state was already permanently altered.
- **Resolution:** `parse_event()` now only classifies `is_opt_out = PersistentOptOutStore.is_opt_out_text(body_text)` without side effects. Authoritative state mutation happens exclusively inside `DurableWebhookEventProcessor.process_inbound_customer_message()`.

### B. Unified Opt-Out Architecture
Rather than maintaining two disparate opt-out systems:
- `PersistentOptOutStore` remains the single source of truth (backed by PostgreSQL `customer_opt_outs` or SQLite `opt_out_registry`).
- `OptOutManager` global singleton bridges to `PersistentOptOutStore`, preserving 100% backward compatibility for all existing callers.

### C. Out-of-Order Delivery & Hierarchy Protection
1. **Never Downgrade RECOVERED:** If a payment capture event has already transitioned a case to `RECOVERED`, any subsequent WhatsApp `failed` callback logs a timeline event but preserves `RECOVERED`.
2. **Delivery Progression Hierarchy:** WhatsApp delivery events follow the hierarchy `PENDING/DISPATCHING(0) < DISPATCHED(1) < DELIVERED(2) < READ(3)`. Late status callbacks (e.g. `SENT` arriving after `DELIVERED` or `READ`) are logged and acknowledged without regressing case state.

### D. Mixed Webhook Payload Handling
Meta Graph API occasionally batches delivery status receipts and incoming customer messages within the same change entry.
- `event_type` is now classified as `"mixed"` if both arrays are populated.
- `handle_whatsapp_webhook` processes all delivery receipts AND all customer messages in a single webhook invocation without dropping either.

---

## 3. Verification & Test Results

### Phase 4 Test Suite (`tests/test_phase4_whatsapp_webhook_integration.py`)
All 9 verification scenarios passed:
1. `test_signature_verification_valid_signature`: Valid HMAC-SHA256 signature succeeds with HTTP 200.
2. `test_signature_verification_tampered_payload_rejected`: Tampered body rejected with HTTP 401.
3. `test_signature_verification_missing_signature_with_secret_rejected`: Missing signature header rejected with HTTP 401.
4. `test_signature_verification_production_missing_secret_fails_closed`: Production with unconfigured secret fails closed with HTTP 500.
5. `test_subscription_handshake_success`: Valid `hub.mode` and `hub.verify_token` returns `hub.challenge` HTTP 200.
6. `test_subscription_handshake_invalid_token`: Invalid verify token returns HTTP 403.
7. `test_inbound_opt_out_suppresses_case_and_cancels_outbox`: "STOP" keyword persists opt-out, cancels pending outbox jobs, and marks case `SUPPRESSED_OPT_OUT`.
8. `test_inbound_customer_interaction_updates_window_without_opt_out`: Freeform question activates 24h Meta customer service window without opt-out.
9. `test_inbound_message_deduplication`: Repeated `message_id` acknowledged as `DUPLICATE_IGNORED`.
10. `test_whatsapp_delivery_status_progression_and_deduplication`: Status progression (`sent` -> `delivered` -> `read`) and composite key deduplication verified.
11. `test_out_of_order_failure_never_downgrades_recovered_case`: Late `failed` event preserves authoritative `RECOVERED` state.
12. `test_mixed_webhook_payload_with_statuses_and_messages`: Mixed payload parsed and processed completely.
13. `test_database_error_fails_closed_with_http_500`: Database outage returns retryable HTTP 500 to Meta.

**Phase 4 Result:** `13 passed in 8.62s`

### Core Regression Test Suite Summary
```
tests/test_phase4_whatsapp_webhook_integration.py .................. [13 passed]
tests/test_phase3_razorpay_webhook_compatibility.py ................ [14 passed]
tests/test_phase3_recovery_workflow.py ............................. [22 passed]
tests/test_phase3_1_postgres_workflow.py ........................... [ 9 passed]
tests/test_phase3_final_closure_gate.py ............................ [13 passed]
tests/test_phase2_integrations.py .................................. [22 passed]
tests/test_phase1b_persistence.py .................................. [11 passed]
============================ 104 passed in 44.19s =============================
```

---

## 4. Security & Compliance Review

1. **HMAC-SHA256 Cryptographic Verification:** All WhatsApp webhook bodies are verified using constant-time `hmac.compare_digest` against `META_APP_SECRET`.
2. **Fail-Closed Production Posture:** When `WAPSI_ENV == "production"`, missing `META_APP_SECRET` immediately fails closed with HTTP 500.
3. **Restricted Privileges:** Database interactions execute under `wapsi_app` with zero `DELETE` privileges. Webhook deduplication respects Supabase Row Level Security via `tenant_session_scope`.
4. **Zero Financial Authority via Chat:** Inbound customer WhatsApp messages can only trigger opt-out suppression or interaction window updates. They can never authorize payment captured, refunds, or monetary state changes.
5. **No Secret Mutation:** `.env` and provider configuration remained intact throughout Phase 4.

---

## 5. Next Steps

With Phase 4 WhatsApp Inbound Webhook Integration completed and verified across 104/104 core tests:
- **Phase 4 Core Causal Learning:** Advance to genuine treatment effect estimation (T-Learner, X-Learner, DML/Causal Forest), conformal prediction coverage, and factual bandit feedback loops using the verified recovery data pipeline.

