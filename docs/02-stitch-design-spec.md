# 02 — Stitch Design Specification

This specification documents the exact visual layout, components, and content hierarchy extracted from the Google Stitch canvas (`https://stitch.withgoogle.com/projects/11931954862282798683`).

## 1. Global Shell Structure
- **Left Sidebar** (Fixed `240px` / `w-60` width):
  - Brand header: WAPSI icon with purple glow + "WAPSI / AI Recovery Engine"
  - Main Navigation items:
    1. Overview (`/overview`)
    2. Recovery Center (`/recovery-center`)
    3. AI Decisions (`/ai-decisions`)
    4. Recovery Cases (`/recovery-cases`)
    5. Analytics (`/analytics`)
    6. Governance (`/governance`)
    7. Automations (Placeholder / Modal)
    8. Reports (Placeholder / Modal)
    9. Risk Radar (Placeholder / Modal)
    10. Settings (`/settings`)
  - Engine Status Widget: Green pulsating dot + "Engine Status / Operational / All systems running smoothly"
  - "Ask WAPSI AI" trigger banner with purple gradient
  - User profile badge: "Acme Corp / Merchant" with circular initial avatar
- **Topbar**:
  - Left: Screen Title & Subtitle description
  - Right:
    - Date Range Dropdown: "Aug 22 – Aug 28, 2025" with calendar icon
    - Filter Button: with filter counter badge
    - Notification bell with unread indicator
    - Help icon
    - User avatar badge
- **Background & Card Styling**:
  - Global canvas: Deep Navy `#080B11` / `#0B0F19`
  - Cards: Slate Navy `#0F172A` / `#111827` with 1px border `#1E293B`
  - Subtle gradients and high-contrast text hierarchy

## 2. Screen-by-Screen Inventory

### Screen 1: WAPSI Overview Dashboard (`/overview`)
- **Top Greeting & Pulse Banner**: "Good Afternoon, Merchant 👋 / Your recovery engine is performing great! WAPSI recovered ₹7.82L this month (+21.3% vs baseline)" + 3D/ambient visualization.
- **Top KPI Cards Row** (5 Cards):
  1. *Revenue at Risk*: ₹18.42L (+16.7% vs baseline) [Red warning accent]
  2. *Recoverable (Actionable)*: ₹11.76L (+25.4% vs baseline) [Amber accent]
  3. *Incremental Recovery*: ₹2.14L (+37.2% vs baseline) [Cyan accent] - "This is the additional recovery driven by WAPSI"
  4. *Recovered*: ₹7.82L (+21.3% vs baseline) [Purple accent]
  5. *Recovery Rate*: 66.5% (+4.6pp vs baseline) [Blue accent]
- **Main Section**:
  - *Recovery Pulse Chart*: Dual-line graph comparing WAPSI Recovered (Purple glow line) vs Baseline No-Action (Cyan line). Annotations for peak day (Aug 28: ₹1.24L). Bottom summary: Recovered ₹7.82L | Baseline ₹5.68L | Incremental ₹2.14L (+37.6%).
  - *AI Opportunities Card*: Radial progress gauge (12 High-confidence opportunities, ₹84,200 expected recovery, +27% Median Uplift, 91% Confidence, 1.6x vs rule-based) + Top Opportunity Actions (WhatsApp Nudge ₹41,200, Retry Smart ₹27,100, Incentive Link ₹14,500, Voice Call ₹7,400).
- **Bottom Section**:
  - *Recovery by Domain*: Donut chart (Subscriptions 64.2%, Checkout 21.3%, B2B Receivables 14.5%).
  - *Recovery Funnel*: Detected (12,842) → Scored (8,183) → Ready (4,257) → Actioned (2,934) → Recovered (1,842), 42.4% overall conversion.
  - *Top Failure Reasons*: Horizontal distribution bars (Insufficient Funds 42.3%, Card Expired 21.8%, Network Timeout 13.6%, Invalid Credentials 9.7%, Other 12.6%).
  - *Model Health Card*: Radial Score 95 + Sub-model statuses (Uplift Model Healthy, Hazard Model Healthy, Policy Engine Healthy, Data Pipeline Healthy, Feature Quality Good) + Conformal Coverage 95.1%, OOD Cases 7.
  - *Governance & Trust Bottom Banner*: "Policy Violations: 0 | All Actions Bounded | Fairness Within Threshold | TEE Protected (Simulated) | Audit Trail Active" + "VIEW GOVERNANCE" button.

