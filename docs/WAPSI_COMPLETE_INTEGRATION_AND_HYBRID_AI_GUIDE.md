# WAPSI — COMPLETE INTEGRATION, PRODUCTION HARDENING & HYBRID AI IMPLEMENTATION MANUAL

**Document ID**: `WAPSI-PROD-INTEGRATION-GUIDE-2026`  
**Platform Version**: `v1.2.0-Production-Hardened`  
**Track**: Razorpay AI Buildathon 2026 — Track 3 (Autonomous Payment Recovery Intelligence)  

---

## 1. System Architecture Map & Integration Topology

WAPSI preserves and combines its existing deterministic decision engines, causal meta-learners, contextual bandits, and governance gates with a high-performance **Hybrid Monte Carlo + LLM Synthetic Data Generation Architecture**.

```
                                  WAPSI INTEGRATED ARCHITECTURE TOPOLOGY
                                  
   +-------------------------------------------------------------------------------------------------+
   |                                     DATA GENERATION & LAB LAYER                                 |
   |                                                                                                 |
   |  [ Procedural Monte Carlo Simulator ]  ----> [ 10,000-Row Immutable Mathematical Skeleton ]     |
   |   (Bounded Chunks / Seed Reproducible)       - Integer paise precision (amount_paise)           |
   |                                              - Factual & Counterfactual outcomes Y(a)           |
   |                                              - Declines, Domains, Fatigue, Issuers, Diurnal     |
   |                                                          |                                      |
   |                                                          v                                      |
   |                            +-------------------------------------------------------------+      |
   |                            |              DUAL-AGENT NARRATIVE STUDIO                    |      |
   |                            |                                                             |      |
   |                            |  [ Agent A: NarrativeGenerator ]                            |      |
   |                            |    Creative synthetic company, contact, backstory, Hinglish |      |
   |                            |                              |                              |      |
   |                            |                              v                              |      |
   |                            |  [ Agent B: NarrativeCritic ]                               |      |
   |                            |    Anti-hallucination review: JSON pass/fail verdict        |      |
   |                            |                              |                              |      |
   |                            |                              v                              |      |
   |                            |  [ Deterministic Programmatic Python Validator ]            |      |
   |                            |    - Exact 2-sentence backstory validation                  |      |
   |                            |    - Strict outcome consistency (failed != recovered)       |      |
   |                            |    - Amount string immutability verification                |      |
   |                            |    - Retry Loop (Max 3 attempts -> Fallback)                |      |
   |                            +-------------------------------------------------------------+      |
   |                                                          |                                      |
   |                                                          v                                      |
   |                            [ Enriched Dataset: Mathematical Skeleton + Validated Narrative ]     |
   +-------------------------------------------------------------------------------------------------+
                                                              |
                                                              v
   +-------------------------------------------------------------------------------------------------+
   |                                    CAUSAL ML & DECISION LAYER                                   |
   |                                                                                                 |
   |   - Causal Meta-Learners: T-Learner, X-Learner, Double Machine Learning (DML)                   |
   |   - Multi-Action Contextual Bandit: LinUCB with Sherman-Morrison rank-1 updates                  |
   |   - Conformal Prediction Gate: 90% finite-sample marginal coverage interval                     |
   |   - Timing Hazard Model: Optimal customer outreach delay estimation                             |
   |   - Root-Cause Decline Taxonomy: Multi-stage UPI, Card, Mandate, Gateway classification         |
   |   * INVARIANT: Narrative strings are NEVER fed into causal meta-learners (Zero Data Leakage)    |
   +-------------------------------------------------------------------------------------------------+
                                                              |
                                                              v
   +-------------------------------------------------------------------------------------------------+
   |                                    OPERATOR GOVERNANCE & HITL GATE                              |
   |                                                                                                 |
   |   - Operator Authorization Gate (OPR_MERCHANT_LEAD / OPR_FINTECH_DIRECTOR)                      |
   |   - SHA-256 Approval Snapshot: Hash(case_id:action:customer_id:dispatch_id:operator_id)         |
   |   - Cryptographic Audit Ledger: Tamper-evident hash-chained blocks                              |
   +-------------------------------------------------------------------------------------------------+
                                                              |
                                                              v
   +-------------------------------------------------------------------------------------------------+
   |                                      DURABLE STORAGE & OUTBOX                                   |
   |                                                                                                 |
   |   - PostgreSQL (Supabase ap-south-1 Mumbai): Multi-tenant Row-Level Security (RLS)              |
   |   - Durable Recovery Outbox: State machine (QUEUED -> SENDING -> SENT / RECOVERY)               |
   |   - Protected Target Outbox Job: 5a6587ab-2601-4017-b396-48e3d2fc2fda (SENT, 0 mutations)       |
   |   - Webhook Event Inbox: Deduplication and idempotency keys (idemp_...)                         |
   +-------------------------------------------------------------------------------------------------+
                                      |                                             |
                                      v                                             v
   +-------------------------------------------------------+   +------------------------------------+
   |               META WHATSAPP CLOUD API                 |   |           RAZORPAY GATEWAY         |
   |                                                       |   |                                    |
   | - Meta Graph API v26.0 (Phone: 1407090562487899)      |   | - Test Mode Gateway (rzp_test_...) |
   | - 24-Hour Customer Service Window enforcement         |   | - Integer paise calculations       |
   | - Pre-approved template: wapsi_payment_recovery_v1    |   | - JIT Payment Link generation      |
   | - Webhook GET handshake & POST X-Hub-Signature-256    |   | - Webhook HMAC-SHA256 verification |
   +-------------------------------------------------------+   +------------------------------------+
```

