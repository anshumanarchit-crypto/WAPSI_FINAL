import json
from pathlib import Path
import dotenv
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
env_vars = dotenv.dotenv_values(env_path)

token = env_vars.get("WHATSAPP_ACCESS_TOKEN", "").strip()
api_version = env_vars.get("WHATSAPP_API_VERSION", "v26.0").strip()

headers = {"Authorization": f"Bearer {token}"}

ids = ["122103630711527143", "61595814315120"]

with httpx.Client(timeout=10.0) as client:
    for uid in ids:
        print(f"\n================ ID: {uid} ================")
        # Test basic fields
        for field in [
            "id,name",
            "id,name,business",
            "id,name,role",
            "id,name,roles",
            "id,name,system_user_id",
            "id,name,is_system_user",
        ]:
            r = client.get(f"https://graph.facebook.com/{api_version}/{uid}?fields={field}", headers=headers)
            print(f"fields={field} -> {r.status_code}: {r.text[:200]}")
        
        # Test edge connections
        for edge in [
            "assigned_business_asset_groups",
            "assigned_users",
            "businesses",
            "whatsapp_business_accounts",
            "assigned_whatsapp_business_accounts",
            "assigned_business_assets",
        ]:
            r = client.get(f"https://graph.facebook.com/{api_version}/{uid}/{edge}", headers=headers)
            print(f"edge={edge} -> {r.status_code}: {r.text[:200]}")

