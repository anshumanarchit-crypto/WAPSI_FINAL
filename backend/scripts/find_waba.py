import os
import sys
from pathlib import Path
import dotenv
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
env = dotenv.dotenv_values(env_path)

token = env.get("WHATSAPP_ACCESS_TOKEN", "").strip()
app_id = "963047183124334"
user_id = "122103630711527143"
phone_id = env.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
ver = env.get("WHATSAPP_API_VERSION", "v26.0").strip()

headers = {"Authorization": f"Bearer {token}"}

# Query businesses and shared WABAs
for endpoint in [
    f"https://graph.facebook.com/{ver}/{user_id}/businesses",
    f"https://graph.facebook.com/{ver}/{user_id}/assigned_business_asset_groups",
    f"https://graph.facebook.com/{ver}/{app_id}/whatsapp_business_accounts",
    f"https://graph.facebook.com/{ver}/me/businesses",
    f"https://graph.facebook.com/{ver}/{phone_id}?fields=whatsapp_business_api_data",
]:
    r = httpx.get(endpoint, headers=headers)
    print(f"--- Endpoint: {endpoint} ---")
    print(r.status_code, r.text)