### Screen 2: Recovery Center Mission Control (`/recovery-center`)
- **Top Summary Cards** (4 Cards):
  1. *Revenue at Risk*: ₹18.42L (+16.7% vs last 7 days)
  2. *Recoverable (Actionable)*: ₹11.76L (+25.4% vs last 7 days)
  3. *Incremental Recovery*: ₹2.14L (+37.6% vs baseline)
  4. *Actions Ready*: 128 (91% median confidence, +12.4% vs last 7 days)
- **Interactive Queue Tabs**:
  - `All 128`, `Subscriptions 52`, `Checkout 28`, `B2B 16`, `Needs Review 14`, `High Impact 21`, `Promise-to-Pay 11`
  - Search bar + Filters button
- **Queue Table Columns**:
  - `Case` (e.g. `RX-48291` with star icon)
  - `Customer` (e.g. `Customer #4821 / cust_6a113e`)
  - `Domain` (Badge: Subscriptions, Checkout, B2B)
  - `Failure` (Insufficient Funds, Payment Failed, Invoice Overdue, Card Expired, Partial Payment)
  - `Amount` (₹8,999, ₹4,200, ₹1,20,000, ₹2,899, ₹6,500, ₹85,000, ₹3,499, ₹1,199)
  - `Recommended Action` (Retry Tomorrow 10:30 AM Window 24-48h, WhatsApp Nudge Today 05:00 PM, Voice Call Tomorrow 11:00 AM, Email+Link, No Action (Monitor), Needs Review)
  - `Inc. Uplift (vs No Action)` (+24%, +15%, +18%, +12%, +21%, +2.1%, —)
  - `Decision Confidence` (96%, 91%, 89%, 76%, 94%, 83%, 94%, 61%)
  - `Evidence Source` (Network+Merchant, Network Data, Merchant Prior, Network Prior [OOD])
  - `Status` (READY, REVIEW, APPROVED, ACTIONED, MONITORING)
- **Case Intelligence Drawer** (Side Panel on row click):
  - Case Header: `RX-48291` (READY badge, ₹8,999, Subscription Payment Failure, Insufficient Funds)
  - *AI Recommendation*: Best Action = Retry (Tomorrow 10:30 AM, Optimal window 24-48h).
  - *Causal Comparison Display*: No Action (Natural recovery 48%) vs Treatment (With intervention 72%) → Incremental Uplift: `+24%`, Decision Confidence: `96%`.
  - *Action Comparison Bars*: No Action (48%), Retry (72% / +24%), WhatsApp Nudge (70% / +22%), Incentive Link (65% / +17%), Voice Call (54% / +6%), Email (51% / +3%).
  - *Why WAPSI Chose This (SHAP)*: Days since failure (+18%), Prior recovery rate (+11%), Issuer behavior (+9%), Amount (-4%), Contact fatigue (-6%).
  - *Evidence Source Breakdown*: Network 74%, Merchant 26%.
  - *Timing Intelligence*: Curve showing issuer success rate peaks at 72% in this window.
  - *Policy Check (5/5 passed)*: Minimum uplift threshold, Retry attempt limit (2/4 attempts), Contact budget (2/5 contacts), Recovery window (Within permitted window).
  - *Action Buttons*: `Approve` (Green/Primary), `Review` (Outline), `Reject` (Red outline).

### Screen 3: WAPSI AI Decisions Intelligence (`/ai-decisions`)
- **Hero Statement**: "WAPSI doesn't predict who pays. It predicts who pays because we act."
- **Navigation Tabs**: `Decision Queue`, `Uplift Intelligence` [Active], `Timing Intelligence`, `Network Prior`, `Model Health`.
- **Top Metrics**:
  - Avg. Incremental Uplift: `+22.6%` (+12.4% vs last 7 days)
  - Decisions Evaluated: `8,421` (+9.7% vs last 7 days)
  - Incremental Recovery (Est.): `₹2.14L` (+37.6% vs last 7 days)
