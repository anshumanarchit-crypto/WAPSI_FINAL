# WAPSI PHASE 7 — RELEASE EVIDENCE INDEX

**Document ID**: `WAPSI-P7-RELEASE-EVIDENCE-INDEX-2026-11-03`  
**Execution Timestamp**: `2026-11-03T21:32:00+05:30` (IST) / `2026-11-03 16:02:00 UTC`  
**Environment**: `WAPSI_ENV=development`, `RAZORPAY_MODE=test`  
**Repository Paths**:
- Backend: `C:\Users\arpit\Desktop\Razorpay\Razorpay`
- Frontend: `C:\Users\arpit\Desktop\WAPSI-Buildathon`

---

## 1. Phase 7 Gate Reports Inventory

| Gate | Title | Document Path | Size (Bytes) | Date / Time | Primary Focus |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **Gate 1** | Historical Regression Restoration | `docs/PHASE_7_GATE_1_BASELINE_RESTORATION_REPORT.md` | 9,119 | 2026-11-03 13:27:22 | 163/163 historical baseline restored; `register_case_mapping` keyword argument alignment |
| **Gate 2** | Production Configuration & Security | `docs/PHASE_7_GATE_2_PRODUCTION_SECURITY_REPORT.md` | 17,206 | 2026-11-03 14:49:19 | Fail-closed production credential validation; Windows registry fallback blocked in prod |
| **Gate 3** | Meta Pre-Approved Template Messaging | `docs/PHASE_7_GATE_3_TEMPLATE_RECOVERY_REPORT.md` | 29,348 | 2026-11-03 15:53:21 | Meta Graph API v26.0 template validation, 24h window router, and fail-closed manual review |
| **Gate 4** | Background Worker Daemon & Concurrency | `docs/PHASE_7_GATE_4_WORKER_DAEMON_REPORT.md` | 29,426 | 2026-11-03 17:11:11 | Continuous daemon lifecycle, SIGTERM/SIGINT graceful shutdown, atomic heartbeat, lease sweep |
| **Gate 5** | Causal Observational Learning (LinUCB) | `docs/PHASE_7_GATE_5_CAUSAL_OBSERVATIONAL_FEEDBACK_REPORT.md` | 25,121 | 2026-11-03 19:31:36 | Propensity logging, LinUCB rank-1 online feedback, verified integer paise rewards, DML export |
| **Gate 6** | Complete Frontend Integration & E2E | `docs/PHASE_7_GATE_6_FRONTEND_INTEGRATION_REPORT.md` | 24,134 | 2026-11-03 21:00:16 | Live React UI binding to FastAPI, HITL approval modal, SHA-256 snapshot, Playwright testing |
| **Gate 7** | Final Engineering Release Audit | `docs/PHASE_7_FINAL_RELEASE_AUDIT.md` | ~25,000 | 2026-11-03 21:30:00 | Comprehensive release audit across all 7 gates; production readiness sign-off assessment |

---

## 2. Test Suite & Regression Verification Evidence

### 2.1 Unified Regression Suite (19 Test Files)

```powershell
.venv\Scripts\python -m pytest `
  tests/test_phase7_frontend_playwright_e2e.py `
  tests/test_phase7_causal_feedback.py `
  tests/test_phase7_worker_daemon.py `
  tests/test_phase7_template_dispatch.py `
  tests/test_phase7_production_readiness.py `
  tests/test_phase6_stage2c_operator_approval_preparation.py `
  tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py `
  tests/test_phase6_stage2d2_fail_closed_tenant_context.py `
  tests/test_phase6_stage2d_exact_job_isolation.py `
  tests/test_phase6_stage2e3_direct_payload.py `
  tests/test_phase6_stage3_recovery_lifecycle.py `
  tests/test_phase6_stage4_production_hardening.py `
  tests/test_frontend_adapter.py `
  tests/test_phase6_stage2b_sandbox_token_routing.py `
  tests/test_phase6_stage2a_authorization.py `
  tests/test_phase6_sandbox_execution.py `
  tests/test_phase6_webhook_authentication_and_ingestion.py `
  tests/test_phase3_recovery_workflow.py `
  tests/test_phase3_1_postgres_workflow.py -q
