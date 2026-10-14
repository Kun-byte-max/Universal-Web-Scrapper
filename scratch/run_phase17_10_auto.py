import sys
import os
import uuid
import json
import time
from pathlib import Path

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath('.'))

from fastapi.testclient import TestClient
from app.main import app
from app.config import OUTPUT_DIR

def run_phase17_10_auto():
    client = TestClient(app)
    
    target_url = "https://medfreshe.com/medical-gas-pipeline-system/"
    print("=== PHASE 17.10 CONTROLLED AUTO-MODE LIVE ACCEPTANCE RUN ===")
    print(f"Target URL: {target_url}")
    print("Mode: auto (URL-only Auto mode, no max_pages/max_records provided)")
    
    start_time = time.time()
    response = client.post("/api/scrape", json={
        "url": target_url,
        "mode": "auto",
        "delay_seconds": 0.5,
        "use_browser_fallback": False
    })
    
    print(f"API /scrape status: {response.status_code}")
    job_data = response.json()
    job_id = job_data.get("job_id")
    print(f"Fresh Job ID: {job_id}")
    
    # Query final job status
    status_resp = client.get(f"/api/jobs/{job_id}")
    final_job = status_resp.json()
    duration = time.time() - start_time
    
    print(f"\nFinal Job Status: {final_job.get('status')}")
    print(f"Status Message: {final_job.get('status_message')}")
    print(f"Overall Duration: {duration:.2f}s")
    
    stats = final_job.get("stats", {})
    print(f"Pages Visited: {stats.get('pages_visited')}")
    print(f"Records Extracted: {stats.get('records_extracted')}")
    print(f"Stop Reason: {stats.get('stop_reason')}")
    print(f"Crawl Complete: {stats.get('crawl_complete')}")
    print(f"Errors: {stats.get('errors')}")
    
    output_dir = OUTPUT_DIR / job_id
    print(f"\nOutput Directory: {output_dir}")
    if output_dir.exists():
        for fname in ["extraction_report.json", "website_pages.json", "products.json", "sitemap_inventory.json"]:
            fpath = output_dir / fname
            if fpath.exists():
                print(f" - {fname}: {fpath.stat().st_size} bytes")
            else:
                print(f" - {fname}: NOT FOUND")

if __name__ == "__main__":
    run_phase17_10_auto()
