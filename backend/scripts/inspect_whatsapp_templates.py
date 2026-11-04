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

print(f"=== Phone ID: {phone_id} ===")
r_phone = httpx.get(
    f"https://graph.facebook.com/{ver}/{phone_id}?fields=id,display_phone_number,verified_name,quality_rating,name_status,code_verification_status",
    headers=headers
)
print("Phone HTTP:", r_phone.status_code)
if r_phone.status_code == 200:
    print(r_phone.json())
else:
    print(r_phone.text)
