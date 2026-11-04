# WAPSI — PHASE 6: FINAL META WABA AUTHORIZATION REPORT

**Date:** 2026-11-03  
**Target App ID:** `963047183124334` (`WAPSI Payment Recovery`)  
**Target WABA ID:** `969727602419694`  
**Target Phone Number ID:** `1407090562487899` (`+1 555-***-8539`)  
**Business Settings System User ID:** `61595814315120`  
**Active Token User ID:** `122103630711527143`  
**Active Token Issue Timestamp:** `1793647795` (2026-11-03 00:59:55 IST)  
**Overall Verdict:** **NOT ESTABLISHED / BLOCKED (WABA container access fails with Code 100, Subcode 33)**

---

## 1. Executive Summary

A comprehensive, strictly read-only Graph API audit was executed to evaluate the active Meta token in `.env` following reported asset assignment updates in Meta Business Settings.

The evaluation inspected:
1. `GET /debug_token` granular scopes and `target_ids`.
2. `GET /me` app-scoped System User identification.
3. `GET /{waba_id}?fields=id,name` WABA object accessibility.
4. `GET /{waba_id}/phone_numbers` child telephone container access.
5. `GET /{waba_id}/assigned_users` account-level messaging task assignments.

**Findings:**  
While the active token authenticates successfully against Meta Graph API (`HTTP 200 OK`) and possesses application-level scopes (`whatsapp_business_management`, `whatsapp_business_messaging`), **WABA container asset authorization is NOT established**:
- `granular_scopes` contains **no `target_ids`** for WABA `969727602419694`.
- Direct queries to WABA `969727602419694` return **`HTTP 400 Bad Request`** (`GraphMethodException Code 100, Error Subcode 33`: "cannot be loaded due to missing permissions").
- Enumeration of child phone numbers and assigned users on WABA `969727602419694` are completely blocked with Subcode 33.
- Consequently, outbound message dispatch will be rejected by Meta Cloud API with `OAuthException Code 10: "Viewer cannot access the provided Paid Message Account 969727602419694"`.

---

## 2. Itemized Verification Results

| # | Inspection Checkpoint | Executed Graph API Call | HTTP Status | Observed Evidence | Verdict |
| :-: | :--- | :--- | :-: | :--- | :---: |
| **1** | **`debug_token` & Granular Scopes** | `GET /debug_token?input_token=...` | `200 OK` | `is_valid: true`, scopes present, but **`target_ids` is ABSENT** in `granular_scopes`. | **FAIL** |
| **2** | **App-Scoped System User ID (`/me`)** | `GET /v26.0/me` | `200 OK` | `id: "122103630711527143"`, `name: "WAPSI-WhatsApp-Integration"`. | **PASS** |
| **3** | **WABA Resource (`/969727602419694`)** | `GET /v26.0/969727602419694?fields=id,name` | `400 Bad Request` | `GraphMethodException Code 100, Subcode 33` (object cannot be loaded due to missing permissions). | **FAIL** |
| **4** | **WABA Phone Numbers** | `GET /v26.0/969727602419694/phone_numbers` | `400 Bad Request` | `GraphMethodException Code 100, Subcode 33` (child telephone container access blocked). | **BLOCKED / FAIL** |
| **5** | **WABA Assigned Users & Tasks** | `GET /v26.0/969727602419694/assigned_users` | `400 Bad Request` | `GraphMethodException Code 100, Subcode 33` (cannot read assigned users or tasks). | **BLOCKED / FAIL** |
| **6** | **Messaging Access Verification** | Evaluated across checks 1–5 | — | Zero account-level tasks or target WABA bindings exist for this token. | **FAIL** |

---

## 3. Deep-Dive Graph API Diagnostic Evidence

### Check 1: `GET /debug_token` & Granular Scopes Inspection
- **Call:** `GET https://graph.facebook.com/debug_token?input_token=<TOKEN>&access_token=<TOKEN>`
- **HTTP Status:** `200 OK`
- **Response Data Excerpt:**
  ```json
  {
    "data": {
      "app_id": "963047183124334",
      "type": "SYSTEM_USER",
      "application": "WAPSI Payment Recovery",
      "is_valid": true,
      "issued_at": 1793647795,
      "expires_at": 0,
      "scopes": [
        "whatsapp_business_management",
        "whatsapp_business_messaging",
        "public_profile"
      ],
      "granular_scopes": [
        {
          "scope": "whatsapp_business_management"
        },
        {
          "scope": "whatsapp_business_messaging"
        }
      ],
      "user_id": "122103630711527143"
    }
  }
  ```
- **Evidence Analysis:**  
  When an access token has authorized asset access to specific WABAs, Meta's Graph API embeds a `target_ids` field within `granular_scopes` (e.g., `"target_ids": ["969727602419694"]`). In the active token, `target_ids` is completely missing from both `whatsapp_business_management` and `whatsapp_business_messaging`.
- **Verdict:** **FAIL**

---

### Check 2: App-Scoped System User Identification (`GET /me`)
- **Call:** `GET https://graph.facebook.com/v26.0/me`
- **HTTP Status:** `200 OK`
- **Response Data:**
  ```json
  {
    "id": "122103630711527143",
    "name": "WAPSI-WhatsApp-Integration"
  }
  ```
- **Evidence Analysis:**  
  The token belongs to an App-Scoped System User with ID **`122103630711527143`** and display name `"WAPSI-WhatsApp-Integration"`.
- **Verdict:** **PASS** (Identity verified as System User `122103630711527143`)

---

