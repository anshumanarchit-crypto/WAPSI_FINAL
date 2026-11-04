"""
WAPSI — Phase 6: Meta WABA Permission Reconciliation Diagnostic Script
Performs strictly read-only inspection against Meta Graph API endpoints.

Strict Safety Rules:
- Never prints token or app secret.
- Read-only GET requests only.
- ZERO message sends.
- ZERO database writes.
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

token = env_vars.get("WHATSAPP_ACCESS_TOKEN", "").strip()
phone_number_id = env_vars.get("WHATSAPP_PHONE_NUMBER_ID", "1407090562487899").strip()
waba_id = env_vars.get("WHATSAPP_BUSINESS_ACCOUNT_ID", "969727602419694").strip()
app_id = "963047183124334"
screenshot_user_id = "61595814315120"
audit_user_id = "122103630711527143"
api_version = env_vars.get("WHATSAPP_API_VERSION", "v26.0").strip()

if not token:
    print("[ERROR] WHATSAPP_ACCESS_TOKEN not found in .env")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "User-Agent": "WAPSI-Audit-Tool/2.0",
}

results: Dict[str, Any] = {
    "api_version": api_version,
    "phone_number_id": phone_number_id,
    "target_waba_id": waba_id,
    "app_id": app_id,
    "screenshot_user_id": screenshot_user_id,
    "audit_user_id": audit_user_id,
    "token_inspection": {},
    "endpoints": {},
}

with httpx.Client(timeout=15.0) as client:
    # 1. Debug Token
    print("[*] Inspecting token via /debug_token...")
    try:
        r = client.get(
            "https://graph.facebook.com/debug_token",
            params={"input_token": token, "access_token": token},
        )
        results["token_inspection"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["token_inspection"] = {"error": str(e)}

    # 2. Inspect /me
    print("[*] Inspecting /me...")
    try:
        r = client.get(f"https://graph.facebook.com/{api_version}/me?fields=id,name", headers=headers)
        results["endpoints"]["me"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["me"] = {"error": str(e)}

    # 3. Inspect App ID
    print("[*] Inspecting App ID...")
    try:
        r = client.get(f"https://graph.facebook.com/{api_version}/{app_id}?fields=id,name,business", headers=headers)
        results["endpoints"]["app"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["app"] = {"error": str(e)}

    # 4. Inspect Audit System User ID (122103630711527143)
    print("[*] Inspecting audit user ID (122103630711527143)...")
    try:
        r = client.get(f"https://graph.facebook.com/{api_version}/{audit_user_id}?fields=id,name", headers=headers)
        results["endpoints"]["audit_user"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["audit_user"] = {"error": str(e)}

    # 5. Inspect Screenshot User ID (61595814315120)
    print("[*] Inspecting screenshot user ID (61595814315120)...")
    try:
        r = client.get(f"https://graph.facebook.com/{api_version}/{screenshot_user_id}?fields=id,name", headers=headers)
        results["endpoints"]["screenshot_user"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["screenshot_user"] = {"error": str(e)}

    # 6. Inspect Phone Number Resource (1407090562487899)
    print("[*] Inspecting Phone Number (1407090562487899)...")
    try:
        r = client.get(
            f"https://graph.facebook.com/{api_version}/{phone_number_id}?fields=id,display_phone_number,verified_name,status,quality_rating,code_verification_status,name_status",
            headers=headers,
        )
        results["endpoints"]["phone_number"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["phone_number"] = {"error": str(e)}

    # 7. Inspect WABA directly (969727602419694)
    print("[*] Inspecting WABA (969727602419694)...")
    try:
        r = client.get(
            f"https://graph.facebook.com/{api_version}/{waba_id}?fields=id,name,currency,timezone_id,message_template_namespace",
            headers=headers,
        )
        results["endpoints"]["waba"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["waba"] = {"error": str(e)}

    # 8. Inspect WABA Phone Numbers
    print("[*] Inspecting WABA phone numbers...")
    try:
        r = client.get(f"https://graph.facebook.com/{api_version}/{waba_id}/phone_numbers", headers=headers)
        results["endpoints"]["waba_phone_numbers"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["waba_phone_numbers"] = {"error": str(e)}

    # 9. Inspect WABA Assigned Users
    print("[*] Inspecting WABA assigned users...")
    try:
        r = client.get(f"https://graph.facebook.com/{api_version}/{waba_id}/assigned_users", headers=headers)
        results["endpoints"]["waba_assigned_users"] = {
            "status_code": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
        }
    except Exception as e:
        results["endpoints"]["waba_assigned_users"] = {"error": str(e)}

# Output formatted JSON report
output_file = PROJECT_ROOT / "scripts" / "waba_reconciliation_output.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\n" + "=" * 70)
print(f"[SUCCESS] Diagnostic output written to: {output_file}")
print("=" * 70)

