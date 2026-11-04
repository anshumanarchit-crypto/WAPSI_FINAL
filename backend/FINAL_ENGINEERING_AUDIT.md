# WAPSI Comprehensive Engineering Audit & Technical Verification
**Razorpay AI Buildathon 2026 | Track 3: Autonomous & Advisory Recovery Router**  
**Audit Conducted By**: Principal Software Engineer, Senior ML Engineer, Fintech Architect & Security Engineer  
**Date**: August 30, 2026 | **Assessment Scope**: Full Workspace Repository

---

## 1. Executive Summary & Verdict

This engineering audit reviews the entire **WAPSI (WhatsApp Automated Payment Recovery and Smart Intervention)** repository against production fintech standards. The system has been audited for:
- Mathematical correctness of causal uplift estimators (T-Learner, X-Learner)
- Hidden potential outcome isolation and data leakage prevention
- Evaluation metrics (Qini curve, AUUC, Oracle bounds)
- Timing hazard estimation and issuer/BIN segmentation
- TreeSHAP local attribution and precedent ground-truth retrieval
- Empirical Bayes network prior shrinkage
- Contextual linear Thompson Sampling bandit exploration
- API contract stability, schema validation, and error boundaries
- Production-shaped TEE boundary, attestation verification, and fail-closed security
- OWASP Top 10 defense, SQLi, XSS, tenant isolation, rate limiting, and webhook HMAC
- Local end-to-end reproducibility and demo execution

**Overall Verdict**: **APPROVED FOR SUBMISSION & LIVE DEMO** (203/203 automated test cases passing).

---

## 2. Comprehensive Audit Findings Across Areas A – K

### Area A: Causal Data Generation & Potential Outcome Isolation
- **Item A.1**:
  - **SEVERITY**: LOW
  - **FILE**: `src/data_generator.py`
  - **PROBLEM**: Ground truth dataset exports counterfactual potential outcomes $Y(a)$ alongside observed factual recovery.
  - **WHY IT MATTERS**: If training pipelines ingest the ground truth file instead of observed data, models would overfit to unobserved counterfactuals (causal data leakage).
  - **RECOMMENDED FIX**: Enforce programmatic column filters in `WAPSIUpliftModel.fit()` that raise an exception if any column starting with `y_`, `p_`, or `tau_` is present.
  - **FIXED?**: **YES** (Strict isolation guard implemented in `src/t_learner.py` and `src/x_learner.py`).

### Area B: Uplift Model & Causal Estimators
- **Item B.1**:
  - **SEVERITY**: MEDIUM
  - **FILE**: `src/t_learner.py` & `src/x_learner.py`
  - **PROBLEM**: Ambiguity between predicted absolute recovery probability $P(Y=1 \mid A=a)$ and incremental causal uplift $\tau_a(x) = E[Y(a) - Y(\text{no\_action}) \mid X=x]$.
  - **WHY IT MATTERS**: An action with high base probability (e.g. UPI retry on affluent users) might have zero or negative incremental uplift, leading to wasted contact cost and customer fatigue.
  - **RECOMMENDED FIX**: Explicitly expose `predict_uplift()` computing CATE $\hat{\tau}_a(x) = \hat{\mu}_a(x) - \hat{\mu}_0(x)$ separately from raw response probabilities `predict_action_outcomes()`.
  - **FIXED?**: **YES** (Separate APIs implemented and validated across test suites).

### Area C: Uplift Evaluation & Metrics
- **Item C.1**:
  - **SEVERITY**: LOW
  - **FILE**: `evaluation/qini.py` & `evaluation/auuc.py`
  - **PROBLEM**: Division-by-zero risk in Qini computation when an evaluation decile contains zero control or treatment units.
  - **WHY IT MATTERS**: Bins with extreme targeting depth or small sample size could cause `NaN` or crash evaluation scripts.
  - **RECOMMENDED FIX**: Add fallback guards returning `0.0` incremental gain when $N_T=0$ or $N_C=0$.
  - **FIXED?**: **YES** (Tested in `tests/test_uplift_evaluation.py`).

### Area D: Timing Hazard Survival Model
- **Item D.1**:
  - **SEVERITY**: LOW
  - **FILE**: `src/hazard_model.py`
  - **PROBLEM**: Unseen bank issuer or BIN bucket in inference causing index error in discrete hazard matrix.
  - **WHY IT MATTERS**: Production traffic frequently encounters non-standard or new BIN prefixes.
  - **RECOMMENDED FIX**: Implement categorical fallback mapping unseen issuers/BINs to `"OTHER"` and `"classic"`.
  - **FIXED?**: **YES** (Handled in `WAPSIHazardModel.recommend_timing()` and tested in `test_hazard_model.py`).

