"""
WAPSI — Phase 6 Stage 2E.1 Dependency Recovery & Readiness Verification.
Strictly Read-Only Inspection.
"""

import datetime
import json
import httpx
from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager
from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.whatsapp.client import WhatsAppClient
from wapsi.recovery.outbox import DurableOutboxStore, compute_approval_hash
from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
from sqlalchemy import text

def run_checks():
    settings = get_settings()
    dm = DatabaseManager()
    store = DurableOutboxStore(database_manager=dm)
    opt_store = get_persistent_opt_out_store(database_manager=dm)
    results = {}

    print("==================================================")
    print("1. META GRAPH API & TOKEN VERIFICATION")
    print("==================================================")
    token = settings.get_whatsapp_token_str()
    diag_token = settings.whatsapp_diagnostic_token.get_secret_value() if settings.whatsapp_diagnostic_token else ""
    token_source = "diagnostic_token" if token == diag_token else "access_token"
    print(f"Active Token Source: {token_source} (length: {len(token)})")

    api_ver = settings.whatsapp_api_version or "v21.0"
    headers = {"Authorization": f"Bearer {token}"}
    phone_id = settings.whatsapp_phone_number_id
    waba_id = settings.whatsapp_business_account_id

    # Phone endpoint check
    url_phone = f"https://graph.facebook.com/{api_ver}/{phone_id}"
    try:
        resp_phone = httpx.get(url_phone, headers=headers, timeout=5.0)
        print(f"Phone Endpoint ({url_phone}) Status: {resp_phone.status_code}")
        if resp_phone.status_code == 200:
            pdata = resp_phone.json()
            print("  Phone Data:", {"id": pdata.get("id"), "display_phone_number": pdata.get("display_phone_number"), "quality_rating": pdata.get("quality_rating")})
            results["meta_phone"] = "PASS"
        else:
            print("  Phone Error:", resp_phone.text[:200])
            results["meta_phone"] = f"FAIL ({resp_phone.status_code})"
    except Exception as e:
        print("  Phone Exception:", str(e))
        results["meta_phone"] = f"ERROR: {str(e)}"

    # Debug token check
    url_debug = f"https://graph.facebook.com/{api_ver}/debug_token?input_token={token}"
    try:
        resp_debug = httpx.get(url_debug, headers=headers, timeout=5.0)
        print(f"Debug Token Status: {resp_debug.status_code}")
        if resp_debug.status_code == 200:
            ddata = resp_debug.json().get("data", {})
            print("  is_valid:", ddata.get("is_valid"))
            print("  app_id:", ddata.get("app_id"))
            print("  type:", ddata.get("type"))
            print("  expires_at:", ddata.get("expires_at"))
            print("  scopes:", ddata.get("scopes"))
            results["meta_token"] = "PASS"
        else:
            print("  Debug Token Error:", resp_debug.text[:200])
            results["meta_token"] = f"FAIL ({resp_debug.status_code})"
    except Exception as e:
        print("  Debug Token Exception:", str(e))
        results["meta_token"] = f"ERROR: {str(e)}"

    print("\n==================================================")
    print("2. FASTAPI LOCAL SERVER VERIFICATION (PORT 8000)")
    print("==================================================")
    try:
        resp_local = httpx.get("http://127.0.0.1:8000/health", timeout=3.0)
        print(f"Local /health Status: {resp_local.status_code}")
        if resp_local.status_code == 200:
            print("  Payload:", resp_local.json())
            results["fastapi_local"] = "PASS"
        else:
            print("  Error:", resp_local.text[:100])
            results["fastapi_local"] = f"FAIL ({resp_local.status_code})"
    except Exception as e:
        print("  Local FastAPI Exception:", str(e))
        results["fastapi_local"] = f"FAIL (Connection refused / Not running)"

    # Webhook GET verification on local
    verify_token = settings.whatsapp_webhook_verify_token.get_secret_value() if settings.whatsapp_webhook_verify_token else "test_token"
    try:
        resp_local_wh = httpx.get(
            "http://127.0.0.1:8000/api/v1/webhooks/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": verify_token, "hub.challenge": "test_chall_123"},
            timeout=3.0
        )
        print(f"Local Webhook GET Status: {resp_local_wh.status_code}, Challenge Match: {resp_local_wh.text == 'test_chall_123'}")
        results["fastapi_webhook_get"] = "PASS" if resp_local_wh.text == "test_chall_123" else "FAIL"
    except Exception as e:
        print("  Local Webhook GET Exception:", str(e))
        results["fastapi_webhook_get"] = f"FAIL: {str(e)}"

    print("\n==================================================")
    print("3. NGROK TUNNEL VERIFICATION")
    print("==================================================")
    # Check ngrok local client API (port 4040)
    ngrok_public_url = None
    try:
        resp_ngrok_api = httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=3.0)
        if resp_ngrok_api.status_code == 200:
            tunnels = resp_ngrok_api.json().get("tunnels", [])
            print(f"Active Ngrok Tunnels ({len(tunnels)}):")
            for t in tunnels:
                print(f"  Name: {t.get('name')}, Public URL: {t.get('public_url')} -> {t.get('config', {}).get('addr')}")
                if "https" in t.get("public_url", ""):
                    ngrok_public_url = t.get("public_url")
            results["ngrok_tunnels_count"] = len(tunnels)
        else:
            print("  Ngrok API status:", resp_ngrok_api.status_code)
    except Exception as e:
        print("  Ngrok Client API (port 4040) not reachable:", str(e))
        results["ngrok_tunnels_count"] = "UNKNOWN"

    configured_base = str(settings.public_base_url).strip().rstrip("/")
    print(f"Configured public_base_url: {configured_base}")
    if configured_base:
        # Check /health on public URL
        try:
            resp_pub_health = httpx.get(f"{configured_base}/health", timeout=5.0)
            print(f"Public /health Status: {resp_pub_health.status_code}")
            if resp_pub_health.status_code == 200:
                print("  Payload:", resp_pub_health.json())
                results["public_health"] = "PASS"
            else:
                print("  Response:", resp_pub_health.text[:150])
                results["public_health"] = f"FAIL ({resp_pub_health.status_code})"
        except Exception as e:
            print("  Public /health Exception:", str(e))
            results["public_health"] = f"FAIL: {str(e)}"

        # Check webhook GET on public URL
        try:
            resp_pub_wh = httpx.get(
                f"{configured_base}/api/v1/webhooks/whatsapp",
                params={"hub.mode": "subscribe", "hub.verify_token": verify_token, "hub.challenge": "pub_chall_987"},
                timeout=5.0
            )
            print(f"Public Webhook GET Status: {resp_pub_wh.status_code}, Match: {resp_pub_wh.text == 'pub_chall_987'}")
            results["public_webhook_get"] = "PASS" if resp_pub_wh.text == "pub_chall_987" else "FAIL"
        except Exception as e:
            print("  Public Webhook GET Exception:", str(e))
            results["public_webhook_get"] = f"FAIL: {str(e)}"

    print("\n==================================================")
    print("4. 24-HOUR CUSTOMER SERVICE WINDOW CALCULATION")
    print("==================================================")
    target_merchant_id = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    with dm.tenant_session_scope(target_merchant_id) as session:
        # Get latest inbound WhatsApp webhook event
        wh_row = session.execute(text("""
            SELECT id, event_id, event_type, received_at, payload_sanitized
            FROM public.webhook_inbox
            WHERE provider = 'whatsapp_meta'
            ORDER BY received_at DESC
            LIMIT 1;
        """)).mappings().one_or_none()

    if wh_row:
        print("Latest Inbound Webhook Event:")
        print("  Inbox ID:", wh_row["id"])
        print("  Event ID:", wh_row["event_id"])
        print("  DB Received At:", wh_row["received_at"])
        p = wh_row["payload_sanitized"]
        provider_ts_str = None
        wamid = None
        if isinstance(p, dict):
            entry = p.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            val = changes.get("value", {})
            msgs = val.get("messages", [])
            if msgs:
                provider_ts_str = msgs[0].get("timestamp")
                wamid = msgs[0].get("id")

        print("  Inbound Wamid:", wamid)
        print("  Provider Timestamp (raw):", provider_ts_str)

        if provider_ts_str:
            provider_ts = int(provider_ts_str)
            dt_provider = datetime.datetime.fromtimestamp(provider_ts, tz=datetime.timezone.utc)
            expiry_dt = dt_provider + datetime.timedelta(hours=24)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            remaining = expiry_dt - now_utc

            print(f"  Provider Timestamp UTC: {dt_provider.isoformat()}")
            print(f"  24h Window Expiry UTC:  {expiry_dt.isoformat()}")
            print(f"  Current UTC Time:       {now_utc.isoformat()}")
            print(f"  Exact Remaining Time:   {remaining}")
            is_active = remaining.total_seconds() > 0
            print(f"  Window Active:          {is_active}")
            results["service_window"] = "PASS (ACTIVE)" if is_active else "FAIL (EXPIRED)"
            results["window_remaining"] = str(remaining)
            results["window_expiry"] = expiry_dt.isoformat()
    else:
        print("  No inbound webhook event found!")
        results["service_window"] = "FAIL (No event)"

    print("\n==================================================")
    print("5. RAZORPAY PAYMENT LINK & OUTBOX JOB AUDIT")
    print("==================================================")
    # Razorpay link check
    rzp_client = RazorpayClient()
    plink_id = "plink_TvKucM1yXJQAZA"
    try:
        plink = rzp_client.get_payment_link(plink_id)
        print(f"Payment Link ID: {plink.get('id')}")
        print(f"  Amount (paise): {plink.get('amount')} (INR {plink.get('amount')/100:.2f})")
        print(f"  Amount Paid:    {plink.get('amount_paid')}")
        print(f"  Status:         {plink.get('status')}")
        print(f"  URL:            {plink.get('short_url')}")
        rzp_pass = (plink.get("id") == plink_id and plink.get("amount") == 1000 and plink.get("amount_paid") == 0 and plink.get("status") == "created")
        results["razorpay_link"] = "PASS" if rzp_pass else "FAIL"
    except Exception as e:
        print("  Razorpay Exception:", str(e))
        results["razorpay_link"] = f"FAIL: {str(e)}"

    # Outbox job check
    target_job_id = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
    job = store.get_job(target_job_id, merchant_id=target_merchant_id)
    if job:
        print(f"\nTarget Job ID: {job.id}")
        print(f"  Merchant ID:            {job.merchant_id}")
        print(f"  Status:                 {job.status}")
        print(f"  Requires Approval:      {job.requires_operator_approval}")
        print(f"  Approved By:            {job.approved_by_operator_id}")
        print(f"  Approved At:            {job.approved_at}")
        print(f"  Approval Snapshot Hash: {job.approval_snapshot_hash}")
        print(f"  Worker ID:              {job.worker_id}")
        print(f"  Retry Count:            {job.retry_count}")
        print(f"  Recipient Masked:       {job.recipient_masked}")

        # Recipient test phone match
        clean_recipient_test = WhatsAppClient.sanitize_phone_number(settings.test_recipient_phone)
        clean_recipient_payload = WhatsAppClient.sanitize_phone_number(job.message_payload.get("to", ""))
        recip_match = clean_recipient_test == clean_recipient_payload
        print(f"  Recipient Matches Test Phone: {recip_match} ({clean_recipient_payload[:3]}****{clean_recipient_payload[-4:]})")

        # Opt-out check
        is_opted = opt_store.is_opted_out(settings.test_recipient_phone)
        print(f"  Recipient Opted Out:    {is_opted}")

        # Payload hash match
        recomputed_hash = compute_approval_hash(
            recipient_masked=job.recipient_masked,
            channel=job.channel,
            message_payload=job.message_payload,
        )
        print(f"  Recomputed Hash:        {recomputed_hash}")

        # Wamids check
        with dm.tenant_session_scope(target_merchant_id) as session:
            disp_count = session.execute(text("SELECT count(*) FROM public.recovery_dispatches WHERE outbox_id = :jid;"), {"jid": target_job_id}).scalar()
        print(f"  Dispatches Count:       {disp_count}")

        job_pass = (
            job.status == "PENDING_APPROVAL" and
            job.requires_operator_approval is True and
            job.approved_by_operator_id is None and
            job.approved_at is None and
            job.approval_snapshot_hash is None and
            job.worker_id is None and
            recip_match is True and
            is_opted is False and
            disp_count == 0
        )
        results["outbox_job"] = "PASS" if job_pass else "FAIL"
    else:
        print("Target job not found in DB!")
        results["outbox_job"] = "FAIL (Not found)"

    print("\n==================================================")
    print("SUMMARY RESULTS")
    print("==================================================")
    for k, v in results.items():
        print(f"  {k}: {v}")

    pass_keys = [
        "meta_phone",
        "meta_token",
        "fastapi_local",
        "fastapi_webhook_get",
        "public_health",
        "public_webhook_get",
        "service_window",
        "razorpay_link",
        "outbox_job",
    ]
    all_pass = all("PASS" in str(results.get(k, "")) for k in pass_keys) and results.get("ngrok_tunnels_count") == 1
    print(f"\nALL DEPENDENCIES PASS: {all_pass}")

if __name__ == "__main__":
    run_checks()
