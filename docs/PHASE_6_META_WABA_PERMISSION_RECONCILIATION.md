# WAPSI — PHASE 6: META WABA PERMISSION RECONCILIATION REPORT

**Audit Timestamp:** 2026-11-02T22:10:00+05:30 (16:40:00 UTC)  
**Target Environment:** Development Sandbox / Meta WhatsApp Cloud API (`v26.0`)  
**Database Posture:** `PENDING_APPROVAL` (Preserved, Zero Mutations)  
**Safety Protocol:** Strict Read-Only Audit (Zero Message Sends, Zero Key Revocations, Zero Link Creations)  
**Final Verdict:** **BLOCKED** (Pending Meta UI Asset Assignment & Token Refresh)  

---

## 1. Executive Summary

During the Phase 6 external sandbox integration, outbound message dispatch to Meta's WhatsApp Cloud API endpoint returned:
```text
HTTP 400 — OAuthException Code 10: (#10) Viewer cannot access the provided Paid Message Account 969727602419694
```

A comprehensive read-only diagnostic was conducted across Meta Graph API (`/debug_token`, `/me`, `/{app_id}`, `/{user_id}`, `/{phone_number_id}`, and `/{waba_id}`).

### Key Audit Findings:
1. **The Active Token is Valid but Unassigned:** The active bearer token loaded from `.env` is a valid, permanent System User token issued by App `963047183124334` (`WAPSI Payment Recovery`). However, its attached WhatsApp accounts list (`/assigned_whatsapp_business_accounts`) is completely **empty (`[]`)**.
2. **Two System User Identities Identified:**
   - **Token Identity (Graph API / ASID):** `122103630711527143` (Name: `WAPSI-WhatsApp-Integration`).
   - **Screenshot Identity (Business Manager):** `61595814315120` (Name: `WAPSI-WhatsApp-Integration`).
   - Both entities share the exact display name `WAPSI-WhatsApp-Integration`, but represent distinct ID handles within Meta's ecosystem (App-Scoped ID vs Business-Scoped System User ID).
3. **Exact WABA & Phone Relationship Verified:**
   - Phone Number ID `1407090562487899` (`+1 555-214-8539`) is an active, verified test sender with `GREEN` quality rating.
   - Meta's backend authoritatively maps Phone Number ID `1407090562487899` to **WABA ID `969727602419694`**.
   - Because neither System User has been granted asset access to WABA `969727602419694` with `whatsapp_business_messaging` permissions, Meta fails closed with HTTP 400 Code 10.
4. **Zero Production Contamination & Frozen State:** Outbox job `5a6587ab-2601-4017-b396-48e3d2fc2fda` remains safely frozen in `PENDING_APPROVAL`. No database mutations or token revocations were executed.

---

## 2. Active Token Identity & Scopes Inspection

Inspection performed via `GET https://graph.facebook.com/debug_token?input_token=<REDACTED>&access_token=<REDACTED>`:

| Attribute | Observed Value | Assessment |
| :--- | :--- | :---: |
| **Token Validity** | `is_valid: true` | Active & Authentic |
| **Token Type** | `SYSTEM_USER` | Valid Non-Expiring System Token |
| **Issuing App ID** | `963047183124334` | Matches "WAPSI Payment Recovery" |
| **Application Name** | `WAPSI Payment Recovery` | Verified App Context |
| **Token Owner User ID**| `122103630711527143` | App-Scoped Identity of System User |
| **Expiration (`expires_at`)** | `0` (Never expires) | Permanent Developer Token |
| **Assigned Scopes** | `whatsapp_business_management`<br>`whatsapp_business_messaging`<br>`public_profile` | Required messaging scopes present |
| **Missing Scopes** | `business_management` | Absent (Optional for messaging; needed for multi-asset management) |
| **Granular Scopes (`target_ids`)** | `whatsapp_business_management`: `None`<br>`whatsapp_business_messaging`: `None` | **CRITICAL GAP:** Zero WABA IDs bound |
| **Assigned WABA Assets** | `GET /122103630711527143/assigned_whatsapp_business_accounts` $\rightarrow$ `{"data": []}` | **CRITICAL GAP:** Empty asset list |

---

## 3. App, WABA, and Phone Number Relationship

| Entity | Identifier | Read API Status | Verified Metadata / Details |
| :--- | :--- | :---: | :--- |
| **Meta App** | `963047183124334` | `HTTP 200` | Name: `WAPSI Payment Recovery`<br>Category: Business / Developer |
| **Phone Number** | `1407090562487899` | `HTTP 200` | Display: `+1 555-214-8539`<br>Verified Name: `Test Number`<br>Status: `CONNECTED`<br>Quality: `GREEN`<br>Code Status: `VERIFIED` |
| **Target WABA** | `969727602419694` | `HTTP 400` (Code 100/33) | Blocked due to missing permission: `"Viewer cannot access the provided Paid Message Account"` |
| **Phone-to-WABA Mapping** | Live API Proof | `HTTP 400` (Code 10) | Confirmed by Meta error payload: Phone `1407090562487899` belongs to Paid Message Account `969727602419694`. |

---

## 4. System User Identity Discrepancy & Reconciliation

Two distinct System User IDs were evaluated:

