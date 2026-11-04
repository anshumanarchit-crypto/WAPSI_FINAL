import os
import sys
from pathlib import Path
import dotenv
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
env = dotenv.dotenv_values(env_path)

token = env.get("WHATSAPP_ACCESS_TOKEN", "").strip()
phone_id = env.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
ver = env.get("WHATSAPP_API_VERSION", "v26.0").strip()
recipient = env.get("TEST_RECIPIENT_PHONE", "").strip()

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

# Clean recipient
clean_phone = "".join(filter(str.isdigit, recipient))
if len(clean_phone) == 10:
    clean_phone = "91" + clean_phone

# Test 1: template hello_world
payload_template = {
    "messaging_product": "whatsapp",
    "to": clean_phone,
    "type": "template",
    "template": {
        "name": "hello_world",
        "language": {"code": "en_US"}
    }
}

r1 = httpx.post(f"https://graph.facebook.com/{ver}/{phone_id}/messages", headers=headers, json=payload_template)
print("Template Response HTTP:", r1.status_code)
print(r1.text)

# Test 2: text message
payload_text = {
    "messaging_product": "whatsapp",
    "to": clean_phone,
    "type": "text",
    "text": {
        "body": "Hello from WAPSI test"
    }
}
r2 = httpx.post(f"https://graph.facebook.com/{ver}/{phone_id}/messages", headers=headers, json=payload_text)
print("\nText Response HTTP:", r2.status_code)
print(r2.text)