---

## 2. Environment Variable Reference (Zero Secrets)

All server-side secrets are stored exclusively on the backend (`.env`) and parsed using Pydantic `SecretStr`. Never expose these variables to frontend bundles or client logs.

| Environment Variable | Category | Description | Safe Example Format |
| :--- | :--- | :--- | :--- |
| `WAPSI_ENV` | Runtime | Environment profile (`development`, `staging`, `production`) | `development` |
| `HOST` | Runtime | Gateway bind address | `127.0.0.1` |
| `PORT` | Runtime | Gateway listen port (Windows WinError 10013 safe) | `8000` (or `8001`) |
| `DATABASE_URL` | Database | Supabase PostgreSQL connection string (Transaction Pooler) | `postgresql://postgres.[ref]:[pass]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres` |
| `WAPSI_ADMIN_DATABASE_URL` | Database | Direct connection for admin schema & migrations | `postgresql://postgres.[ref]:[pass]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres` |
| `SUPABASE_URL` | Supabase | Supabase Project REST URL | `https://[project-ref].supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase | Public client API key | `eyJhbGciOi...` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase | Backend administrative service-role key | `eyJhbGciOi...` |
| `RAZORPAY_MODE` | Payment | Mode (`test` or `live`) | `test` |
| `RAZORPAY_KEY_ID` | Payment | Razorpay API Key ID (prefixed with rzp_test_ in test mode) | `rzp_test_****` |
| `RAZORPAY_KEY_SECRET` | Payment | Razorpay API Secret | `[REDACTED_SECRET]` |
| `RAZORPAY_WEBHOOK_SECRET` | Payment | Razorpay Webhook HMAC secret | `[REDACTED_SECRET]` |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp | Meta WhatsApp Cloud Phone Number ID | `1407090562487899` |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | WhatsApp | Meta WhatsApp Business Account (WABA) ID | `969727602419694` |
| `WHATSAPP_ACCESS_TOKEN` | WhatsApp | Meta System User or Sandbox Bearer Token | `[REDACTED_TOKEN]` |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | WhatsApp | Verification challenge token for GET handshake | `[REDACTED_VERIFY_TOKEN]` |
| `META_APP_SECRET` | WhatsApp | Meta App Secret for `X-Hub-Signature-256` validation | `[REDACTED_APP_SECRET]` |
| `WHATSAPP_API_VERSION` | WhatsApp | Meta Graph API Version | `v26.0` |
| `GROQ_API_KEY` | LLM | Groq API Key (Primary Narrative Generator) | `gsk_****` |
| `GROQ_MODEL` | LLM | Model ID for Groq chat completions | `llama-3.3-70b-versatile` |
| `GEMINI_API_KEY` | LLM | Google AI Studio Gemini API Key | `AIzaSy****` |
| `GEMINI_MODEL` | LLM | Model ID for Gemini completions | `gemini-2.5-flash` |
| `OLLAMA_BASE_URL` | LLM | Local Ollama endpoint | `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | LLM | Local model installed in Ollama | `llama3` |

