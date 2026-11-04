"""
Read-only webhook readiness check.
"""

import httpx
from wapsi.core.config import get_settings

def check():
    settings = get_settings()
    base_url = str(settings.public_base_url).strip().rstrip("/")
    print("public_base_url:", base_url)

    # 1. Local FastAPI health check
    try:
        resp_local = httpx.get("http://127.0.0.1:8000/health", timeout=3.0)
        print("Local FastAPI Health Status:", resp_local.status_code, resp_local.json() if resp_local.status_code == 200 else resp_local.text[:100])
    except Exception as e:
        print("Local FastAPI Health Error:", str(e))

    # 2. Public Base URL health check (via ngrok)
    if base_url:
        public_url = f"{base_url}/health"
        try:
            resp_pub = httpx.get(public_url, timeout=5.0)
            print("Public Base URL Health Status:", resp_pub.status_code, resp_pub.json() if resp_pub.status_code == 200 else resp_pub.text[:100])
        except Exception as e:
            print("Public Base URL Health Error:", str(e))

        # 3. Webhook GET verification endpoint check
        webhook_get_url = f"{base_url}/api/v1/webhooks/whatsapp"
        verify_token = settings.whatsapp_webhook_verify_token.get_secret_value() if settings.whatsapp_webhook_verify_token else "test_token"
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": verify_token,
            "hub.challenge": "123456789"
        }
        try:
            resp_wh = httpx.get(webhook_get_url, params=params, timeout=5.0)
            print("Webhook Verification GET Status:", resp_wh.status_code, "Challenge Match:", resp_wh.text == "123456789")
        except Exception as e:
            print("Webhook Verification GET Error:", str(e))

if __name__ == "__main__":
    check()
