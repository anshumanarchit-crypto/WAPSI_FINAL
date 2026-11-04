# WAPSI Causal Decision Engine — Frontend API Contract
**Razorpay AI Buildathon 2026 | Track 3: Autonomous & Advisory Recovery Router**  
**API Version**: `1.0.0` | **Base URL**: `http://localhost:8000` | **Interactive Docs**: [`/docs`](http://localhost:8000/docs)

---

## 1. Overview for Frontend Engineers

WAPSI (**W**hat **A**ction **P**revents **S**ubscription/Payment **I**ssues) is an **advisory causal decision engine**.

When a payment fails on Razorpay checkout or recurring billing, the frontend / backend passes the transaction covariates to WAPSI. WAPSI calculates:
1. **Which intervention produces the highest incremental recovery** (e.g. WhatsApp 1-Click vs Instant Retry vs Merchant Discount).
2. **When recovery is temporally most likely** (`0-24h`, `24-48h`, `48-72h`, `72h+`).
3. **Why the action was chosen** (exact mathematical TreeSHAP feature drivers).
4. **Historical precedent evidence & counter-evidence** (most similar past transactions and whether they recovered).
5. **Statistical safety gate** (whether the case is safe for automated execution or requires human review).

> **CRITICAL ARCHITECTURAL RULE**:
> This API is **strictly advisory / recommendation-only**. Calling this API **does not** send real WhatsApp messages, execute real bank retries, or trigger real payments.

---

## 2. API Endpoints Summary

| Method | Endpoint | Description | Auth |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/recovery/predict` | **Primary Endpoint**: Evaluates failure & returns optimal recovery recommendation | None |
| `GET` | `/health` | Healthcheck & model readiness probe | None |
| `GET` | `/api/v1/model/info` | Public model metadata, supported actions & calibration levels | None |

---

## 3. Primary Endpoint: `POST /api/v1/recovery/predict`

### 3.1 Request Payload

```json
{
  "case_id": "CASE_123",
  "merchant_id": "M001",
  "domain": "subscription",
  "amount": 4999.0,
  "decline_reason": "insufficient_funds",
  "attempts_used": 1,
  "account_age_days": 730,
  "previous_failures": 3,
  "previous_recoveries": 2,
  "prior_recovery_rate": 0.67,
  "day_of_week": 2,
  "hour": 11,
  "issuer": "HDFC",
  "bin_bucket": "classic",
  "fatigue_score": 0.10
}
```

#### Field Specifications:
| Field | Type | Required? | Constraints | Example / Description |
| :--- | :--- | :---: | :--- | :--- |
| `case_id` | `string` | Optional | Auto-generated if omitted | `"CASE_123"` — Unique failure reference |
| `merchant_id` | `string` | Optional | Default `"merch_default"` | `"M001"` — Merchant account identifier |
| `domain` | `string` | **Required** | `ecommerce`, `subscription`, `b2b_saas`, `food_delivery`, `travel`, `education`, `gaming` | `"subscription"` — Merchant category |
| `amount` | `number` | **Required** | `> 0.0` | `4999.0` — Transaction value in INR |
| `decline_reason` | `string` | **Required** | Standard decline reason code | `"insufficient_funds"`, `"upi_pin_timeout"`, `"bank_downtime"` |
| `attempts_used` | `integer` | Optional | `ge=1`, default `1` | `1` — Attempts already made |
| `prior_recovery_rate` | `number` | Optional | `0.0` to `1.0`, default `0.50` | `0.67` — Customer historical recovery rate |
| `fatigue_score` | `number` | Optional | `0.0` to `1.0`, default `0.10` | `0.10` — Communication fatigue level |
| `hour` | `integer` | Optional | `0` to `23`, default `14` | `11` — Hour of transaction (IST) |
| `issuer` | `string` | Optional | Default `"HDFC"` | `"HDFC"`, `"ICICI"`, `"SBI"`, `"AXIS"`, `"KOTAK"` |
| `bin_bucket` | `string` | Optional | Default `"classic"` | `"classic"`, `"platinum"`, `"corporate"`, `"rupay"` |

---

### 3.2 Full Response Payload (HTTP 200 OK)

```json
{
  "case_id": "CASE_123",
  "decision_id": "dec_8f2b7a91c0e3",
  "recommended_action": "whatsapp_nudge",
  "uplift": 0.3885,
  "action_scores": {
    "retry_only": 0.143,
    "whatsapp_nudge": 0.3885,
    "voice_call": 0.1244,
    "email": 0.0973,
    "incentive_link": 0.1409
  },
  "timing": {
    "recommended_window": "0-24h",
    "hazard_by_window": {
      "0-24h": 0.9855,
      "24-48h": 0.0076,
      "48-72h": 0.007,
      "72h+": 0.0
    }
  },
  "confidence": 0.8063,
  "explanation": {
    "top_reasons": [
      {
        "feature": "decline_reason",
        "value": "insufficient_funds",
        "impact": 0.6275
      },
      {
        "feature": "prior_recovery_rate",
        "value": 0.67,
        "impact": 0.4435
      },
      {
        "feature": "account_age_days",
        "value": 730,
        "impact": 0.3949
      },
      {
        "feature": "fatigue_score",
        "value": 0.10,
        "impact": -0.2924
      }
    ],
    "top_positive_features": [
      {
        "feature": "decline_reason",
        "value": "insufficient_funds",
        "impact": 0.6275
      }
    ],
    "top_negative_features": [
      {
        "feature": "fatigue_score",
        "value": 0.10,
        "impact": -0.2924
      }
    ]
  },
  "precedents": [
    {
      "case_id": "case_03f8f08eb4aa",
      "action": "whatsapp_nudge",
      "recovered": true,
      "similarity": 0.842,
      "time_to_recovery_hours": 0.27,
      "domain": "subscription",
      "decline_reason": "insufficient_funds",
      "issuer": "HDFC",
      "amount": 4999.0
    },
    {
      "case_id": "case_034637fa86c1",
      "action": "whatsapp_nudge",
      "recovered": true,
      "similarity": 0.796,
      "time_to_recovery_hours": 1.15,
      "domain": "subscription",
      "decline_reason": "insufficient_funds",
      "issuer": "HDFC",
      "amount": 4500.0
    }
  ],
  "counter_evidence": false,
  "network_prior": {
    "network_uplift": 0.3521,
    "merchant_uplift": 0.3885,
    "merchant_observations": 30,
    "merchant_weight": 0.2308,
    "combined_uplift": 0.3605
  },
  "bandit": {
    "selected_action": "whatsapp_nudge",
    "sampled_rewards": {
      "no_action": 295.25,
      "retry_only": -157.15,
      "whatsapp_nudge": 511.63,
      "voice_call": -468.15,
      "email": -4202.26,
      "incentive_link": -451.54
    },
    "expected_rewards": {
      "no_action": 263.04,
      "retry_only": -324.71,
      "whatsapp_nudge": 453.41,
      "voice_call": -426.22,
      "email": -4201.25,
      "incentive_link": -473.78
    }
  },
  "tee_status": "attested",
  "policy_status": "allowed",
  "policy_inputs": {
    "dnd_active": false,
    "frequency_capped": false,
    "conformal_gate": {
      "eligible_for_auto_action": true,
      "confidence": 0.8063,
      "calibration_status": "CALIBRATED_NOMINAL_90",
      "action": "whatsapp_nudge",
      "predicted_uplift": 0.3885,
      "prediction_interval": [
        0.2952,
        0.4819
      ],
      "conformal_score": 0.0934,
      "conformal_threshold": 0.1107,
      "reason": "Statistically calibrated: 90% conformal interval [29.52%, 48.19%] is strictly positive (lower bound >= 2.0%). Autonomous execution authorized."
    }
  }
}
```

---

## 4. UI Component Mapping Guide

Here is how each JSON field directly maps to frontend UI elements:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CASE #CASE_123                                [ DOMAIN: SUBSCRIPTION ]     │
├─────────────────────────────────────────────────────────────────────────────┤
│  RECOMMENDED ACTION:  WHATSAPP 1-CLICK NUDGE   [ +38.85% Uplift ]           │
│  TIMING WINDOW:       0 - 24 HOURS (98.6% Prob)                             │
│  SAFETY STATUS:       ● AUTO-ACTION AUTHORIZED (90% Conf)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  ACTION COMPARISON:                                                         │
│   - WhatsApp Nudge    : ████████████████████████ (+38.85%)  <-- WINNER      │
│   - Retry Only        : █████████                (+14.30%)                  │
│   - Incentive Link    : █████████                (+14.09%)                  │
│   - Voice Call Assist : ████████                 (+12.44%)                  │
│   - Email             : ██████                   (+9.73%)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  WHY WAPSI CHOSE THIS (SHAP Drivers):                                       │
│   [+] Decline Reason: insufficient_funds (+0.63)                            │
│   [+] Prior Recovery Rate: 67% (+0.44)                                      │
│   [-] Customer Fatigue: 0.10 (-0.29)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  SIMILAR HISTORICAL CASES (Grounding):                                      │
│   • Case #case_03f8... | Action: WhatsApp | Status: RECOVERED | Sim: 84.2%  │
│   • Case #case_0346... | Action: WhatsApp | Status: RECOVERED | Sim: 79.6%  │
│   Counter-Evidence Flag: FALSE (No historical failure contradictions)       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key UI Decision Rules:
1. **Displaying Uplift**:
   - Always display `uplift` as a percentage (e.g. `+38.85%`).
   - Clearly label it as **"Incremental Causal Uplift"** (NOT "Probability of Payment").
2. **Auto-Action vs Human Review Badge**:
   - Check `policy_inputs.conformal_gate.eligible_for_auto_action`:
     - If `true`: Show Green Badge: `"Auto-Action Authorized"`
     - If `false`: Show Orange Badge: `"Escalated for Human Review"` (Display reason from `policy_inputs.conformal_gate.reason`).
3. **TRAI DND Alert Banner**:
   - If `policy_inputs.dnd_active == true`, show informational banner:
     `"⚠️ Night Window (21:00 - 09:00 IST): Automated SMS / WhatsApp contact is restricted by TRAI rules."`
4. **Counter-Evidence Indicator**:
   - If `counter_evidence == true`, show cautionary callout:
     `"⚠️ Caution: Similar historical cases experienced high failure rates under this action."`

---

## 5. Standard Error Handling

All error responses adhere to a consistent structured schema:

```json
{
  "error": "Validation Error",
  "detail": "amount: Input should be greater than 0",
  "status_code": 422,
  "case_id": null
}
```

### Status Codes:
- `200 OK`: Valid prediction generated successfully.
- `422 Unprocessable Entity`: Request validation failed (e.g. negative amount, invalid fatigue score).
- `500 Internal Server Error`: Generic safe internal failure response (no stack trace or filesystem paths exposed).
