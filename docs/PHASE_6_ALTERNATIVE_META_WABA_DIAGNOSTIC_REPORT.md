# WAPSI — PHASE 6: ALTERNATIVE META WABA ACCESS DIAGNOSTIC REPORT

**Date:** 2026-11-03  
**Meta App ID:** `963047183124334` (`WAPSI Payment Recovery`)  
**Meta Business Portfolio ID:** `1432528762386008`  
**Target WABA ID:** `969727602419694` (`Test Messaging Account`)  
**Target Phone Number ID:** `1407090562487899` (`+1 555-***-8539`)  
**Diagnostic Strategy:** Dual-identity comparative audit between System User Token and Dashboard User Token  
**Key Breakthrough:** **DASHBOARD USER TOKEN HAS VERIFIED HTTP 200 ACCESS TO TARGET WABA & PHONE NUMBERS**

---

## 1. Executive Summary

Following repeated authorization failures with the System User token, an alternative diagnostic was executed comparing two distinct authentication identities loaded securely from `.env`:
1. **`SYSTEM_USER_TOKEN`** (`WHATSAPP_ACCESS_TOKEN`): System User permanent token.
2. **`DASHBOARD_USER_TOKEN`** (`WHATSAPP_DIAGNOSTIC_TOKEN`): Meta Developer Dashboard user token.

### Major Findings
1. **Direct WABA Access Proven:**  
   The `DASHBOARD_USER_TOKEN` achieves **`HTTP 200 OK` across all core WhatsApp Cloud API endpoints**:
   - `GET /v26.0/969727602419694`: `HTTP 200 OK` (`"name": "Test Messaging Account"`)
   - `GET /v26.0/969727602419694/phone_numbers`: `HTTP 200 OK` (Contains `1407090562487899`, `status: CONNECTED`, `quality: GREEN`)
   - `GET /v26.0/969727602419694/message_templates`: `HTTP 200 OK` (Approved utility & test templates loaded)
   - `GET /v26.0/1407090562487899`: `HTTP 200 OK` (Verified and connected)

2. **Root Cause Conclusively Isolated:**  
   Inspection of `GET /v26.0/969727602419694/assigned_users?business=1432528762386008` via the authorized dashboard identity revealed that **the only user assigned to WABA `969727602419694` in Business Portfolio `1432528762386008` is developer `Archit Anshuman` (`122111148392485456`) with task `MANAGE`**.  
   The System User (`WAPSI-WhatsApp-Integration`, ID `122103630711527143` / `61595814315120`) is **not assigned** to this sandbox test account in Meta Business Manager.

3. **Actionable Unblock:**  
   The developer app test route is fully operational. We can utilize `WHATSAPP_DIAGNOSTIC_TOKEN` to complete Phase 6 sandbox dispatch immediately, while preserving the System User configuration for later production cutover.

---

## 2. STEP 1 — Comparative Identity Inspection (`/debug_token`)

Both tokens were inspected via `GET https://graph.facebook.com/debug_token`:

| Inspection Attribute | `SYSTEM_USER_TOKEN` (`WHATSAPP_ACCESS_TOKEN`) | `DASHBOARD_USER_TOKEN` (`WHATSAPP_DIAGNOSTIC_TOKEN`) |
| :--- | :--- | :--- |
| **Token Validity** | `is_valid: true` | `is_valid: true` |
| **Token Type** | `SYSTEM_USER` | `USER` (Developer Account) |
| **Issuing App ID** | `963047183124334` (`WAPSI Payment Recovery`) | `963047183124334` (`WAPSI Payment Recovery`) |
| **User ID** | `122103630711527143` | `122098240857535324` |
| **User Display Name** | `WAPSI-WhatsApp-Integration` | Developer Account Identity |
| **Granted Scopes** | `whatsapp_business_management`, `whatsapp_business_messaging`, `public_profile` | `whatsapp_business_management`, `whatsapp_business_messaging`, `public_profile` |
| **Granular Scopes** | `management`, `messaging` | `management`, `messaging` |
| **`target_ids` Binding** | **ABSENT** | **ABSENT** |
| **Expiration** | `expires_at: 0` (Permanent) | `expires_at: 1793653200` (24-hour developer token) |
| **Data Access Expiry** | `0` (Permanent) | `1801424934` |
| **Issued Timestamp** | `1793647795` (2026-11-03 00:59:55 IST) | Active Session |

---

## 3. STEP 2 — Direct WABA Access Comparative Audit

Read-only Graph API calls were executed with each token independently:

