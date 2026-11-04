# WAPSI Synthetic Causal Recovery Dataset — Data Dictionary
### Razorpay AI Buildathon 2026 — Track 3

This document defines the schema, data types, physical constraints, business context, and causal data-generating process (DGP) for the WAPSI synthetic tabular payment recovery environment.

---

## 1. Public Observed Schema (Exposed to Training Pipeline)

Each row represents **one payment failure or checkout abandonment recovery opportunity (`case_id`)**.

| Field Name | Type | Range / Values | Description & Business Context | Causal Role |
|---|---|---|---|---|
| `case_id` | `string` | Unique alphanumeric (e.g. `case_3f9a12bc001a`) | Primary key for the recovery opportunity instance. | Identifier |
| `merchant_id` | `string` | Categorical (e.g. `merch_urban_mart`, `merch_cloud_scale`) | Account identifier of the merchant where checkout failed. | Stratification / Cluster |
| `customer_id` | `string` | Categorical (e.g. `cust_498124`) | Unique customer identifier across repeat transactions. | Entity Tracking |
| `domain` | `string` | `ecommerce`, `b2b_saas`, `travel`, `education`, `gaming`, `subscription`, `food_delivery` | Industry vertical of the merchant. Determines ticket distribution, urgency, and communication tolerance. | Confounder / Effect Modifier |
| `amount` | `float` | ₹49.00 to ₹150,000.00 (log-normal distributed) | Total order transaction amount in Indian Rupees (INR). Strictly positive. | Confounder / Effect Modifier |
| `decline_reason` | `string` | `insufficient_funds`, `technical_gateway_error`, `authentication_failed`, `upi_pin_timeout`, `card_limit_exceeded`, `user_cancelled_checkout`, `bank_downtime` | Low-level gateway/issuer decline reason code. | Major Effect Modifier |
| `attempts_used` | `integer` | `1`, `2`, `3`, `4` | Number of payment attempts already attempted by user in current checkout session. | Friction Indicator |
| `account_age_days` | `integer` | `1` to `2500` days | Age of the customer's account with the merchant in days. | Loyalty / Baseline Trust |
| `previous_failures` | `integer` | `0` to `20+` | Historical count of payment failures recorded for this customer in the past 90 days. | Risk / Friction History |
| `previous_recoveries` | `integer` | `0` to `20+` | Historical count of successfully recovered payments for this customer in the past 90 days. | Recovery Propensity |
| `prior_recovery_rate` | `float` | `0.0000` to `1.0000` | Historical recovery ratio: `previous_recoveries / (previous_failures + previous_recoveries)`. Set to `0.0` for new users. | Confounder / Responsiveness |
| `day_of_week` | `integer` | `0` (Monday) to `6` (Sunday) | Day of week when transaction failure occurred. | Temporal Confounder |
| `hour` | `integer` | `0` to `23` (24-hour format) | Hour of the day in Indian Standard Time (IST) when failure occurred. | Temporal / DND Confounder |
| `issuer` | `string` | `HDFC`, `ICICI`, `SBI`, `AXIS`, `KOTAK`, `CITI`, `OTHER` | Acquiring / issuing banking institution processing the card/UPI rail. | Rail Health / Timing Latency |
| `bin_bucket` | `string` | `classic`, `platinum`, `signature`, `corporate`, `rupay`, `upi_standard` | Card tier or payment rail classification derived from Card BIN or VPA. | Purchasing Power Proxy |
| `fatigue_score` | `float` | `0.0000` to `1.0000` | Continuous customer outreach fatigue indicator. High fatigue strongly penalizes interactive channels (WhatsApp, voice). | Dynamic Friction Barrier |
| `treatment` | `string` | `no_action`, `retry_only`, `whatsapp_nudge`, `voice_call`, `email`, `incentive_link` | Factual intervention assigned to this recovery case by historical policy. | **Observed Treatment ($A$)** |
| `recovered` | `integer` | `0` (Failed/Abandoned) or `1` (Successfully Recovered) | Realized payment outcome under observed treatment. Satisfies SUTVA: $Y = Y(A)$. | **Primary Factual Target ($Y$)** |
| `time_to_recovery_hours` | `float` | `0.01` to `72.00` (or `NaN` if unrecovered) | Time elapsed from failure timestamp to successful payment settlement in hours. | **Survival Duration ($T$)** |

---

## 2. Recovery Action Space (`treatment`)

