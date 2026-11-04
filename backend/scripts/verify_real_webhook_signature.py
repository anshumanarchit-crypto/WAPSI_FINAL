import dotenv
import hmac
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
env = dotenv.dotenv_values(PROJECT_ROOT / ".env")
meta_secret = env.get("META_APP_SECRET", "").strip()

# Raw body from ngrok
raw_body = b'{"object":"whatsapp_business_account","entry":[{"id":"969727602419694","changes":[{"value":{"messaging_product":"whatsapp","metadata":{"display_phone_number":"15552148539","phone_number_id":"1407090562487899"},"contacts":[{"profile":{"name":"Arpit Jham"},"wa_id":"916260055671","user_id":"IN.1481829960534905"}],"messages":[{"from":"916260055671","from_user_id":"IN.1481829960534905","id":"wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBQjRBNEU4NTk3NEI2RjVFMjQ1Njc4QTVDNzg5QjQA","timestamp":"1793637318","text":{"body":"Hii"},"type":"text"}]},"field":"messages"}]}]}'

header_sig = "sha256=0a8a585adbb1a8382646fa328610951e63da86bfed66d8924520f0400bf25c6c"
expected_hex = header_sig.replace("sha256=", "")
computed_hex = hmac.new(meta_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

is_valid = hmac.compare_digest(computed_hex, expected_hex)
print(f"Signature Valid: {is_valid}")
print(f"Header Hex:   {expected_hex}")
print(f"Computed Hex: {computed_hex}")