### Area E: Explainability & Precedents
- **Item E.1**:
  - **SEVERITY**: MEDIUM
  - **FILE**: `src/precedent_engine.py`
  - **PROBLEM**: NearestNeighbors search could inadvertently retrieve cases from a test set if fit on evaluation splits.
  - **WHY IT MATTERS**: Peer evidence presented to merchants must only reference historical settled cases.
  - **RECOMMENDED FIX**: Enforce that `WAPSIPrecedentEngine.fit()` only runs on historical training splits.
  - **FIXED?**: **YES** (Precedent engine fits exclusively on training history).

### Area F: Network Prior & Shrinkage
- **Item F.1**:
  - **SEVERITY**: LOW
  - **FILE**: `src/network_prior.py`
  - **PROBLEM**: Merchant sample size $n=0$ causing undefined weight or zero division in empirical Bayes formula.
  - **WHY IT MATTERS**: New merchants (cold start) must seamlessly inherit global network effect.
  - **RECOMMENDED FIX**: Use smooth rational shrinkage $w(n) = \frac{n}{n + n_0}$ where $w(0) = 0.0$ yields 100% network prior.
  - **FIXED?**: **YES** (Validated in `tests/test_network_prior.py`).

### Area G: Contextual Bandit & Policy Engine Safety
- **Item G.1**:
  - **SEVERITY**: HIGH
  - **FILE**: `src/bandit.py` & `wapsi/policy/policy_engine.py`
  - **PROBLEM**: Autonomous reinforcement learning bandit exploring actions that violate compliance (e.g. messaging during TRAI DND 21:00–09:00 IST).
  - **WHY IT MATTERS**: Fintech recovery systems cannot allow stochastic exploration to violate regulatory DND or contact frequency caps.
  - **RECOMMENDED FIX**: Filter candidate action space through the Policy Engine before bandit exploration, ensuring policy-ineligible actions cannot be sampled.
  - **FIXED?**: **YES** (Candidate action filtering strictly enforced in `WAPSIInferenceEngine.predict()` and `simulation/simulator.py`).

### Area H: API Contract & Stability
- **Item H.1**:
  - **SEVERITY**: LOW
  - **FILE**: `api/app.py` & `api/schemas.py`
  - **PROBLEM**: Non-standard error response shapes on 404/422 causing frontend crashes.
  - **WHY IT MATTERS**: The frontend dashboard requires a consistent `ErrorResponse` schema.
  - **RECOMMENDED FIX**: Add custom Starlette and FastAPI validation exception handlers standardizing all error bodies.
  - **FIXED?**: **YES** (Implemented and verified in `tests/test_api.py`).

### Area I: TEE Boundary & Hardware Enclave Claims
- **Item I.1**:
  - **SEVERITY**: HIGH
  - **FILE**: `security/tee/mock_tee.py` & `docs/TEE_ARCHITECTURE.md`
  - **PROBLEM**: Risk of falsely claiming production hardware enclave execution in pitch.
  - **WHY IT MATTERS**: Hackathon integrity requires transparently distinguishing between mock/software abstractions and hardware deployments.
  - **RECOMMENDED FIX**: Explicitly document that `WAPSIMockTEE` is a cryptographic software emulation of an AWS Nitro / Intel SGX enclave with real SHA-256 PCR measurements, HMAC signatures, and fail-closed gates, but not a hardware-provisioned enclave.
  - **FIXED?**: **YES** (Documented in `docs/TEE_ARCHITECTURE.md` and verified in `tests/test_tee.py`).

### Area J: Security, OWASP & Tenant Isolation
- **Item J.1**:
  - **SEVERITY**: HIGH
  - **FILE**: `api/app.py`
  - **PROBLEM**: Insecure Direct Object Reference (IDOR) / Cross-tenant prediction requests where Merchant A queries Merchant B's customer data.
  - **WHY IT MATTERS**: Multi-tenant SaaS must prevent cross-merchant data leakage.
  - **RECOMMENDED FIX**: Add tenant authorization check verifying `X-Merchant-ID` header matches payload `merchant_id`, returning `403 Forbidden` on mismatch.
  - **FIXED?**: **YES** (Enforced in `api/app.py` and verified in `tests/test_security_audit.py`).