---

## 3. Supabase & PostgreSQL Integration

- **Cluster Location**: AWS `ap-south-1` (Mumbai).
- **Driver**: `psycopg2-binary>=2.9.9` with SQLAlchemy 2.0 session factory.
- **Connection Optimization**: Configured with `pool_size=4`, `max_overflow=2`, `pool_recycle=300`, and `sslmode="require"`.
- **Tenant Context**: Enforced via `app.current_merchant_id` session setting in all PostgreSQL queries:
  ```sql
  SELECT set_config('app.current_merchant_id', :merchant_id, true);
  ```
- **Protected Hosted Outbox Record**:
  - Outbox Job ID: `5a6587ab-2601-4017-b396-48e3d2fc2fda`
  - Merchant ID: `04a2aaf8-8c8a-4d99-852c-cefc80e82019`
  - Status: `SENT` (retry count: 1, payload hash: `dd0bcf49b2fa...`)
  - **Invariant**: Remains completely untouched by all tests, sweeps, and migrations.

---

## 4. Razorpay Payment Gateway Integration

- **Mode**: Strictly `test` mode during development.
- **Key Validation**: Ensures `RAZORPAY_KEY_ID` begins with `rzp_test_` in non-production. Rejects live keys in test mode.
- **Webhook HMAC-SHA256 Verification**:
  - The webhook handler computes constant-time HMAC-SHA256 over the unmodified raw request body (`request.body()`).
  - Signature header: `X-Razorpay-Signature`.
  - Replay protection: Durable deduplication via `X-Razorpay-Event-Id` in `webhook_inbox`.
- **Financial Calculation**:
  - All monetary amounts use integer paise (`amount_paise = int(round(amount * 100))`).
  - Clamped business utility rewards prevent unbounded bandit updates.

---

## 5. Meta WhatsApp Cloud API Integration

- **Graph API Endpoint**: `https://graph.facebook.com/v26.0/{phone_number_id}/messages`
- **Customer Service Window**: Enforces the 24-hour rule (`wapsi/integrations/whatsapp/service_window.py`).
  - Within 24 hours of customer inbound: permitted interactive / text nudges.
  - Outside 24 hours: pre-approved HSM template only (`wapsi_payment_recovery_v1`).
