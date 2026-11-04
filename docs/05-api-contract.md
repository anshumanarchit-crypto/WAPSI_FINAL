# 05 — API Contract Specification (Future FastAPI Interface)

The frontend is structured to communicate cleanly with a future FastAPI backend via typed endpoints.

## 1. Recovery Endpoints
- `GET /api/v1/recovery/cases`
  - Query parameters: `page`, `limit`, `domain`, `status`, `min_uplift`, `search`
  - Response: `{ cases: RecoveryCase[], total: number, page: number, limit: number }`
- `GET /api/v1/recovery/cases/{caseId}`
  - Response: `RecoveryCaseDetail` (including `decisionOutput`, `policyResult`, `auditEvents`)
- `POST /api/v1/recovery/cases/{caseId}/approve`
  - Body: `{ action: ActionType, scheduledTime?: string }`
  - Response: `{ status: "APPROVED", policyResult: PolicyResult, auditEventId: string }`
- `POST /api/v1/recovery/cases/{caseId}/review`
  - Body: `{ note: string }`
  - Response: `{ status: "UNDER_REVIEW" }`
- `POST /api/v1/recovery/cases/{caseId}/reject`
  - Body: `{ reason: string }`
  - Response: `{ status: "REJECTED" }`
- `POST /api/v1/recovery/cases/{caseId}/simulate-recovery`
  - Response: `{ status: "RECOVERED", recoveredAmount: number, recoveredAt: string }`

## 2. Decision & ML Endpoints
- `GET /api/v1/decisions/overview`
  - Response: `DecisionsSummary` (uplift metrics, timing hazard distributions, network prior blend)
- `GET /api/v1/decisions/model-health`
  - Response: `ModelHealth` (AUUC, Qini, Conformal coverage, OOD count, sub-model statuses)

## 3. Analytics & Simulation Endpoints
- `GET /api/v1/analytics/summary`
  - Query parameters: `startDate`, `endDate`, `domain`
  - Response: `AnalyticsSummary` (WAPSI vs Baseline comparison, domain breakdown, funnel)
- `POST /api/v1/analytics/simulate`
  - Body: `{ expectedContacts: number, retryBudget: number }`
  - Response: `SimulationResult` (projected recovery, efficiency delta, contact tradeoff)

## 4. Governance Endpoints
- `GET /api/v1/governance/policies`
  - Response: `PolicyControl[]` (NPCI limits, TRAI contact budget, compliance percentages)
- `GET /api/v1/governance/audit-trail`
  - Response: `AuditEvent[]`
- `GET /api/v1/governance/fairness`
  - Response: `FairnessMetrics` (Disparate impact, equal opportunity, calibration error)
- `GET /api/v1/governance/tee-status`
  - Response: `TEEStatus` (Attestation status, zero-copy guarantees, enclave signature)

## 5. Settings Endpoints
- `GET /api/v1/settings`
  - Response: `MerchantSettings`
- `PUT /api/v1/settings`
  - Body: `Partial<MerchantSettings>`
  - Response: `MerchantSettings`