- **Treatment Uplift Comparison Card**:
  - Horizontal/Vertical bar distribution comparing No Action (48% baseline), Retry (61% -> 72%, +13% to +24% uplift), WhatsApp (72% / +24%), Voice Call (67% / +19%), Incentive Link (79% / +31%).
- **Segment Impact [Retry]**:
  - Top segments where Retry shows highest incremental uplift:
    1. Insufficient Funds (1-2 attempts): `+28.3%` [High impact]
    2. Salary Window (T+1 to T+3): `+25.7%` [High impact]
    3. First Time Failures: `+22.1%` [Medium impact]
    4. High Historic Payer Score: `+18.9%` [Medium impact]
    5. Small Ticket (< ₹2,000): `+12.4%` [Low impact]
- **Timing Intelligence Card**:
  - Recovery probability over time hazard curve with peak at 18h (`72%`). Annotation: "Recommended action: Retry in 18 hours. Issuer success rate peaks at 72% in this window."
- **Network Prior Card**:
  - Razorpay network-scale intelligence visual blending Merchant A (200 data points) & Merchant B (2,000 data points) → Signal Contribution: `70% Network`, `30% Merchant`. Explanation of cold start benefit.
- **Uplift Model Performance**:
  - AUUC: `0.87`, Qini: `0.31`
  - Confidence & Calibration: Median Decision Confidence `91%`, Conformal Coverage `95.1%` (95% target).
- **Key Insights Panel**: Bullet summary of causal takeaways.

### Screen 4: Recovery Cases Ledger & Details (`/recovery-cases`)
- **Top Metrics**: Total Cases (12,842), Recovered Cases (4,931 / 38.4%), Total Recovered (₹7.82L), Avg Recovery Time (2.7 days), Incremental Recovery (₹2.14L).
- **Filters Row**: Date Range, Domain (All), Amount (All), Action (All), Outcome (All), Issuer (All), Confidence (All), Decision Source (All), Reset button, Export CSV.
- **Tab Badges**: All 12,842, Detected 1,582, Scored 2,514, Ready 1,211, Approved 1,200, Actioned 1,734, Recovered 4,931, Failed 1,210, Escalated 708, Monitoring 385.
- **Table Structure**: Rich data grid with sortable headers, status badges, and side panel drawer trigger.

### Screen 5: Analytics Deep Dive Dashboard (`/analytics`)
- **Top Metrics**: Total Recovered by WAPSI (₹7.82L vs baseline ₹5.68L / +37.7%), Incremental Recovery (₹2.14L), Total Cases (12,842), Avg Recovery Time (2.7 days / -0.6 days).
- **WAPSI vs Baseline Comparison Matrix**:
  - Recovered: WAPSI ₹7.82L vs Baseline ₹5.68L (Difference: +₹2.14L / +37.7%)
  - Attempts: WAPSI 1,842 vs Baseline 3,104 (Difference: -1,262 / +40.7% efficiency)
  - Contacts: WAPSI 742 vs Baseline 1,921 (Difference: -1,179 / +61.4% fewer contacts)
  - ₹ / Attempt: WAPSI ₹425 vs Baseline ₹183 (Difference: +₹242 / +132.2%)
  - ₹ / Contact: WAPSI ₹1,054 vs Baseline ₹296 (Difference: +₹758 / +256.1%)
- **Recovery Over Time Chart**: Line chart with WAPSI vs Baseline curves.
- **Donut Charts**: Recovery by Domain & Outcome Distribution.
- **Recovery Funnel**: Funnel graph showing step-by-step conversion.
- **Interactive Recovery Simulator**:
  - Slider 1: Expected Contacts (Current: `742`, Range: 200 - 2,000)
  - Slider 2: Expected Retry Budget [Attempts] (Current: `1,842`, Range: 500 - 4,000)
  - Dynamic Projection: Expected Recovery (Est.) `₹7.82L`
  - Tradeoff Callouts: If contact volume increases by 20% → Projected Recovery `₹8.31L` (+₹0.49L / +6.3%); But if contacts decrease by 20% → Projected Recovery `₹6.95L` (-₹0.87L / -11.1%).
  - Reset Simulator button.

