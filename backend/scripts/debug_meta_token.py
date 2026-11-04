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

headers = {"Authorization": f"Bearer {token}"}

# Check token debug info
print("=== Checking Debug Token / Me ===")
r_me = httpx.get(f"https://graph.facebook.com/{ver}/me?fields=id,name", headers=headers)
print("Me HTTP:", r_me.status_code, r_me.text)

r_debug = httpx.get(f"https://graph.facebook.com/debug_token?input_token={token}&access_token={token}")
print("Debug Token HTTP:", r_debug.status_code, r_debug.text)

print("\n=== Checking Phone Number Fields ===")
r_phone = httpx.get(
    f"https://graph.facebook.com/{ver}/{phone_id}?fields=id,display_phone_number,verified_name,status",
    headers=headers
)
print("Phone HTTP:", r_phone.status_code, r_phone.text)