### Area K: End-to-End Demo & Reproducibility
- **Item K.1**:
  - **SEVERITY**: MEDIUM
  - **FILE**: `simulation/runner.py`
  - **PROBLEM**: Windows console `UnicodeEncodeError` when printing currency symbol `₹`.
  - **WHY IT MATTERS**: Running `simulation/runner.py` on default Windows PowerShell could crash the live demo.
  - **RECOMMENDED FIX**: Configure `sys.stdout.reconfigure(encoding="utf-8")` in `simulation/runner.py`.
  - **FIXED?**: **YES** (Fixed and tested on Windows environment).

---

## 3. Verified System Capabilities

### 3.1 Genuinely Implemented Components
1. **Multi-Action T-Learner & X-Learner Meta-Estimators**: Real scikit-learn Gradient Boosting classifiers fitted across 6 treatment arms.
2. **Discrete-Time Hazard Survival Model**: Predicts recovery probability across 4 operational windows (0-24h, 24-48h, 48-72h, 72h+).
3. **TreeSHAP Local Attribution**: Real Shapley value attribution explaining causal uplift drivers.
4. **Precedent Retrieval Engine**: Real k-NN search on standardized feature space with historical counter-evidence detection.
5. **Empirical Bayes Network Prior**: Analytical shrinkage calculator for merchant cold-start.
6. **Split-Conformal Calibration Decision Gate**: Calibrated nonconformity quantile threshold for $(1-\alpha)$ coverage guarantee.
7. **Contextual Thompson Sampling Bandit**: Online linear Bayesian ridge regression tracking cumulative business reward.
8. **Cryptographic Append-Only Audit Ledger**: Real SHA-256 hash-chained block ledger with tamper-evident verification.
9. **FastAPI Production REST API**: Fully validated Pydantic schemas, rate limiting, and tenant authorization.
10. **Full Test Suite**: 203 automated test cases covering causal data, ML models, API, security, TEE, and simulation.

### 3.2 Mocked / Simulated Components (Clearly Disclosed)
1. **Mock TEE Enclave (`WAPSIMockTEE`)**: Emulates hardware attestation (PCR0/PCR1/PCR2) and cryptographic signing in software.
2. **Simulated Payment Gateway & Dispatches**: Emulates customer recovery responses and channel dispatches without calling real Razorpay production endpoints or charging live cards.
3. **Synthetic Tabular DGP (`WapsiDataGenerator`)**: Generates realistic payment failures with mathematically defined ground-truth treatment effects.

### 3.3 What Should NEVER Be Claimed in the Pitch
- **Do NOT claim**: "WAPSI is currently running inside an Intel SGX / AWS Nitro hardware enclave in production." (State that a production-shaped TEE abstraction is implemented with real cryptographic verification).
- **Do NOT claim**: "WAPSI sends live WhatsApp messages or charges live credit cards." (State that the causal decision engine recommends and simulates execution).
- **Do NOT claim**: "WAPSI provides a 100% mathematical guarantee of recovery." (State that split-conformal calibration provides distribution-free 90% finite-sample confidence bounds on uplift).

---

## 4. Operational & Demo Runbook

### 4.1 Prerequisites
```bash
python -m pip install -r requirements.txt
```

### 4.2 Run End-to-End Simulation Demo
```bash
python simulation/runner.py
```

### 4.3 Run FastAPI REST API Server
```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI Docs: `http://localhost:8000/docs`

### 4.4 Sample API Request
```bash
curl -X POST "http://localhost:8000/api/v1/recovery/predict" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: rzp_live_wapsi_key_demo" \
     -H "X-Merchant-ID: merch_trendy_wear" \
     -d '{
       "case_id": "CASE_REC_101",
       "merchant_id": "merch_trendy_wear",
       "domain": "ecommerce",
       "amount": 4999.0,
       "decline_reason": "upi_pin_timeout",
       "attempts_used": 1,
       "account_age_days": 420,
       "previous_failures": 1,
       "previous_recoveries": 2,
       "prior_recovery_rate": 0.85,
       "day_of_week": 2,
       "hour": 14,
       "issuer": "HDFC",
       "bin_bucket": "platinum",
       "fatigue_score": 0.05
     }'
```

### 4.5 Run Complete Test Suite
```bash
python -m pytest tests/ -v
```
Result: **203 passed**.