- **Webhook Handshake**:
  - GET `/api/v1/webhooks/whatsapp`: Validates `hub.mode=subscribe` and matches `hub.verify_token` against `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
  - POST `/api/v1/webhooks/whatsapp`: Computes HMAC-SHA256 over raw request bytes using `META_APP_SECRET` against `X-Hub-Signature-256`.

---

## 6. Hybrid Monte Carlo + LLM Synthetic Data Architecture

### Core Principle
Procedural simulation creates the mathematical ground truth. The LLM enriches that truth with realistic narratives. **The LLM never calculates, alters, or overrules numeric fields.**

### Step 1: The Mathematical Skeleton
- Generated by `DeterministicSkeletonGenerator` (`wapsi/simulation/hybrid_synthetic.py`).
- Produces exactly 10,000 synthetic rows in bounded chunks with reproducible seed (default 42).
- Contains 26 immutable columns: `amount_paise`, `amount_display`, `domain`, `decline_reason`, `treatment`, `recovered`, `outcome`, etc.
- Cryptographic SHA-256 manifest generated (`manifest.json`) verifying dataset immutability.

### Step 2: Agent A (NarrativeGenerator)
- Strict system prompt prevents inventing financial amounts or altering outcomes.
- Generates: `company_name`, `contact_person`, `failure_backstory` (exactly 2 sentences), `hinglish_whatsapp_message`, and `synthetic: true`.

### Step 3: Agent B (NarrativeCritic)
- Strict reviewer comparing original row with proposed narrative.
- Checks: outcome consistency, failure code alignment, amount integrity, PII absence.
- Returns strictly: `{"status": "pass", "error": null}` or `{"status": "fail", "error": "..."}`.

### Step 4: Deterministic Programmatic Python Validator
- Exact regex checks on sentence boundaries (`(?<!\d)[\.!\?](?:\s+|$)`).
- Outcome contradiction rejection (e.g. claims payment success when `recovered=0`).
- Exact formatted currency match.
- Retry policy: maximum 3 attempts per row.
- Fallback: deterministic offline narrative generator when 3 attempts fail, setting `narrative_status="fallback"`.

---

## 7. LLM Provider Routing & Fallback

- **Priority Tier**:
  1. Groq (`https://api.groq.com/openai/v1`, `llama-3.3-70b-versatile`)
  2. Gemini (`https://generativelanguage.googleapis.com/v1beta/openai`, `gemini-2.5-flash`)
  3. Local Ollama (`http://localhost:11434/v1`, `llama3`)
  4. Deterministic Offline Fallback (`wapsi-fallback-v1`)
- **Guaranteed Resilience**: When API credentials are absent or external services experience timeouts/rate limits, the deterministic fallback immediately provides valid narratives matching the exact schema.

---

## 8. Frontend Integration (Synthetic Data Lab)

- **Route**: `/synthetic-lab` (`src/pages/SyntheticLabPage.tsx`)
- **Navigation**: Registered in `Sidebar.tsx` with `Sparkles` icon.
- **Capabilities**:
  - Live Integration Health Telemetry Matrix.
  - Mathematical Skeleton Generator (Seed, Row Count, Progress Bar, Manifest Card).
  - Dual-Agent Narrative Studio (Provider Selector, Sample Batching, Live Agent Telemetry).
  - Enriched Dataset Explorer Table with pagination, search, and domain filtering.
  - Direct JSON and CSV dataset export.

---

## 9. Local Startup & Commands Guide

### A. Backend Activation & Startup
```powershell
# 1. Activate virtual environment
cd "C:\Users\arpit\Desktop\Razorpay\Razorpay"
.\.venv\Scripts\Activate.ps1

# 2. Run canonical FastAPI gateway on port 8000
python -m uvicorn wapsi.api.app:app --host 127.0.0.1 --port 8000 --reload
```

### B. Frontend Startup
```powershell
# In a separate terminal
cd "C:\Users\arpit\Desktop\WAPSI-Buildathon"
npm run dev
# Vite runs on http://localhost:5173
```

### C. Run All Backend Regression Tests
```powershell
cd "C:\Users\arpit\Desktop\Razorpay\Razorpay"
.\.venv\Scripts\python -m pytest tests/test_hybrid_synthetic_pipeline.py `
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

---

## 10. External Readiness & Production Pre-requisites

The platform is technically complete and verified across sandbox, simulation, and test modes. Live merchant production cutover requires the following external actions:

1. **Razorpay Live Credentials**:
   - Status: `rzp_test_****bdqI` returns HTTP 401 on `api.razorpay.com`.
   - Action Required: Regenerate valid API Key and Secret from the merchant Razorpay Dashboard.
2. **Meta WhatsApp System User Token**:
   - Status: Temporary sandbox token expired on 02-Nov-2026.
   - Action Required: Generate permanent System User Access Token in Meta Business Manager.
3. **Meta Message Template Pre-Approval**:
   - Status: Template `wapsi_payment_recovery_v1` is defined in code with full parameters.
   - Action Required: Submit `wapsi_payment_recovery_v1` in Meta WhatsApp Manager and await approval.
4. **Online LLM Credentials**:
   - Status: Unconfigured in local `.env` (system safely operates via deterministic fallback).
   - Action Required: Set `GROQ_API_KEY` or `GEMINI_API_KEY` in `.env` if cloud model generation is desired.
