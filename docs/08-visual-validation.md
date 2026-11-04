# 08 — Visual Validation & Verification Protocol

This document defines the strict visual validation checklist and comparison protocol to ensure pixel fidelity with Google Stitch.

## 1. Reference Screenshots Directory
All Stitch canvas captures are stored in:
- `overview_screen_1788196671283.png`
- `recovery_center_screen_1788196716661.png`
- `ai_decisions_screen_1788196286185.png`
- `recovery_cases_screen_1788196349725.png`
- `analytics_screen_1788196124941.png`
- `governance_screen_1788196082807.png`
- `settings_screen_1788196169573.png`

## 2. Screen Comparison Gates

### Screen 1: Overview (`/overview`)
- [ ] Sidebar width is `w-60` (240px) with correct logo, nav items, status dot, AI card, and user footer.
- [ ] Topbar displays date selector, search, notifications, help, avatar.
- [ ] 5 Top metric cards match exact values (₹18.42L, ₹11.76L, ₹2.14L, ₹7.82L, 66.5%) with color-coded delta pills.
- [ ] Recovery Pulse chart shows dual glowing lines (WAPSI vs Baseline) and Aug 28 peak callout.
- [ ] AI Opportunities card features circular radial gauge + top opportunity actions with amounts.
- [ ] Domain donut chart, Funnel bars, Failure Reasons, Model Health score (95), and Governance footer banner match Stitch geometry.

### Screen 2: Recovery Center (`/recovery-center`)
- [ ] 4 top KPI cards (₹18.42L, ₹11.76L, ₹2.14L, 128 Actions Ready).
- [ ] 7 filter tabs with pill badges (All 128, Subscriptions 52, Checkout 28, B2B 16, Needs Review 14, High Impact 21, Promise-to-Pay 11).
- [ ] Recovery queue table rows display action badges, uplift % in green, confidence %, and evidence source.
- [ ] Clicking a row smoothly opens the Case Intelligence Drawer with action comparison bar chart, SHAP attribution, timing chart, and policy checklist.

### Screen 3: AI Decisions (`/ai-decisions`)
- [ ] Hero banner: *"WAPSI doesn't predict who pays. It predicts who pays because we act."*
- [ ] 5 tab headers: Decision Queue, Uplift Intelligence, Timing Intelligence, Network Prior, Model Health.
- [ ] Treatment comparison chart showing No Action (48%) vs Retries/WhatsApp/Voice/Incentive.
- [ ] Segment Impact ranking for Retry treatment.
- [ ] Hazard timing curve with 18h peak marker.
- [ ] Network prior signal split (70% Network / 30% Merchant).
- [ ] AUUC (0.87), Qini (0.31), Conformal coverage (95.1%).

### Screen 4: Recovery Cases (`/recovery-cases`)
- [ ] 5 KPI cards matching global totals.
- [ ] Comprehensive filter bar with reset & export buttons.
- [ ] Tab status badges (All, Detected, Scored, Ready, Approved, Actioned, Recovered, Failed, Escalated, Monitoring).
- [ ] High-density enterprise ledger table with sorting and drawer integration.

### Screen 5: Analytics (`/analytics`)
- [ ] Top 4 KPI summary cards.
- [ ] WAPSI vs Baseline counterfactual comparison table with colored delta columns.
- [ ] Recovery Over Time graph with glowing area fill.
- [ ] Domain and Outcome donut charts.
- [ ] Interactive Recovery Simulator with responsive sliders and dynamic calculation of contact efficiency.

### Screen 6: Governance (`/governance`)
- [ ] 5 Policy KPI cards with sparklines.
- [ ] Policy Controls Overview table with compliance progress bars and status badges.
- [ ] Policy Health radial gauge (100% Healthy).
- [ ] Interactive Audit Trail timeline with step-by-step verification badges.
- [ ] Fairness & Bias Monitor segment table and disparity metrics.
- [ ] Prototype TEE Security Boundary card.

### Screen 7: Settings (`/settings`)
- [ ] 5 navigation tabs (Merchant, Recovery Policies, Channels, Integrations, Team & Access).
- [ ] Merchant Profile card with verified badge and details.
- [ ] Business Overview KPI grid.
- [ ] Interactive Notification switches and channel checkboxes.
- [ ] Engine & Model parameter sliders/inputs.
- [ ] Data retention dropdowns.