1. **User ID `122103630711527143` (Owner of Active `.env` Token):**
   - Query: `GET /v26.0/122103630711527143` $\rightarrow$ `{"id": "122103630711527143", "name": "WAPSI-WhatsApp-Integration"}`
   - Edge `assigned_whatsapp_business_accounts`: Returns `{"data": []}` (HTTP 200).
   - This identity owns the active token. It has zero WABAs assigned.

2. **User ID `61595814315120` (Shown in Meta Business Settings UI):**
   - Query: `GET /v26.0/61595814315120` $\rightarrow$ `{"id": "61595814315120", "name": "WAPSI-WhatsApp-Integration"}`
   - Edge `assigned_whatsapp_business_accounts`: Returns `HTTP 403 - Code 200 (Missing Permissions)` because the token owned by `122103630711527143` lacks administrative rights over `61595814315120`.

### Architectural Root Cause:
In Meta Business Manager:
- `61595814315120` is the **Business-Scoped System User ID** visible in the Business Settings UI under **Users > System Users**.
- `122103630711527143` is the **App-Scoped ID (ASID)** generated when token credentials were created for App `963047183124334`.
- Because the WABA asset `969727602419694` was **never assigned** to the System User under **Assigned Assets** in the Business Manager UI, the token lacks authorization to read WABA `969727602419694` or dispatch messages through Phone Number `1407090562487899`.

---

## 5. Exact Step-by-Step Meta UI Remediation Instructions

Follow these exact steps in the Meta Business Manager UI to assign the WABA asset and bind the permissions:

### Step 1: Open Meta Business Settings
1. Navigate to **Meta Business Settings**: [https://business.facebook.com/settings](https://business.facebook.com/settings)
2. Ensure the active Business Portfolio selected in the top-left dropdown is the portfolio containing App `963047183124334` (`WAPSI Payment Recovery`).

### Step 2: Assign the WABA Asset to System User `61595814315120`
1. In the left navigation bar, go to **Users** > **System Users**.
2. Click on the System User named **`WAPSI-WhatsApp-Integration`** (verify ID matches `61595814315120`).
3. Click the **Assign Assets** button.
4. In the modal dialog:
   - On the left sidebar under *Select Asset Type*, click **WhatsApp Accounts**.
   - In the asset list, locate the WhatsApp Business Account with exact ID **`969727602419694`** (do not rely on display name alone; confirm the account ID matches `969727602419694`).
   - On the right pane under *Permissions*, toggle ON **Full Control** (or ensure both **Manage WhatsApp Business Account** and **Send Messages** are enabled).
5. Click **Save Changes**.

### Step 3: Verify the Sending Phone Number Inside the WABA
1. In the left navigation bar, go to **Accounts** > **WhatsApp Accounts**.
2. Select WABA **`969727602419694`**.
3. Click on the **WhatsApp Manager** button (or open the **Phone Numbers** tab).
4. Verify that Phone Number `+1 555-214-8539` (Phone Number ID: `1407090562487899`) is listed as active.

### Step 4: Generate a Refreshed System User Token
> [!IMPORTANT]
> In Meta Cloud API, tokens generated prior to asset assignment often do not dynamically inherit newly assigned granular asset scopes. A fresh token ensures target asset IDs are properly bound.

1. Return to **Users** > **System Users** > **`WAPSI-WhatsApp-Integration`** (`61595814315120`).
2. Click **Generate New Token**.
3. Select App: **`WAPSI Payment Recovery`** (`963047183124334`).
4. Select Token Expiration: **Never**.
5. Select the following scopes:
   - `whatsapp_business_messaging` (Required)
   - `whatsapp_business_management` (Required)
   - `business_management` (Recommended if available in the list)
6. Click **Generate Token** and copy the generated token string.
7. Update the project `.env` file:
   ```bash
   WHATSAPP_ACCESS_TOKEN=<newly_generated_token>
   ```

### Step 5: Run Read-Only Verification
Execute the non-mutating verification script to confirm WABA asset binding:
```powershell
python scripts/reconcile_meta_waba_permissions.py
```
Expected verification evidence:
- `GET /v26.0/969727602419694` returns `HTTP 200 OK`.
- `GET /me/assigned_whatsapp_business_accounts` contains WABA ID `969727602419694`.

---

## 6. Safety Attestation & State Freeze

During this reconciliation audit:
- **ZERO** WhatsApp messages were dispatched.
- **ZERO** Razorpay payment links were created.
- **ZERO** payments were executed.
- **ZERO** database rows were mutated or deleted.
- **ZERO** tokens were revoked or automatically modified.
- Existing Outbox Job `5a6587ab-2601-4017-b396-48e3d2fc2fda` remains safely in `PENDING_APPROVAL` with `requires_operator_approval = True`.

---

## 7. Final Verdict

$$\mathbf{VERDICT:\ BLOCKED}$$

**Blocker Description:** Meta System User `WAPSI-WhatsApp-Integration` (`61595814315120` / ASID `122103630711527143`) has not been assigned the WhatsApp Business Account asset `969727602419694` in Meta Business Manager. Outbound WhatsApp dispatch cannot proceed until manual UI asset assignment and token refresh in Section 5 are completed.

