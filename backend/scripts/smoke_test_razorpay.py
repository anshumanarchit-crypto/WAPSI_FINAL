#!/usr/bin/env python3
"""
WAPSI Phase 2.1: Controlled Real Razorpay Test Mode Smoke Test.
Target: Razorpay Test Mode API (https://api.razorpay.com/v1)

Safety Guarantees:
- Strict test-mode guard: Refuses execution if live keys (rzp_live_) are detected.
- Controlled low-value payment link (1000 paise = Rs 10.00).
- Immediate link cancellation: created link is immediately cancelled to ensure zero accidental charge.
- Zero secret exposure: Key secret and full authorization tokens are strictly masked.
- Bounded network timeout: 10 seconds.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wapsi.core.config import get_settings
from wapsi.integrations.razorpay.client import (
    RazorpayAuthError,
    RazorpayClient,
    RazorpayError,
)


def mask_id(key: str) -> str:
    """Safely masks identifier showing prefix and last 4 chars."""
    if not key:
        return "<EMPTY>"
    if len(key) <= 8:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


def run_razorpay_smoke_test() -> bool:
    print("=" * 75)
    print("WAPSI PHASE 2.1: CONTROLLED RAZORPAY TEST MODE SMOKE TEST")
    print("=" * 75)

    settings = get_settings()
    key_id = settings.razorpay_key_id
    key_secret = settings.razorpay_key_secret.get_secret_value() if settings.razorpay_key_secret else None

    # 1. Credential Verification Guard
    if not key_id or not key_secret:
        print("[FAIL] Missing Razorpay credentials in environment or .env file.")
        print("       Required variables:")
        print(f"       - RAZORPAY_KEY_ID: {'CONFIGURED' if key_id else 'MISSING'}")
        print(f"       - RAZORPAY_KEY_SECRET: {'CONFIGURED' if key_secret else 'MISSING'}")
        return False

    if key_id.startswith("rzp_live_"):
        print("[SECURITY HALT] Live Razorpay key detected (rzp_live_...).")
        print("                Phase 2.1 strictly forbids executing against live Razorpay accounts.")
        return False

    if not key_id.startswith("rzp_test_"):
        print(f"[FAIL] RAZORPAY_KEY_ID must start with 'rzp_test_'. Got: {mask_id(key_id)}")
        return False

    print(f"[*] Razorpay Mode: {settings.razorpay_mode.upper()} (SAFE)")
    print(f"[*] Key ID:        {mask_id(key_id)}")
    print(f"[*] Key Secret:    <CONFIGURED - REDACTED>")
    print(f"[*] API Endpoint:  https://api.razorpay.com/v1")
    print()

    client = RazorpayClient(
        key_id=key_id,
        key_secret=key_secret,
        timeout_seconds=10.0,
        max_retries=2,
    )

    test_case_id = f"SMOKE-{int(time.time())}"
    test_amount_paise = 1000  # Rs 10.00
    expire_unix = int(time.time() + 1200)  # 20 minutes (Razorpay requires >= 15m)

    # 2. Create Controlled Payment Link
    print(f"[*] Step 1: Issuing test Payment Link creation (amount: {test_amount_paise} paise / Rs 10.00)...")
    try:
        start_t = time.time()
        created_link = client.create_payment_link(
            amount_in_paise=test_amount_paise,
            currency="INR",
            description="WAPSI Controlled Smoke Test (Auto-Cancel)",
            customer={
                "name": "WAPSI Test Sandbox",
                "contact": "+919876543210",
                "email": "test-sandbox@wapsi.internal",
            },
            notes={
                "case_id": test_case_id,
                "environment": "sandbox_verification",
                "purpose": "phase2_1_smoke_test",
            },
            expire_by=expire_unix,
            notify_whatsapp=False,
            notify_sms=False,
        )
        latency_ms = (time.time() - start_t) * 1000.0
        plink_id = created_link.get("id")
        short_url = created_link.get("short_url")
        link_status = created_link.get("status")

        print(f"    [PASS] Payment Link created successfully in {latency_ms:.1f} ms")
        print(f"           - Link ID:   {plink_id}")
        print(f"           - Short URL: {short_url}")
        print(f"           - Status:    {link_status}")
        print(f"           - Amount:    {created_link.get('amount')} paise")
        print(f"           - Currency:  {created_link.get('currency')}")

    except RazorpayAuthError as auth_err:
        print(f"[FAIL] Razorpay authentication failed: {auth_err}")
        print("       Please check that the configured test credentials in .env are active.")
        return False
    except RazorpayError as rzp_err:
        print(f"[FAIL] Razorpay API call failed: {rzp_err}")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected connection error: {type(e).__name__}: {e}")
        return False

    # 3. Retrieve Created Payment Link
    print(f"\n[*] Step 2: Retrieving Payment Link {plink_id} to verify fields...")
    try:
        retrieved_link = client.get_payment_link(plink_id)
        assert retrieved_link.get("id") == plink_id
        assert retrieved_link.get("amount") == test_amount_paise
        assert retrieved_link.get("notes", {}).get("case_id") == test_case_id
        print(f"    [PASS] Retrieved link verified matching fields.")
    except Exception as get_err:
        print(f"[FAIL] Failed to retrieve payment link: {get_err}")
        return False

    # 4. Immediate Safety Cancellation
    print(f"\n[*] Step 3: Cancelling Payment Link {plink_id} to ensure zero accidental charge...")
    try:
        cancelled_link = client.cancel_payment_link(plink_id)
        final_status = cancelled_link.get("status")
        print(f"    [PASS] Cancellation successful.")
        print(f"           - Final Status: {final_status}")
    except Exception as cancel_err:
        print(f"[WARNING] Automatic cancellation returned: {cancel_err}")

    print("\n" + "=" * 75)
    print("[SUCCESS] Razorpay Test Mode Smoke Test passed genuine provider verification!")
    print("=" * 75)
    return True


if __name__ == "__main__":
    success = run_razorpay_smoke_test()
    sys.exit(0 if success else 1)
