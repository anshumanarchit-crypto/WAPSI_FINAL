"""
WAPSI — Phase 6 Stage A: Actual Provider Authentication Verification Script
Safely tests read-only connectivity against:
1. Razorpay Test Mode API (Harmless GET /v1/payments?count=1)
2. Meta WhatsApp Cloud API (Harmless GET /{version}/{phone_number_id})
3. Application Database via DATABASE_URL (SELECT 1 only)
4. Admin Database via WAPSI_ADMIN_DATABASE_URL (SELECT 1 only)

Strict Security Constraints:
- NEVER logs or outputs full credentials, tokens, DB URLs, or secrets.
- ZERO mutations, ZERO message dispatches, ZERO payment link creations.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import dotenv
import httpx
import psycopg2


def mask_string(val: str | None, prefix_len: int = 4, suffix_len: int = 4) -> str:
    if not val:
        return "[NOT CONFIGURED]"
    if len(val) <= prefix_len + suffix_len:
        return "****"
    return f"{val[:prefix_len]}...{val[-suffix_len:]}"


def normalize_dsn_for_psycopg2(url: str) -> str:
    """Strips SQLAlchemy dialect prefixes such as +psycopg2 for raw psycopg2 connection."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def run_stage_a_verification() -> Dict[str, Any]:
    # Locate .env file
    env_path = Path(".env")
    if not env_path.exists():
        return {
            "error": ".env file not found in current working directory",
            "overall_status": "BLOCKED"
        }

    env_vars = dotenv.dotenv_values(env_path)

    report: Dict[str, Any] = {
        "stage": "Phase 6 Stage A: Actual Provider Authentication",
        "checks": {},
        "verdicts": {},
    }

    # --------------------------------------------------------------------------
    # 1. Environment & Mode Verification
    # --------------------------------------------------------------------------
    rzp_mode = env_vars.get("RAZORPAY_MODE", "test").strip().lower()
    rzp_key_id = env_vars.get("RAZORPAY_KEY_ID", "").strip()
    rzp_key_secret = env_vars.get("RAZORPAY_KEY_SECRET", "").strip()
    rzp_webhook_secret = env_vars.get("RAZORPAY_WEBHOOK_SECRET", "").strip()

    wa_token = env_vars.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    wa_phone_id = env_vars.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    wa_version = env_vars.get("WHATSAPP_API_VERSION", "v21.0").strip()
    meta_app_secret = env_vars.get("META_APP_SECRET", "").strip()
    wa_verify_token = env_vars.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip()

    db_url = env_vars.get("DATABASE_URL", "").strip()
    admin_db_url = env_vars.get("WAPSI_ADMIN_DATABASE_URL", "").strip()

    mode_check = {
        "razorpay_mode": rzp_mode,
        "is_test_mode": rzp_mode == "test",
        "key_id_prefix_valid": rzp_key_id.startswith("rzp_test_"),
        "key_id_masked": f"rzp_test_...{rzp_key_id[-4:]}" if len(rzp_key_id) > 12 else "rzp_test_****",
        "has_key_secret": bool(rzp_key_secret),
        "has_webhook_secret": bool(rzp_webhook_secret),
        "secrets_are_separate": bool(rzp_key_secret and rzp_webhook_secret and rzp_key_secret != rzp_webhook_secret),
        "has_whatsapp_token": bool(wa_token),
        "has_whatsapp_phone_id": bool(wa_phone_id),
        "phone_id_masked": mask_string(wa_phone_id, 3, 3),
        "has_meta_app_secret": bool(meta_app_secret),
        "has_whatsapp_verify_token": bool(wa_verify_token),
        "whatsapp_api_version": wa_version,
        "has_database_url": bool(db_url),
        "has_admin_database_url": bool(admin_db_url),
    }
    report["checks"]["environment_configuration"] = mode_check

    # --------------------------------------------------------------------------
    # 2. Razorpay Test Mode Authentication Check (Read-Only)
    # --------------------------------------------------------------------------
    rzp_auth_result: Dict[str, Any] = {
        "endpoint": "https://api.razorpay.com/v1/payments?count=1",
        "method": "GET",
    }
    if not rzp_key_id or not rzp_key_secret:
        rzp_auth_result["status"] = "BLOCKED"
        rzp_auth_result["reason"] = "Razorpay credentials missing from .env"
        report["verdicts"]["razorpay_authentication"] = "BLOCKED"
    elif not rzp_key_id.startswith("rzp_test_"):
        rzp_auth_result["status"] = "FAIL"
        rzp_auth_result["reason"] = "Safety failure: Key ID does not start with rzp_test_"
        report["verdicts"]["razorpay_authentication"] = "FAIL"
    else:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://api.razorpay.com/v1/payments",
                    params={"count": 1},
                    auth=(rzp_key_id, rzp_key_secret),
                )
                rzp_auth_result["http_status"] = resp.status_code
                rzp_auth_result["request_id"] = resp.headers.get("x-razorpay-request-id", "none")
                if resp.status_code == 200:
                    data = resp.json()
                    rzp_auth_result["authenticated"] = True
                    rzp_auth_result["entity"] = data.get("entity", "unknown")
                    rzp_auth_result["count"] = data.get("count", 0)
                    report["verdicts"]["razorpay_authentication"] = "PASS"
                elif resp.status_code == 401:
                    rzp_auth_result["authenticated"] = False
                    rzp_auth_result["error"] = resp.json().get("error", {}).get("description", "Unauthorized")
                    report["verdicts"]["razorpay_authentication"] = "FAIL"
                else:
                    rzp_auth_result["authenticated"] = False
                    rzp_auth_result["error"] = f"Unexpected HTTP {resp.status_code}: {resp.text[:100]}"
                    report["verdicts"]["razorpay_authentication"] = "FAIL"
        except Exception as exc:
            rzp_auth_result["status"] = "ERROR"
            rzp_auth_result["error"] = type(exc).__name__
            report["verdicts"]["razorpay_authentication"] = "FAIL"

    report["checks"]["razorpay_connectivity"] = rzp_auth_result

    # --------------------------------------------------------------------------
    # 3. Meta WhatsApp Cloud API Authentication Check (Read-Only)
    # --------------------------------------------------------------------------
    wa_auth_result: Dict[str, Any] = {
        "endpoint": f"https://graph.facebook.com/{wa_version}/{wa_phone_id}",
        "method": "GET",
    }
    if not wa_token or not wa_phone_id:
        wa_auth_result["status"] = "BLOCKED"
        wa_auth_result["reason"] = "WhatsApp credentials missing from .env"
        report["verdicts"]["whatsapp_authentication"] = "BLOCKED"
    else:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"https://graph.facebook.com/{wa_version}/{wa_phone_id}",
                    headers={"Authorization": f"Bearer {wa_token}"},
                )
                wa_auth_result["http_status"] = resp.status_code
                if resp.status_code == 200:
                    data = resp.json()
                    wa_auth_result["authenticated"] = True
                    wa_auth_result["resource_accessible"] = True
                    wa_auth_result["id_matched"] = data.get("id") == wa_phone_id
                    wa_auth_result["verified_name"] = bool(data.get("verified_name"))
                    wa_auth_result["quality_rating"] = data.get("quality_rating", "UNKNOWN")
                    wa_auth_result["code_verification_status"] = data.get("code_verification_status", "UNKNOWN")
                    report["verdicts"]["whatsapp_authentication"] = "PASS"
                elif resp.status_code in (400, 401, 403):
                    wa_auth_result["authenticated"] = False
                    err_info = resp.json().get("error", {})
                    wa_auth_result["error_type"] = err_info.get("type", "OAuthException")
                    wa_auth_result["error_code"] = err_info.get("code")
                    wa_auth_result["error_subcode"] = err_info.get("error_subcode")
                    wa_auth_result["error_message"] = err_info.get("message", "Authentication/Authorization error")
                    report["verdicts"]["whatsapp_authentication"] = "FAIL"
                else:
                    wa_auth_result["authenticated"] = False
                    wa_auth_result["error"] = f"Unexpected HTTP {resp.status_code}"
                    report["verdicts"]["whatsapp_authentication"] = "FAIL"
        except Exception as exc:
            wa_auth_result["status"] = "ERROR"
            wa_auth_result["error"] = type(exc).__name__
            report["verdicts"]["whatsapp_authentication"] = "FAIL"

    report["checks"]["whatsapp_connectivity"] = wa_auth_result

    # --------------------------------------------------------------------------
    # 4. Database Connectivity: DATABASE_URL (Application Role: wapsi_app)
    # --------------------------------------------------------------------------
    app_db_result: Dict[str, Any] = {
        "query": "SELECT 1, current_user;",
    }
    if not db_url:
        app_db_result["status"] = "BLOCKED"
        app_db_result["reason"] = "DATABASE_URL not configured in .env"
        report["verdicts"]["application_database"] = "BLOCKED"
    else:
        try:
            clean_url = normalize_dsn_for_psycopg2(db_url)
            conn = psycopg2.connect(clean_url, connect_timeout=5)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT 1, current_user;")
                row = cur.fetchone()
                app_db_result["result"] = row[0]
                app_db_result["current_user"] = row[1]
                app_db_result["is_wapsi_app_user"] = row[1] == "wapsi_app"
            conn.close()
            if app_db_result["result"] == 1 and app_db_result["is_wapsi_app_user"]:
                report["verdicts"]["application_database"] = "PASS"
            else:
                report["verdicts"]["application_database"] = "FAIL"
        except Exception as exc:
            app_db_result["status"] = "ERROR"
            app_db_result["error"] = type(exc).__name__
            report["verdicts"]["application_database"] = "FAIL"

    report["checks"]["application_database"] = app_db_result

    # --------------------------------------------------------------------------
    # 5. Database Connectivity: WAPSI_ADMIN_DATABASE_URL (Admin Role: postgres)
    # --------------------------------------------------------------------------
    admin_db_result: Dict[str, Any] = {
        "query": "SELECT 1, current_user;",
    }
    if not admin_db_url:
        admin_db_result["status"] = "BLOCKED"
        admin_db_result["reason"] = "WAPSI_ADMIN_DATABASE_URL not configured in .env"
        report["verdicts"]["admin_database"] = "BLOCKED"
    else:
        try:
            clean_admin_url = normalize_dsn_for_psycopg2(admin_db_url)
            conn = psycopg2.connect(clean_admin_url, connect_timeout=5)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT 1, current_user;")
                row = cur.fetchone()
                admin_db_result["result"] = row[0]
                admin_db_result["current_user"] = row[1]
                admin_db_result["is_admin_user"] = row[1] in ("postgres", "supabase_admin")
            conn.close()
            if admin_db_result["result"] == 1 and admin_db_result["is_admin_user"]:
                report["verdicts"]["admin_database"] = "PASS"
            else:
                report["verdicts"]["admin_database"] = "FAIL"
        except Exception as exc:
            admin_db_result["status"] = "ERROR"
            admin_db_result["error"] = type(exc).__name__
            report["verdicts"]["admin_database"] = "FAIL"

    report["checks"]["admin_database"] = admin_db_result

    return report


if __name__ == "__main__":
    results = run_stage_a_verification()
    print(json.dumps(results, indent=2))