### Screen 6: Governance & Compliance Dashboard (`/governance`)
- **Tabs**: `Policy Controls` [Active], `Audit Trail`, `Fairness`, `Model Confidence`, `Security`.
- **Top 5 Metrics**: Policy Checks (12,842), Actions Blocked (214), Policy Violations (0), Manual Reviews (184), Autonomous Actions (92.6%).
- **Policy Controls Overview Table**:
  1. *NPCI Attempt Limit*: Max retry attempts allowed (3 / 4, 88% Compliance, Within Limit)
  2. *Contact Budget (TRAI)*: Max contacts per customer (2 / 5, 67% Compliance, Within Limit)
  3. *Merchant Daily Limit*: Max contacts per day (45 / 50, 90% Compliance, Within Limit)
  4. *Confidence Threshold*: Minimum confidence required (85% required, 96% Compliance, Healthy)
  5. *Recovery Window*: Allowed time window for action (Wider Window, 77% Compliance, Healthy)
  6. *Uplift Threshold*: Minimum uplift vs no action (3% required, 92% Compliance, Healthy)
- **Policy Health Gauge Card**: Radial gauge showing "100% Healthy", All policies active, No breaches detected, Actions Bounded by Policy 100%, Policies Passing Thresholds 5/5.
- **Audit Trail (Timeline)**: Steps for case `RX-48291`:
  - 10:32:14: Payment Failed (Subscription ₹8,999 failed for Customer 4821) [DETECTED]
  - 10:32:15: Root Cause Classified (Insufficient funds detected based on NPCI code) [CLASSIFIED]
  - 10:32:16: Causal Decision Generated (Uplift model selected Smart Retry with WhatsApp fallback) [DECIDED]
  - 10:32:18: Policy Validated (All 5 merchant + regulatory policies verified) [VALIDATED]
  - 11:47:00: WhatsApp Action Recovered (Full amount ₹8,999 paid successfully) [EXECUTED]
- **Fairness & Bias Monitor**:
  - Segment statistics: New vs Existing, High vs Low Value, Sleeper (Tier 1 vs 2/3).
  - Summary metrics: Disparate Impact (0.92, target > 0.80), Equal Opportunity (0.81, target > 0.80), Calibration Error (1.8%, target < 5%).
- **Trusted Execution Environment (TEE) Card**:
  - Prototype Enclave Security Boundary: Decision logic enclave, Customer data encrypted, All ML data leaves enclave, Tamper-proof execution, SAFE OUTPUT ONLY (No raw data leaves the enclave).

### Screen 7: Settings Configuration Dashboard (`/settings`)
- **Tabs**: `Merchant` [Active], `Recovery Policies`, `Channels`, `Integrations`, `Team & Access`.
- **Merchant Profile**: Acme Corp (Verified badge), Merchant ID `MRC_928374`, Business Type `Subscription & Billing`, Industry `SaaS`, Website `https://acmecorp.com`, Country `India`, Timezone `(GMT+05:30) Asia/Kolkata`.
- **Business Overview Metrics**: Active Customers 12,842, Monthly GMV ₹2.48Cr, Recovery Enabled 100%, AOV ₹1,932, Recovery Success Rate 68.2%, Est Incremental Recovery ₹2.14L.
- **Notification Preferences**: Toggles for Critical Alerts, Recovery Updates, Daily Summary, Policy Violations, System Updates; Checkboxes for Email, SMS, In-app.
- **Engine & Model Settings**:
  - Decision Confidence Threshold: `90%`
  - Minimum Uplift Threshold: `+5%`
  - Retry Attempt Limit: `4 attempts`
  - Contact Budget (per customer): `5 contacts`
  - Recovery Window: `24 - 72 hrs`
  - Model Version: `v2.3.1 (Latest)` [ACTIVE badge]
- **Data Retention & Privacy**: Dropdowns for Recovery Cases (24 Months), Audit Logs (36 Months), System Logs (12 Months), Analytics Data (24 Months) + Security statement.
