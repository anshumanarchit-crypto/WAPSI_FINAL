import httpx
import json

r = httpx.get("http://127.0.0.1:4040/api/requests/http?limit=50")
if r.status_code == 200:
    reqs = r.json().get("requests", [])
    print(f"Captured requests: {len(reqs)}")
    for idx, req in enumerate(reqs):
        r_info = req.get("request", {})
        resp_info = req.get("response", {})
        uri = req.get("uri")
        # Fetch full details of request
        detail_r = httpx.get(f"http://127.0.0.1:4040{uri}")
        if detail_r.status_code == 200:
            d = detail_r.json()
            r_full = d.get("request", {})
            raw_url = r_full.get("raw_url", "")
            method = r_full.get("method", "")
            headers = r_full.get("headers", {})
            body = r_full.get("body", "")
            resp_full = d.get("response", {})
            resp_status = resp_full.get("status_code", 0)
            resp_body = resp_full.get("body", "")
            
            print(f"\n================ [{idx}] {method} {raw_url} -> HTTP {resp_status} ================")
            print("Headers:")
            for h, v in headers.items():
                if "signature" in h.lower() or "user-agent" in h.lower() or "content-type" in h.lower():
                    print(f"  {h}: {v}")
            if body:
                print("Body (first 500 chars):")
                print(body[:500])
            if resp_body:
                print("Response Body:")
                print(resp_body[:200])