| Action Name | Channel | Direct Cost (INR) | Friction Penalty | Description | Optimal Use Cases |
|---|---|---|---|---|---|
| `no_action` | None | ₹0.00 | None | Silent organic control. Customer retries spontaneously. | High baseline self-cure, repeat loyal buyers, low friction. |
| `retry_only` | Gateway Reroute | ₹0.15 | Zero customer contact | Background reroute to healthy bank switch without disturbing user. | `technical_gateway_error`, `bank_downtime`, HDFC/ICICI rails. |
| `whatsapp_nudge` | WhatsApp Business | ₹0.85 | Low | Rich interactive 1-click payment link deep-linking into UPI/wallet. | `upi_pin_timeout`, `authentication_failed`, mobile checkout. |
| `voice_call` | Automated IVR | ₹3.50 | High (irritation on low tickets) | Outbound automated voice assist with keypad guided recovery. | High-ticket ($> ₹8,000$), B2B SaaS, corporate BINs, daytime. |
| `email` | Transactional Email | ₹0.05 | Very low | Detailed payment invoice retry link with 24-hour expiration. | `b2b_saas`, `education`, desktop renewals, high account age. |
| `incentive_link` | WhatsApp / SMS | ₹2.50 | Low | Direct link offering micro-discount (3-5%) or BNPL alternative. | `user_cancelled_checkout`, price hesitation, ecommerce. |

---

## 3. Hidden Potential Outcomes (Ground Truth Evaluation Dataset Only)

These columns are generated internally by the causal DGP to enable exact mathematical validation of ITE / CATE estimation error, Qini curves, AUUC, and policy regret. **They are strictly excluded from the training dataset.**

| Field Name | Type | Description |
|---|---|---|
| `p_no_action` | `float` | True latent baseline recovery probability $p_0(x) = \mathbb{P}(Y(\text{no\_action}) = 1 \mid X=x)$ |
| `p_retry_only` | `float` | True latent recovery probability under `retry_only` |
| `p_whatsapp_nudge` | `float` | True latent recovery probability under `whatsapp_nudge` |
| `p_voice_call` | `float` | True latent recovery probability under `voice_call` |
| `p_email` | `float` | True latent recovery probability under `email` |
| `p_incentive_link` | `float` | True latent recovery probability under `incentive_link` |
| `tau_retry_only` | `float` | True individual treatment effect $\tau_{\text{retry}}(x) = p_{\text{retry}}(x) - p_0(x)$ |
| `tau_whatsapp_nudge` | `float` | True individual treatment effect $\tau_{\text{whatsapp}}(x) = p_{\text{whatsapp}}(x) - p_0(x)$ |
| `tau_voice_call` | `float` | True individual treatment effect $\tau_{\text{voice}}(x) = p_{\text{voice}}(x) - p_0(x)$ |
| `tau_email` | `float` | True individual treatment effect $\tau_{\text{email}}(x) = p_{\text{email}}(x) - p_0(x)$ |
| `tau_incentive_link` | `float` | True individual treatment effect $\tau_{\text{incentive}}(x) = p_{\text{incentive}}(x) - p_0(x)$ |
| `y_no_action` | `integer (0/1)` | Realized potential outcome $Y(\text{no\_action})$ |
| `y_retry_only` | `integer (0/1)` | Realized potential outcome $Y(\text{retry\_only})$ |
| `y_whatsapp_nudge` | `integer (0/1)` | Realized potential outcome $Y(\text{whatsapp\_nudge})$ |
| `y_voice_call` | `integer (0/1)` | Realized potential outcome $Y(\text{voice\_call})$ |
| `y_email` | `integer (0/1)` | Realized potential outcome $Y(\text{email})$ |
| `y_incentive_link` | `integer (0/1)` | Realized potential outcome $Y(\text{incentive\_link})$ |
| `t_<action>` | `float` | Realized potential latency in hours under each action |
| `optimal_treatment` | `string` | Oracle optimal action $\text{argmax}_{a} p_a(x)$ |
| `oracle_max_uplift` | `float` | Oracle maximum achievable treatment uplift $\max_{a} \tau_a(x)$ |
| `customer_archetype` | `string` | Causal archetype classification: `always_taker`, `persuadable`, `defier`, `never_taker` |

---

## 4. Latent Causal Archetypes

- **Always-Takers (Self-Curers)**: Customers who will complete their payment organically without intervention ($Y(0)=1, Y(\text{best})=1$). Nudging them wastes budget and risks friction.
- **Persuadables (True Targets)**: Customers who would abandon unless reached by the right tailored intervention ($Y(0)=0, Y(\text{best})=1$). This is where causal AI generates net revenue uplift.
- **Defiers (Friction Drops)**: Customers who would have self-cured, but become annoyed by aggressive communication ($Y(0)=1, Y(\text{action})=0$), e.g. receiving a voice call for a ₹199 order at night.
- **Never-Takers (Doomed Cases)**: Cases where payment cannot be recovered under any channel ($Y(0)=0, Y(a)=0$), e.g. frozen bank account, permanent fraud block.