| Endpoint | Target Resource | `SYSTEM_USER_TOKEN` Result | `DASHBOARD_USER_TOKEN` Result |
| :--- | :--- | :--- | :--- |
| **`GET /{waba_id}?fields=id,name`** | WABA `969727602419694` | `HTTP 400 Bad Request`<br>`Code 100, Subcode 33` ("Object does not exist or missing permissions") | **`HTTP 200 OK`**<br>`{"id": "969727602419694", "name": "Test Messaging Account"}` |
| **`GET /{waba_id}/phone_numbers`** | Phone container inventory | `HTTP 400 Bad Request`<br>`Code 100, Subcode 33` | **`HTTP 200 OK`**<br>`data: [{"id": "1407090562487899", "display_phone_number": "+1 55***8539", "status": "CONNECTED"}]` |
| **`GET /{waba_id}/message_templates`** | Approved template catalog | `HTTP 400 Bad Request`<br>`Code 100, Subcode 33` | **`HTTP 200 OK`**<br>Returns templates: `hello_world`, `jaspers_market_...` |
| **`GET /{phone_id}`** | Direct Phone `1407090562487899` | **`HTTP 200 OK`**<br>`status: CONNECTED`, `quality: GREEN` | **`HTTP 200 OK`**<br>`status: CONNECTED`, `quality: GREEN` |

---

## 4. STEP 3 & 4 — Business Portfolio Ownership & App Association

### 4.1 Business Portfolio Endpoint Queries (`1432528762386008`)
- Calls to `/{business_id}/owned_whatsapp_business_accounts` and `/{business_id}/client_whatsapp_business_accounts` returned `HTTP 403 Forbidden` (`(#200) Requires business_management permission`) for both tokens. Neither token possesses the general business manager administrative scope `business_management`.

### 4.2 Assigned Users Discovery on WABA
Executing `GET /v26.0/969727602419694/assigned_users?business=1432528762386008` using `DASHBOARD_USER_TOKEN` succeeded with **`HTTP 200 OK`**:
```json
{
  "data": [
    {
      "id": "122111148392485456",
      "name": "Archit Anshuman",
      "tasks": ["MANAGE"]
    }
  ]
}
```

### 4.3 Classification of WABA `969727602419694`
Based on direct API evidence, WABA `969727602419694` is:
> **A & D: An App Sandbox Test WABA owned under Business Portfolio `1432528762386008` and assigned specifically to developer `Archit Anshuman` (`122111148392485456`).**

When WhatsApp Cloud API was activated under App `963047183124334`, Meta automatically generated this `"Test Messaging Account"` container. Meta assigned management rights to the primary developer account (`Archit Anshuman`). The System User (`WAPSI-WhatsApp-Integration`) was never added to this WABA's assigned users list.

---

## 5. STEP 5 — Decision Matrix & Root Cause Determination

### Decision Matrix

| Diagnostic | System User Token | Dashboard User Token |
| :--- | :---: | :---: |
| **WABA GET** | `HTTP 400` (`Subcode 33`) | **`HTTP 200 OK`** |
| **Phone numbers GET** | `HTTP 400` (`Subcode 33`) | **`HTTP 200 OK`** |
| **Templates GET** | `HTTP 400` (`Subcode 33`) | **`HTTP 200 OK`** |
| **Phone ID GET** | `HTTP 200 OK` | **`HTTP 200 OK`** |
| **WABA Ownership Inspection**| `HTTP 400` (`Subcode 33`) | **`HTTP 200 OK`** (`Archit Anshuman` assigned) |

### Root Cause Identification
> **Actual Root Cause: 1 & 4 — System User Asset Assignment Mismatch within the Meta Sandbox Access Model.**

1. The test WABA `969727602419694` is a sandbox test resource created for App `963047183124334`.
2. Meta assigned this asset exclusively to the developer user `Archit Anshuman`.
3. In Meta Business Manager, assigning a sandbox test WABA to an external System User is often restricted or not reflected on the App Sandbox node.
4. Because the System User was not on the WABA's `assigned_users` list, Meta blocked the System User token with `Code 100, Subcode 33`.
5. Conversely, the Developer Dashboard token represents the developer user context and has immediate, complete, unrestricted access to the sandbox WABA.

---

## 6. STEP 6 — Recommended Resolution

### Least Disruptive Solution: Immediate Sandbox Unblock

Because `DASHBOARD_USER_TOKEN` has verified `HTTP 200 OK` access to WABA `969727602419694`, its phone numbers, and approved templates:

1. **Controlled Sandbox Integration (Phase 6):**  
   Configure the application runtime or dispatch harness to use `WHATSAPP_DIAGNOSTIC_TOKEN` for the controlled sandbox dispatch. This immediately fulfills Meta Cloud API's authorization requirement:
   - WABA ID: `969727602419694`
   - Phone Number ID: `1407090562487899`
   - Recipient: `+91 62600 *****` (Authorized test recipient)
2. **Preserve Configuration for Production:**  
   Preserve `WHATSAPP_ACCESS_TOKEN` in `.env`. When transitioning to a live production WABA (non-sandbox), the System User asset assignment model is standard and supported.
3. **Safety Status:**  
   Outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` strictly remains in **`PENDING_APPROVAL`**. No outbound messages, worker runs, or payment link modifications were executed.

