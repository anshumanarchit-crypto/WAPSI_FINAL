# 01 — WAPSI Product Specification

## 1. Executive Summary
WAPSI (Weighted Adaptive Payment Strategy Intelligence) is an AI Revenue Recovery Engine. It solves the critical failure point of modern recurring billing, subscription services, and digital checkouts: **failed transactions and churn**.

Traditional recovery systems rely on static retry schedules and aggressive notifications. This leads to:
1. Wasted retry costs and customer fatigue.
2. Cannibalization: spending resources contacting customers who would have recovered naturally.
3. Policy breaches (e.g. NPCI daily retry limits in India).

WAPSI introduces **Causal Uplift Modeling** to recovery:
- Distinguishes **Natural Recovery Probability** ($P_0$) from **Treatment Recovery Probability** ($P_t$).
- Computes **Incremental Uplift** ($\tau = P_t - P_0$).
- Selects the optimal action (including **No Action** when natural recovery is high or intervention yields negligible marginal gain).
- Optimizes the exact intervention timing window (Hazard/Survival modeling).
- Leverages **Network Priors** (cross-merchant intelligence from millions of transactions) blended with merchant-specific behavioral evidence.

## 2. Core Value Pillars
- **Causal Uplift vs Predictive Scoring**: Prioritizes cases where merchant intervention *causes* recovery, rather than cherry-picking easy recoveries.
- **Timing Optimization**: Predicts peak recovery windows (e.g. post-salary credit, 18-24h window).
- **Multi-Channel Precision**: Smart Retries, WhatsApp Nudges, Voice Calls, Incentive Links, or No Action.
- **Strict Governance & Compliance**: Enforces NPCI limits, customer contact budgets, and algorithmic fairness.
- **Cold-Start Resolution**: Utilizes aggregate network intelligence to guide decisions for new merchants from Day 1.

## 3. Seven Primary Surfaces
1. **Overview**: Executive recovery pulse, revenue metrics, AI opportunities, funnel, and health.
2. **Recovery Center**: Operational mission control for managing actionable recovery opportunities.
3. **AI Decisions**: Model explainability, causal uplift distributions, timing curves, and network signal blending.
4. **Recovery Cases**: Complete searchable audit ledger of individual transaction attempts and recovery states.
5. **Analytics**: Incremental uplift verification, baseline counterfactuals, and interactive policy simulation.
6. **Governance**: Policy compliance bars, immutable audit trails, demographic fairness, and TEE privacy boundaries.
7. **Settings**: Merchant profile, engine thresholds, channel configurations, and data retention rules.
