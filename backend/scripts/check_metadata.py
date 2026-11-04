import dotenv
import httpx
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
env_vars = dotenv.dotenv_values(env_path)
token = env_vars.get("WHATSAPP_ACCESS_TOKEN", "").strip()
ver = env_vars.get("WHATSAPP_API_VERSION", "v26.0").strip()
headers = {"Authorization": f"Bearer {token}"}

with httpx.Client(timeout=10.0) as client:
    for uid in ["61595814315120", "122103630711527143"]:
        print(f"\n--- Checking {uid} metadata ---")
        r = client.get(f"https://graph.facebook.com/{ver}/{uid}?metadata=1", headers=headers)
        print("Status:", r.status_code)
        if r.status_code == 200:
            print(r.json())
        else:
            print(r.text)

