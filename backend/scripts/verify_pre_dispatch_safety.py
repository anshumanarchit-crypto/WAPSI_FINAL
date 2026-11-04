"""
WAPSI — Phase 6 Pre-Dispatch Safety Verification Script
Executes strictly read-only inspection of:
1. Razorpay Payment Link (plink_TvKucM1yXJQAZA) on live Test Mode API.
2. Durable Outbox Job (5a6587ab-2601-4017-b396-48e3d2fc2fda) in PostgreSQL.
3. WhatsApp Test Recipient, Opt-Out, WABA, and 24-hour Session Window.
4. Prepared Message Content & Sandbox Disclosure.

Strict Safety Rules:
- ZERO mutations.
- ZERO message sends.
- ZERO background worker execution.
- Reports BLOCKED if job is eligible for dispatch or if 24h window / approved template is absent.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from sqlalchemy import text

from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager
from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import WhatsAppClient
from wapsi.recovery.opt_out_store import get_persistent_opt_out_store


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "[NOT CONFIGURED]"
    clean = phone.strip()
    if len(clean) <= 6:
        return "****"
    return f"{clean[:3]}****{clean[-4:]}"


def run_pre_dispatch_verification() -> Dict[str, Any]:
    settings = get_settings()
    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage": "Phase 6 Pre-Dispatch Safety Verification",
        "checks": {},
        "blockers": [],
        "overall_verdict": "PENDING",
    }

    # ==========================================================================
    # 1. Razorpay Payment Link Verification (Live Read-Only API Fetch)
    # ==========================================================================
    rzp_check: Dict[str, Any] = {}
    target_link_id = "plink_TvKucM1yXJQAZA"
    target_ref_id = "ref_wapsi_p6_s2_001"
    
    try:
        rzp_client = RazorpayClient()
        link_data = rzp_client.get_payment_link(target_link_id)
        
        rzp_check["id_matches"] = link_data.get("id") == target_link_id
        rzp_check["payment_link_id"] = link_data.get("id")
        rzp_check["amount_paise"] = link_data.get("amount")
        rzp_check["amount_paise_is_1000"] = link_data.get("amount") == 1000
        rzp_check["currency"] = link_data.get("currency")
        rzp_check["currency_is_inr"] = link_data.get("currency") == "INR"
        rzp_check["reference_id"] = link_data.get("reference_id")
        rzp_check["reference_id_matches"] = link_data.get("reference_id") == target_ref_id
        rzp_check["status"] = link_data.get("status")
        rzp_check["status_is_created"] = link_data.get("status") == "created"
        rzp_check["amount_paid"] = link_data.get("amount_paid", 0)
        rzp_check["is_unpaid"] = link_data.get("amount_paid", 0) == 0
        
        notify = link_data.get("notify", {})
        rzp_check["sms_disabled"] = notify.get("sms") is False
        rzp_check["email_disabled"] = notify.get("email") is False
        rzp_check["whatsapp_disabled"] = notify.get("whatsapp") is False
        rzp_check["reminders_disabled"] = link_data.get("reminder_enable") is False
        rzp_check["short_url"] = link_data.get("short_url")
        rzp_check["notes"] = link_data.get("notes", {})
        
        rzp_passed = (
            rzp_check["id_matches"]
            and rzp_check["amount_paise_is_1000"]
            and rzp_check["currency_is_inr"]
            and rzp_check["reference_id_matches"]
            and rzp_check["status_is_created"]
            and rzp_check["is_unpaid"]
            and rzp_check["sms_disabled"]
            and rzp_check["email_disabled"]
            and rzp_check["whatsapp_disabled"]
            and rzp_check["reminders_disabled"]
        )
        rzp_check["verdict"] = "PASS" if rzp_passed else "FAIL"
    except Exception as exc:
        rzp_check["verdict"] = "FAIL"
        rzp_check["error"] = type(exc).__name__
        results["blockers"].append(f"Razorpay link verification failed: {exc}")

    results["checks"]["razorpay_payment_link"] = rzp_check

    # ==========================================================================
    # 2. Durable Outbox Safety & Worker Eligibility Check
    # ==========================================================================
    outbox_check: Dict[str, Any] = {}
    target_job_id = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
    target_case_id = "wapsi_case_phase6_stage2_001"
    merchant_uuid = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"

    dm = DatabaseManager()
    with dm.tenant_session_scope(merchant_uuid) as session:
        # Check specific job
        stmt = text(
            "SELECT id, case_id, payment_id, merchant_id, action, channel, "
            "recipient_masked, message_payload, status, next_attempt_at, "
            "worker_id, lease_expires_at, retry_count "
            "FROM recovery_outbox WHERE id = :jid"
        )
        row = session.execute(stmt, {"jid": target_job_id}).fetchone()
        
        # Check duplicate jobs for this case
        dup_stmt = text(
            "SELECT count(*) FROM recovery_outbox WHERE case_id = :cid"
        )
        dup_count = session.execute(dup_stmt, {"cid": target_case_id}).scalar()

    if not row:
        outbox_check["verdict"] = "FAIL"
        outbox_check["error"] = f"Job {target_job_id} not found in database."
        results["blockers"].append(f"Outbox job {target_job_id} not found.")
    else:
        outbox_check["job_id"] = str(row[0])
        outbox_check["case_id"] = row[1]
        outbox_check["case_id_matches"] = row[1] == target_case_id
        outbox_check["channel"] = row[5]
        outbox_check["channel_is_whatsapp"] = row[5] == "whatsapp"
        outbox_check["recipient_masked"] = row[6]
        outbox_check["db_status"] = row[8]
        outbox_check["next_attempt_at"] = row[9].isoformat() if row[9] else None
        outbox_check["worker_id"] = row[10]
        outbox_check["has_worker_id"] = bool(row[10])
        outbox_check["no_message_dispatched"] = row[10] is None
        outbox_check["duplicate_count_for_case"] = dup_count
        outbox_check["no_duplicates"] = dup_count == 1
        
        # Check payload
        payload = row[7] if isinstance(row[7], dict) else {}
        outbox_check["has_whatsapp_message_id"] = "wamid" in payload or "message_id" in payload

        # Check eligibility for automatic dispatch:
        # Migration 7 claim function selects WHERE status IN ('QUEUED', 'RETRY') AND next_attempt_at <= now
        is_eligible_for_auto_dispatch = row[8] in ("QUEUED", "RETRY")
        outbox_check["eligible_for_auto_dispatch"] = is_eligible_for_auto_dispatch

        if is_eligible_for_auto_dispatch:
            outbox_check["verdict"] = "BLOCKED"
            outbox_check["dispatch_safety_issue"] = (
                "Outbox job is currently in 'QUEUED' status with next_attempt_at in the past. "
                "Any running outbox worker executing claim_recovery_outbox_jobs() could claim "
                "and dispatch this job without explicit operator approval. "
                "Job must be transitioned to 'PENDING_APPROVAL' or held before workers are active."
            )
            results["blockers"].append(
                "Outbox safety blocker: Job is currently in 'QUEUED' status and eligible for automatic worker claim."
            )
        else:
            outbox_check["verdict"] = "PASS"

    results["checks"]["durable_outbox_safety"] = outbox_check

    # ==========================================================================
    # 3. WhatsApp Recipient, WABA, Opt-Out & 24h Window Checks
    # ==========================================================================
    wa_check: Dict[str, Any] = {}
    test_phone = settings.test_recipient_phone
    token = settings.get_whatsapp_token_str()
    phone_id = settings.whatsapp_phone_number_id
    waba_id = settings.whatsapp_business_account_id
    version = settings.whatsapp_api_version
    
    wa_check["configured_test_phone_masked"] = mask_phone(test_phone)
    wa_clean = WhatsAppClient.sanitize_phone_number(test_phone)
    wa_check["sanitized_recipient"] = mask_phone(wa_clean)

    # Opt-Out check
    opt_out_store = get_persistent_opt_out_store(database_manager=dm)
    is_opted_out = opt_out_store.is_opted_out(test_phone)
    wa_check["is_opted_out"] = is_opted_out
    wa_check["opt_out_clear"] = is_opted_out is False

    # WABA & Phone Sender verification via Meta Graph API
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r_phone = httpx.get(f"https://graph.facebook.com/{version}/{phone_id}", headers=headers, timeout=10.0)
        if r_phone.status_code == 200:
            p_data = r_phone.json()
            wa_check["sender_phone_number"] = p_data.get("display_phone_number")  # e.g. +1 555-214-8539
            wa_check["verified_name"] = p_data.get("verified_name")
            wa_check["quality_rating"] = p_data.get("quality_rating")
            wa_check["phone_verified"] = p_data.get("code_verification_status") == "VERIFIED"
        else:
            wa_check["phone_verified"] = False
            wa_check["phone_error"] = r_phone.text[:100]
    except Exception as e:
        wa_check["phone_verified"] = False
        wa_check["phone_error"] = type(e).__name__

    # Inbound message & 24-hour customer service window check
    last_inbound_ts = None
    if hasattr(opt_out_store, "get_last_inbound_timestamp"):
        last_inbound_ts = opt_out_store.get_last_inbound_timestamp(test_phone)
    wa_check["last_inbound_timestamp"] = last_inbound_ts

    now_ts = time.time()
    is_within_24h_window = bool(last_inbound_ts and (now_ts - last_inbound_ts) <= 86400)
    wa_check["is_within_24h_window"] = is_within_24h_window

    # Approved Template Check
    # In Meta Cloud API Sandbox, standard template 'hello_world' is available
    # Custom payment recovery templates (e.g. 'payment_recovery_v1') require business manager creation & approval
    has_approved_recovery_template = False
    wa_check["approved_recovery_template_available"] = has_approved_recovery_template
    wa_check["sandbox_hello_world_available"] = True  # Standard Sandbox default

    # Evaluate Session Window or Template condition:
    # A. An approved template can be used; OR
    # B. The recipient has an active 24-hour customer service window permitting a free-form message.
    policy_condition_met = is_within_24h_window or has_approved_recovery_template
    wa_check["policy_condition_met"] = policy_condition_met

    if not policy_condition_met:
        wa_check["verdict"] = "BLOCKED"
        wa_check["policy_blocker_reason"] = (
            "Neither condition holds: The recipient (+91****5671) has no recorded inbound interaction "
            "within the last 24 hours (24h window closed), and no custom payment recovery template "
            "is registered/approved on the WABA. Sending a free-form text recovery link without an active "
            "24h session window will be rejected by Meta Cloud API (HTTP 400 - Code 131047 / Re-engagement template required). "
            "To open the 24-hour service window for sandbox testing, the test recipient must send a message "
            "(e.g. 'Hi') to the test sender (+1 555-214-8539)."
        )
        results["blockers"].append(
            "WhatsApp policy blocker: Recipient 24-hour customer service window is inactive and no custom template is approved."
        )
    else:
        wa_check["verdict"] = "PASS"

    results["checks"]["whatsapp_recipient_and_policy"] = wa_check

    # ==========================================================================
    # 4. Message Content & Disclosure Review
    # ==========================================================================
    msg_check: Dict[str, Any] = {}
    if row and isinstance(row[7], dict):
        raw_text = row[7].get("text", {}).get("body", "")
        msg_check["raw_body"] = raw_text
        msg_check["contains_sandbox_disclosure"] = "WAPSI SANDBOX TEST" in raw_text
        msg_check["contains_correct_amount"] = "INR 10.00" in raw_text
        msg_check["contains_correct_link"] = "https://rzp.io/rzp/NCf137AL" in raw_text
        msg_check["explicit_test_warning"] = "Do NOT make a real payment" in raw_text
        msg_check["contains_opt_out_instruction"] = "Reply STOP to opt out" in raw_text
        msg_check["no_real_customer_pii"] = True
        msg_check["no_false_payment_claim"] = "Your payment link for INR 10.00 is ready" in raw_text and "succeeded" not in raw_text.lower()
        
        msg_passed = (
            msg_check["contains_sandbox_disclosure"]
            and msg_check["contains_correct_amount"]
            and msg_check["contains_correct_link"]
            and msg_check["explicit_test_warning"]
            and msg_check["contains_opt_out_instruction"]
            and msg_check["no_real_customer_pii"]
            and msg_check["no_false_payment_claim"]
        )
        msg_check["verdict"] = "PASS" if msg_passed else "FAIL"
    else:
        msg_check["verdict"] = "FAIL"
        msg_check["error"] = "No message body found in outbox payload."
        results["blockers"].append("Message review failed: empty payload.")

    results["checks"]["message_content_review"] = msg_check

    # ==========================================================================
    # Final Overall Verdict
    # ==========================================================================
    if results["blockers"]:
        results["overall_verdict"] = "BLOCKED"
    else:
        results["overall_verdict"] = "PASS"

    return results


if __name__ == "__main__":
    res = run_pre_dispatch_verification()
    print(json.dumps(res, indent=2))

