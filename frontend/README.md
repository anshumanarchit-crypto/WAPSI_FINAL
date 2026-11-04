# WAPSI — AI Revenue Recovery Engine (Frontend)

WAPSI is an AI-powered revenue recovery intelligence platform designed for modern recurring and digital commerce. Unlike traditional blunt retry systems that spam users or blindly reissue transactions, WAPSI determines **causal incremental uplift**—predicting not just who pays, but who pays *specifically because of a strategic intervention*—while respecting strict compliance limits (NPCI, contact budgets, frequency caps) and preserving merchant trust.

## 🎯 Primary Source of Truth
This frontend implementation is a pixel-accurate reproduction of the Google Stitch Project:
[Google Stitch WAPSI Project](https://stitch.withgoogle.com/projects/11931954862282798683)

## 🧭 Core Product Screens (7 Routes)
- `/overview`: High-level pulse of revenue at risk, incremental recovery, AI opportunities, domain breakdown, funnel, and governance banner.
- `/recovery-center`: Live recovery mission control queue with recommended actions, incremental uplift %, decision confidence, evidence source, and interactive Case Intelligence Drawer.
- `/ai-decisions`: Deep causal uplift intelligence, treatment vs baseline comparison (No Action, Retry, WhatsApp, Voice, Incentive), timing hazard curves, network prior signal contribution, and model health.
- `/recovery-cases`: Comprehensive operational ledger of all recovery cases with multi-facet filtering, sorting, status tracking, and case causal attribution.
- `/analytics`: Causal recovery metrics, WAPSI vs Baseline counterfactual comparison, domain/outcome distributions, and real-time interactive Recovery Simulator.
- `/governance`: Enterprise policy controls (NPCI limits, contact budgets), Policy Health gauge, immutable Audit Trail timeline, Fairness & Bias monitor, and TEE Enclave simulation.
- `/settings`: Merchant profile, engine & model thresholds, communication channels, integrations, and data retention policies.

## 🧠 How WAPSI Works (The Core Product Thesis)

Most recovery systems predict **who will pay** and repeatedly retry every failed transaction. This wastes merchant margins on discounts, triggers bank velocity blocks, and contacts customers who would have paid organically.

WAPSI predicts **who pays because we act**:
1. **Natural Recovery Estimation ($P_0$):** What is the probability this customer self-recovers organically without any intervention?
2. **Multi-Treatment Causal Uplift ($\tau_t$):** For each intervention channel $t \in \{\text{Retry}, \text{WhatsApp}, \text{Voice}, \text{Incentive}\}$, what is the true incremental lift over natural recovery: $\tau(t) = P(\text{recovery} \mid t) - P_0$?
3. **Expected Net Recovery Value (ENRV) Optimization:** Rather than picking the channel with the highest raw recovery probability, WAPSI maximizes net economic payoff:
   $$\text{ENRV}(t) = \left[P(\text{recovery} \mid t) \times \text{Amount}\right] - \text{Intervention Cost} - \text{Incentive Margin Loss} - \text{Operational Fees} - \text{Risk Penalty}$$
4. **Continuous-Time Hazard Timing:** Identifies the exact hour window (e.g., Tomorrow 10:30–12:00 IST) that aligns with banking settlement cycles (salary credit batches) while strictly avoiding TRAI DND curfew hours (21:00–09:00 IST).
5. **Deterministic Policy & Compliance Gating:** Enforces 5 hard regulatory constraints before dispatch (NPCI 3-retry caps, TRAI weekly contact budgets, merchant discount ceilings, high-value audit thresholds, conformal confidence lower bounds).
6. **Human-in-the-Loop Routing:** Automatically dispatches high-confidence decisions while escalating out-of-distribution (OOD) cases, high-value transactions, or policy edge-cases to Risk Officers.
7. **Closed-Loop Bayesian Learning:** When payment outcomes occur, Bernoulli evidence updates posterior Beta-binomial channel priors and logs tamper-evident SHA-256 audit blocks.
8. **Covariate Drift & PSI Monitoring:** Continuously evaluates Population Stability Index on incoming transaction features. Under critical drift, autonomous dispatch is halted and shifted to human review.

---

## 💎 Technical Differentiators for Judges

| Evaluation Dimension | Traditional Blunt Retry / Heuristics | WAPSI AI Causal Decision Engine |
| :--- | :--- | :--- |
| **Optimization Target** | Raw recovery probability or blind scheduled retry | **Expected Net Recovery Value** ($\arg\max_t \text{ENRV}$) |
| **Discount Handling** | Blasts 5–10% coupons to everyone | Disqualifies incentives when discount costs exceed uplift |
| **Fatigue & Compliance** | Spams until customer complains or bank blocks | Strict TRAI 3-contact budget & NPCI retry enforcement |
| **Timing Precision** | Fixed delays (e.g. +4 hours, +24 hours) | Continuous-time hazard survival curve matching settlement batches |
| **Transparency** | Black-box scoring or rigid if-else rules | SHAP causal drivers, "Why this action?", "Why not alternatives?" |
| **Self-Auditing Autopilot**| Batch scripts with silent failures | Mathematical invariant check: $\text{AUTO} + \text{REVIEW} + \text{BLOCK} \equiv \text{TOTAL}$ |

---

## ⚡ Hero Case Judging Walkthrough (₹8,999 Insufficient Funds)

Click the **`⚡ Hero Demo (₹8,999)`** button in the top navigation bar to launch the interactive 10-step guided judging walkthrough:
- **Step 1: Failed Transaction Ingestion** (₹8,999 UPI Autopay drop, Customer Ananya Sharma).
- **Step 2: Natural Recovery Assessment** ($P_0 = 47.9\%$, Expected gross ₹4,311).
- **Step 3: Multi-Treatment Causal Evaluation** (Comparing No Action, Retry, WhatsApp, Voice, Incentive).
- **Step 4: The Economic Inversion** (Why Incentive at 87.7% loses to WhatsApp at 76.5% due to ₹1,605 margin erosion).
- **Step 5: Optimal Action Selection** (WhatsApp selected with ₹6,880 Expected Net Value).
- **Step 6: Hazard Timing Curve** (18–24h window chosen, avoiding 9 PM–9 AM TRAI DND curfew).
- **Step 7: Policy & Governance Gate** (5/5 checks verified in TEE simulation).
- **Step 8: Autonomous Dispatch & Execution Receipt** (Cryptographic attestation).
- **Step 9: Closed-Loop Bayesian Outcome** (Simulating payment recovery & shifting prior from 76.5% to 77.2%).
- **Step 10: Batch Autopilot & Portfolio Scale** (Processing 350 transactions with invariant verification).

---

## 🧪 Testing & Validation

```bash
# Run the complete Causal Engine test suite (17/17 passing tests)
npx tsx tests/causalEngine.test.ts

# Run the Python backend test suite (221/221 passing tests)
python -m pytest backend/tests

# Validate TypeScript compilation & production bundle
npm run build
```

---

## 📁 Architecture Documentation
Detailed specifications are organized in `/docs`:
- `docs/01-product-spec.md`
- `docs/02-stitch-design-spec.md`
- `docs/03-design-system.md`
- `docs/04-frontend-architecture.md`
- `docs/05-api-contract.md`
- `docs/06-ml-contract.md`
- `docs/07-demo-flow.md`
- `docs/08-visual-validation.md`

