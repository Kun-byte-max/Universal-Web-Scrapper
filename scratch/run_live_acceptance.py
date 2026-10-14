import time
import json
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8000/api"

payload = {
    "url": "https://medfreshe.com/modular-ot-icu-er/",
    "mode": "bounded",
    "max_pages": 1,
    "max_records": 5,
    "delay_seconds": 0.5,
    "use_browser_fallback": False
}

req_data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    f"{API_URL}/scrape",
    data=req_data,
    headers={"Content-Type": "application/json"}
)

print(f"Triggering bounded live crawl for {payload['url']}...")
try:
    with urllib.request.urlopen(req) as resp:
        res_data = json.loads(resp.read().decode())
        job_id = res_data["job_id"]
        print(f"Job launched successfully. Job ID: {job_id}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} - {e.read().decode()}")
    exit(1)
except Exception as e:
    print(f"Connection failed: {e}")
    exit(1)

# Poll for completion
start_time = time.time()
while True:
    time.sleep(1.0)
    try:
        with urllib.request.urlopen(f"{API_URL}/jobs/{job_id}") as resp:
            job_status = json.loads(resp.read().decode())
            status = job_status.get("status")
            progress = job_status.get("progress")
            msg = job_status.get("status_message")
            stats = job_status.get("stats", {})
            print(f"[{round(time.time() - start_time, 1)}s] Status: {status} ({progress}%) - {msg}")
            if status in ("completed", "failed"):
                print("\n=== FINAL JOB STATUS ===")
                print(json.dumps(job_status, indent=2))
                break
    except Exception as e:
        print(f"Polling error: {e}")

    if time.time() - start_time > 120:
        print("Polling timeout reached (120s)")
        break
