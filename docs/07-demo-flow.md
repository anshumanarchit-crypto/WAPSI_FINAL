# 07 — Interactive Demo Flow & Reactive State Architecture

The frontend contains a unified demo state powered by **Zustand (`demoStore.ts`)**. All screens react immediately when state changes occur.

## 1. Case Approval & Recovery Simulation Workflow
1. User navigates to **Recovery Center** (`/recovery-center`) or **Recovery Cases** (`/recovery-cases`).
2. User clicks on row `RX-48291` (Subscription payment failure, Amount: ₹8,999, Natural Recovery: 48%, Smart Retry Recovery: 72%, Uplift: +24%).
3. The **Case Intelligence Drawer** slides in from the right.
4. User reviews:
   - AI Recommended Action: Smart Retry (Tomorrow 10:30 AM).
   - Natural Recovery vs Treatment Comparison (+24% incremental uplift).
   - SHAP explanation feature importances.
   - Network evidence weighting (74% Network, 26% Merchant).
   - Policy Validation status (5/5 passed).
5. User clicks **"Approve"**:
   - Animated policy check sequence runs ("Verifying NPCI retry cap... Checking customer contact budget... Validating execution window... Passed!").
   - Case status updates to `APPROVED` and action is scheduled.
6. User clicks **"Simulate Recovery"** (Interactive Demo Action):
   - Case transitions to `RECOVERED`.
   - Notification toast displays: *"Payment for Case RX-48291 successfully recovered (₹8,999) via Smart Retry"*.
   - **Cross-Screen Reactions**:
     - *Overview Dashboard*: Total Recovered increases (`₹7.82L` → updated), Recovery Pulse point ticks up, AI opportunities decrements.
     - *Recovery Center*: Actions Ready decreases by 1, case moved to Actioned/Recovered.
     - *Recovery Cases Ledger*: Status updates with green `RECOVERED` badge.
     - *Analytics*: Total Recovered, ₹/Attempt and ₹/Contact refresh dynamically.
     - *Governance*: New verified Audit Log event appended to the Audit Trail timeline with timestamp and execution signature.

## 2. Interactive Analytics Simulation
1. User navigates to **Analytics** (`/analytics`).
2. User adjusts the **Recovery Simulator** sliders:
   - Slider 1: Expected Contacts (`200` to `2,000`).
   - Slider 2: Expected Retry Budget (`500` to `4,000`).
3. Real-time projection updates:
   - Total projected revenue recalculates dynamically using diminishing marginal returns formula.
   - Tradeoff pills recalculate (+20% contacts vs -20% contacts impact).

## 3. Interactive AI Copilot
1. User clicks **"Ask WAPSI AI"** in the sidebar or presses the AI trigger.
2. Copilot drawer opens with suggested enterprise prompts:
   - *"Why is recovery falling for Checkout domain?"*
   - *"Which cases should we target this afternoon?"*
   - *"Explain why No Action was selected for RX-48297"*
   - *"What is driving the +37.2% incremental uplift?"*
3. Clicking any prompt streams an intelligent, contextual causal response tied directly to WAPSI's underlying data.