### Check 3: WABA Resource Accessibility (`GET /969727602419694?fields=id,name`)
- **Call:** `GET https://graph.facebook.com/v26.0/969727602419694?fields=id,name,currency,timezone_id`
- **HTTP Status:** `400 Bad Request`
- **Response Data:**
  ```json
  {
    "error": {
      "message": "Unsupported get request. Object with ID '969727602419694' does not exist, cannot be loaded due to missing permissions, or does not support this operation. Please read the Graph API documentation at https://developers.facebook.com/docs/graph-api",
      "type": "GraphMethodException",
      "code": 100,
      "error_subcode": 33,
      "fbtrace_id": "AVqn9K08WevjLQFc87_HVN4"
    }
  }
  ```
- **Evidence Analysis:**  
  `GraphMethodException Code 100, Error Subcode 33` conclusively demonstrates that the active token does not possess read permissions on the target WABA container `969727602419694`.
- **Verdict:** **FAIL**

---

### Check 4: Child Phone Numbers Enumeration (`GET /969727602419694/phone_numbers`)
- **Call:** `GET https://graph.facebook.com/v26.0/969727602419694/phone_numbers`
- **HTTP Status:** `400 Bad Request`
- **Response Data:**
  ```json
  {
    "error": {
      "message": "Unsupported get request. Object with ID '969727602419694' does not exist, cannot be loaded due to missing permissions, or does not support this operation. Please read the Graph API documentation at https://developers.facebook.com/docs/graph-api",
      "type": "GraphMethodException",
      "code": 100,
      "error_subcode": 33,
      "fbtrace_id": "A2plL-ELg_AaEBjOazfktGu"
    }
  }
  ```
- **Evidence Analysis:**  
  While direct lookup of Phone Number `1407090562487899` succeeds (`HTTP 200 OK`, `status: CONNECTED`, `quality_rating: GREEN`), enumerating phone numbers through the WABA node fails completely. Container-level containment cannot be verified by this token.
- **Verdict:** **BLOCKED / FAIL**

---

### Check 5: WABA Assigned Users & Tasks (`GET /969727602419694/assigned_users`)
- **Call:** `GET https://graph.facebook.com/v26.0/969727602419694/assigned_users?fields=id,name,user_type,tasks,role`
- **HTTP Status:** `400 Bad Request`
- **Response Data:**
  ```json
  {
    "error": {
      "message": "Unsupported get request. Object with ID '969727602419694' does not exist, cannot be loaded due to missing permissions, or does not support this operation. Please read the Graph API documentation at https://developers.facebook.com/docs/graph-api",
      "type": "GraphMethodException",
      "code": 100,
      "error_subcode": 33,
      "fbtrace_id": "AT2pwjjYKGPrs6J5V1royzI"
    }
  }
  ```
- **Evidence Analysis:**  
  Because WABA node permissions are missing, inspecting assigned users and their tasks (`MANAGE`, `MESSAGING`) is entirely blocked.
- **Verdict:** **BLOCKED / FAIL**

---

### Check 6: Messaging Access Verification
- **Evidence Analysis:**  
  Under Meta WhatsApp Cloud API architecture, outbound messaging requires that the token holder have account-level permissions on the parent Paid Message Account (WABA).
  - Check 1 confirms `target_ids` is missing.
  - Check 3 confirms WABA node returns `HTTP 400 Subcode 33`.
  - Check 5 confirms assigned user tasks cannot be loaded.
  - Secondary check `GET /me/assigned_whatsapp_business_accounts` returns `{"data": []}`.
- **Verdict:** **FAIL**

---

## 4. Multi-Perspective Analysis: App-Scoped vs. Business Settings Identity

The prompt notes:
> *"Do not assume that the app-scoped System User ID must numerically equal the Business Settings ID. Do not rely solely on `/me/assigned_whatsapp_business_accounts`. Compare the WABA resource, assigned users, granular scope targets and UI assignment evidence."*

Following this guidance rigorously:

1. **Even if `122103630711527143` is an App-Scoped ID (ASID) alias for Business Settings user `61595814315120`:**  
   If the underlying System User had Full Access on WABA `969727602419694`, direct node queries to `GET /969727602419694?fields=id,name` would resolve with `HTTP 200 OK` regardless of ASID translation.
2. **Comparison with WABA Node Behavior:**  
   `GET /969727602419694` fails with `Subcode 33` ("cannot be loaded due to missing permissions"). This is not an ID aliasing artifact; it is an explicit Meta authorization denial on the WABA object itself.
3. **Comparison with `granular_scopes`:**  
   `granular_scopes` does not contain `target_ids: ["969727602419694"]`.
4. **Conclusion on Asset Assignment:**  
   In Meta Business Manager:
   - Either the asset assignment was applied to a different System User than the one used to generate this token.
   - Or when generating the System User token, the WABA asset was not selected / attached to the token generation scope.
   - Or the assignment in the Meta Business Settings UI was not confirmed/saved.

---

## 5. Final Verdict & Operational Gate

### **IS OUTBOUND WHATSAPP AUTHORIZATION ESTABLISHED?**

# **NO.**

### Operational Impact
Executing an outbound message dispatch via `POST /{version}/1407090562487899/messages` with this token will fail with:
```json
{
  "error": {
    "message": "(#10) Viewer cannot access the provided Paid Message Account 969727602419694",
    "type": "OAuthException",
    "code": 10
  }
}
```

### Safety Status
- Outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` strictly remains in **`PENDING_APPROVAL`**.
- Zero messages have been dispatched.
- Zero payment links have been created.
- Background workers remain halted.