```

### 2.2 Suite Breakdown

| Suite # | Test File | Gate / Area | Collected | Passed | Failed | Skipped | Pass Rate |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | `tests/test_phase7_frontend_playwright_e2e.py` | Gate 6 | 45 | 45 | 0 | 0 | 100% |
| 2 | `tests/test_phase7_causal_feedback.py` | Gate 5 | 52 | 52 | 0 | 0 | 100% |
| 3 | `tests/test_phase7_worker_daemon.py` | Gate 4 | 40 | 39 | 0 | 1 | 100%* |
| 4 | `tests/test_phase7_template_dispatch.py` | Gate 3 | 36 | 36 | 0 | 0 | 100% |
| 5 | `tests/test_phase7_production_readiness.py` | Gate 2 | 19 | 19 | 0 | 0 | 100% |
| 6 | `tests/test_phase6_stage2c_operator_approval_preparation.py` | Gate 1 | 10 | 10 | 0 | 0 | 100% |
| 7 | `tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py` | Gate 1 | 9 | 9 | 0 | 0 | 100% |
| 8 | `tests/test_phase6_stage2d2_fail_closed_tenant_context.py` | Gate 1 | 11 | 11 | 0 | 0 | 100% |
| 9 | `tests/test_phase6_stage2d_exact_job_isolation.py` | Gate 1 | 9 | 9 | 0 | 0 | 100% |
| 10 | `tests/test_phase6_stage2e3_direct_payload.py` | Gate 1 | 22 | 22 | 0 | 0 | 100% |
| 11 | `tests/test_phase6_stage3_recovery_lifecycle.py` | Gate 1 | 12 | 12 | 0 | 0 | 100% |
| 12 | `tests/test_phase6_stage4_production_hardening.py` | Gate 1 | 8 | 8 | 0 | 0 | 100% |
| 13 | `tests/test_frontend_adapter.py` | Gate 1 | 8 | 8 | 0 | 0 | 100% |
| 14 | `tests/test_phase6_stage2b_sandbox_token_routing.py` | Gate 1 | 10 | 10 | 0 | 0 | 100% |
| 15 | `tests/test_phase6_stage2a_authorization.py` | Gate 1 | 10 | 10 | 0 | 0 | 100% |
| 16 | `tests/test_phase6_sandbox_execution.py` | Gate 1 | 11 | 11 | 0 | 0 | 100% |
| 17 | `tests/test_phase6_webhook_authentication_and_ingestion.py` | Gate 1 | 11 | 11 | 0 | 0 | 100% |
| 18 | `tests/test_phase3_recovery_workflow.py` | Gate 1 | 23 | 23 | 0 | 0 | 100% |
| 19 | `tests/test_phase3_1_postgres_workflow.py` | Gate 1 | 9 | 9 | 0 | 0 | 100% |
| **TOTAL** | **19 Test Files** | **Gates 1–6** | **355** | **354** | **0** | **1** | **100%** |

*\*Skipped test: `test_37_postgres_concurrency_skip_locked_isolated` skipped safely due to absence of local PostgreSQL cluster on port 5438. Zero synthetic rows written to hosted Supabase.*

---

## 3. Playwright Visual Screenshot Inventory

Located in `docs/screenshots/`:

| Filename | Dimensions | File Size | Description |
| :--- | :---: | :---: | :--- |
| `overview_desktop.png` | 1440x900 | 417,090 bytes | Desktop Executive Overview with live PostgreSQL & TEE header badges |
| `recovery_center.png` | 1440x900 | 285,002 bytes | Recovery Center case table with 15 scored deterministic seed cases |
| `operator_approval_modal.png` | 1440x900 | 243,583 bytes | HITL Operator Approval Modal with policy guardrails & SHA-256 hash |
| `case_authorized_state.png` | 1440x900 | 284,257 bytes | Recovery table verifying case mutation to `APPROVED` |
| `case_detail_drawer.png` | 1440x900 | 360,646 bytes | Detail drawer with SHAP feature weights and historical precedents |
| `ai_decisions.png` | 1440x900 | 429,233 bytes | CATE uplift estimates and LinUCB arm exploration distributions |
| `observational_learning.png` | 1440x900 | 314,456 bytes | Gate 5 observational diagnostics and DML retraining pipeline |
| `observational_export.png` | 1440x900 | 259,665 bytes | Date-filtered streaming JSONL dataset export interface |
| `worker_operations.png` | 1440x900 | 334,932 bytes | Gate 4 daemon status, active leases, and outbox partition metrics |
| `settings_integrations.png` | 1440x900 | 215,231 | Real-time status for Razorpay, WhatsApp Cloud API, and Postgres |
| `tablet_responsive.png` | 768x1024 | 285,036 bytes | Tablet portrait layout with responsive navigation and metric cards |
| `mobile_responsive.png` | 375x812 | 144,402 bytes | Mobile viewport layout with single-column responsive stacking |
| `gate6_initial_overview.png` | 1440x900 | 488,483 bytes | Pre-audit baseline screenshot for visual comparison |

---

## 4. Source Code Artifacts Created & Modified in Phase 7

### 4.1 Backend (`C:\Users\arpit\Desktop\Razorpay\Razorpay`)
- `wapsi/core/config.py`: Hardened `WapsiSettings` with fail-closed production validation and secret masking.
- `wapsi/integrations/whatsapp/client.py`: Implemented `send_template_message` with Graph API v26.0 schema validation.
- `wapsi/recovery/worker_daemon.py`: Implemented `RecoveryWorkerDaemon`, `WorkerHeartbeat`, and SIGTERM/SIGINT handlers.
- `wapsi/recovery/observational_logger.py`: Implemented `ObservationalLogger` and `DecisionObservationRecord`.
- `wapsi/bandit/feedback.py`: Implemented `BanditClosedLoopFeedback` with Sherman-Morrison rank-1 updates.
- `wapsi/api/app.py`: Integrated worker health and observational export/metrics endpoints.
- `wapsi/api/frontend_adapter.py`: Added SHA-256 snapshot hashing and case detail drawer adapters.
- `wapsi/db/session.py`: Implemented `_shared_engines` caching to prevent Supabase connection pool exhaustion.
- `tests/test_phase7_production_readiness.py`: 19 security tests.
- `tests/test_phase7_template_dispatch.py`: 36 template dispatch tests.
- `tests/test_phase7_worker_daemon.py`: 40 worker daemon concurrency tests.
- `tests/test_phase7_causal_feedback.py`: 52 causal observational learning tests.
- `tests/test_phase7_frontend_playwright_e2e.py`: 45 frontend integration E2E tests.

### 4.2 Frontend (`C:\Users\arpit\Desktop\WAPSI-Buildathon`)
- `src/services/api/apiClient.ts`: Centralized typed API client bound to live FastAPI backend.
- `src/components/recovery/OperatorApprovalModal.tsx`: HITL modal with SHA-256 snapshot computation.
- `src/components/shared/WapsiBrandedHeader.tsx`: Swiss minimalist fintech header with live telemetry.
- `src/components/shared/DataTransparencyBanner.tsx`: Dynamic banner bound to API connection status.
- `src/pages/ObservationalLearningPage.tsx`: Observational learning metrics and date-filtered DML exporter.
- `src/pages/WorkerOperationsPage.tsx`: Background worker health and outbox partition breakdown.
- `src/components/layout/DashboardLayout.tsx`: Responsive layout supporting desktop, tablet, and mobile.
- `src/components/layout/Sidebar.tsx`: Off-canvas responsive mobile drawer with hamburger toggle.

---

## 5. Machine Learning Models & Artifacts

Located in `models/`:
- `models/manifest.json`: Active production version `v1.2.0-dml` registering 3 models.
- `models/wapsi_t_learner_v1.0.0.joblib` (35,000 training rows, Qini: 104.22).
- `models/wapsi_x_learner_v1.1.0.joblib` (35,000 training rows, Qini: 102.89).
- `models/wapsi_dml_v1.2.0.joblib` (35,000 training rows, Qini: 99.49, positivity satisfied).

---

## 6. Protected Target Outbox Job Record

- **Job UUID**: `5a6587ab-2601-4017-b396-48e3d2fc2fda`
- **Merchant UUID**: `04a2aaf8-8c8a-4d99-852c-cefc80e82019`
- **Status in Hosted PostgreSQL**: `SENT`
- **Retry Count**: `1`
- **Approved by Operator**: `operator_arpit`
- **Approval Snapshot Hash**: `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd`
- **Safety Invariant**: Guarded by `guard_live_target_mutations` in `tests/conftest.py`. Exactly zero mutations occurred.

---
*End of WAPSI Phase 7 Release Evidence Index.*
