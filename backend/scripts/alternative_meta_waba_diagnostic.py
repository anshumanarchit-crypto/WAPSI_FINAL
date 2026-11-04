"""
WAPSI — Alternative Meta WABA Access Diagnostic Script
Executes read-only queries against Meta Graph API comparing:
1. SYSTEM_USER_TOKEN (WHATSAPP_ACCESS_TOKEN)
2. DASHBOARD_USER_TOKEN (WHATSAPP_DIAGNOSTIC_TOKEN)

Strict Safety:
- Strictly GET requests only.
- Never prints tokens, secrets, or full phone numbers.
- ZERO database mutations or message sends.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import dotenv
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
env_vars = dotenv.dotenv_values(env_path)

sys_token = env_vars.get("WHATSAPP_ACCESS_TOKEN", "").strip()
diag_token = env_vars.get("WHATSAPP_DIAGNOSTIC_TOKEN", "").strip()

api_version = env_vars.get("WHATSAPP_API_VERSION", "v26.0").strip()
waba_id = "969727602419694"
phone_id = "1407090562487899"
app_id = "963047183124334"
business_id = "1432528762386008"

tokens = {
    "SYSTEM_USER_TOKEN": sys_token,
    "DASHBOARD_USER_TOKEN": diag_token,
}

def mask_phone(phone_str: str) -> str:
    if not phone_str:
        return ""
    if len(phone_str) <= 7:
        return "****"
    return phone_str[:5] + "***" + phone_str[-4:]

def sanitize_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            if "phone" in k.lower() and isinstance(v, str):
                new_dict[k] = mask_phone(v)
            elif "token" in k.lower() or "secret" in k.lower():
                new_dict[k] = "[REDACTED]"
            else:
                new_dict[k] = sanitize_json(v)
        return new_dict
    elif isinstance(obj, list):
        return [sanitize_json(i) for i in obj]
    return obj

results: Dict[str, Any] = {
    "tokens": {},
    "waba_access": {},
    "business_portfolio": {},
    "app_associations": {},
}

with httpx.Client(timeout=15.0) as client:
    # -------------------------------------------------------------
    # STEP 1: Inspect tokens via /debug_token
    # -------------------------------------------------------------
    for label, tok in tokens.items():
        if not tok:
            results["tokens"][label] = {"error": "Token not found in .env"}
            continue
        try:
            r = client.get(
                "https://graph.facebook.com/debug_token",
                params={"input_token": tok, "access_token": tok},
            )
            resp = r.json() if r.status_code == 200 else {"raw": r.text}
            results["tokens"][label] = {
                "status_code": r.status_code,
                "data": sanitize_json(resp.get("data", resp)),
            }
        except Exception as e:
            results["tokens"][label] = {"error": str(e)}

    # -------------------------------------------------------------
    # STEP 2: Test direct WABA access with BOTH tokens
    # -------------------------------------------------------------
    endpoints_step2 = [
        ("waba_get", f"https://graph.facebook.com/{api_version}/{waba_id}?fields=id,name"),
        ("phone_numbers_get", f"https://graph.facebook.com/{api_version}/{waba_id}/phone_numbers?fields=id,display_phone_number,verified_name,status,quality_rating"),
        ("templates_get", f"https://graph.facebook.com/{api_version}/{waba_id}/message_templates"),
        ("phone_id_get", f"https://graph.facebook.com/{api_version}/{phone_id}?fields=id,display_phone_number,verified_name,status,quality_rating"),
    ]

    for label, tok in tokens.items():
        results["waba_access"][label] = {}
        headers = {"Authorization": f"Bearer {tok}"}
        for ep_key, url in endpoints_step2:
            try:
                r = client.get(url, headers=headers)
                try:
                    body = r.json()
                except Exception:
                    body = {"raw": r.text[:300]}
                results["waba_access"][label][ep_key] = {
                    "status_code": r.status_code,
                    "body": sanitize_json(body),
                }
            except Exception as e:
                results["waba_access"][label][ep_key] = {"error": str(e)}

    # -------------------------------------------------------------
    # STEP 3: Investigate Business Portfolio ownership
    # -------------------------------------------------------------
    endpoints_step3 = [
        ("owned_wabas", f"https://graph.facebook.com/{api_version}/{business_id}/owned_whatsapp_business_accounts"),
        ("client_wabas", f"https://graph.facebook.com/{api_version}/{business_id}/client_whatsapp_business_accounts"),
        ("system_users", f"https://graph.facebook.com/{api_version}/{business_id}/system_users"),
    ]

    for label, tok in tokens.items():
        results["business_portfolio"][label] = {}
        headers = {"Authorization": f"Bearer {tok}"}
        for ep_key, url in endpoints_step3:
            try:
                r = client.get(url, headers=headers)
                try:
                    body = r.json()
                except Exception:
                    body = {"raw": r.text[:300]}
                results["business_portfolio"][label][ep_key] = {
                    "status_code": r.status_code,
                    "body": sanitize_json(body),
                }
            except Exception as e:
                results["business_portfolio"][label][ep_key] = {"error": str(e)}

    # -------------------------------------------------------------
    # STEP 4: Investigate App & Business Associations
    # -------------------------------------------------------------
    endpoints_step4 = [
        ("app_details", f"https://graph.facebook.com/{api_version}/{app_id}?fields=id,name,business,primary_business"),
        ("business_details", f"https://graph.facebook.com/{api_version}/{business_id}?fields=id,name,primary_page,created_time,verification_status"),
        ("me_businesses", f"https://graph.facebook.com/{api_version}/me/businesses"),
        ("me_accounts", f"https://graph.facebook.com/{api_version}/me/accounts"),
        ("me_assigned_wabas", f"https://graph.facebook.com/{api_version}/me/assigned_whatsapp_business_accounts"),
    ]

    for label, tok in tokens.items():
        results["app_associations"][label] = {}
        headers = {"Authorization": f"Bearer {tok}"}
        for ep_key, url in endpoints_step4:
            try:
                r = client.get(url, headers=headers)
                try:
                    body = r.json()
                except Exception:
                    body = {"raw": r.text[:300]}
                results["app_associations"][label][ep_key] = {
                    "status_code": r.status_code,
                    "body": sanitize_json(body),
                }
            except Exception as e:
                results["app_associations"][label][ep_key] = {"error": str(e)}

out_file = PROJECT_ROOT / "scripts" / "alternative_diagnostic_output.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"[SUCCESS] Diagnostic complete. Written to {out_file}")

