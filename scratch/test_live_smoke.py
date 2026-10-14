import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import json
import time
from pathlib import Path
from app.models import ScrapeRequest

from app.scraper.scrapy_engine.runner import ScrapyJobRunner
from app.config import OUTPUT_DIR

def run_smoke_test():
    print("Starting Bounded Live Smoke Test (Phase 5) against https://medfreshe.com/...")
    req = ScrapeRequest(
        url="https://medfreshe.com/",
        max_pages=5,
        max_records=10,
        delay_seconds=1.0
    )
    
    start_t = time.time()
    records, stats = ScrapyJobRunner.run_job(req, "smoke_test_phase5")
    duration = time.time() - start_t
    
    print("\n--- Phase 5 Smoke Test Results ---")
    print(f"Pages Visited: {stats.pages_visited}")
    print(f"Products Extracted: {len(records)}")
    print(f"Duration: {duration:.2f}s")
    print(f"Errors: {stats.errors}")

    smoke_dir = OUTPUT_DIR / "smoke_test_phase5"
    if smoke_dir.exists():
        for filename in ["website_pages.json", "products.json", "sitemap_inventory.json", "extraction_report.json"]:
            fpath = smoke_dir / filename
            if fpath.exists():
                size = fpath.stat().st_size
                print(f"Generated output file: {filename} ({size} bytes)")


if __name__ == "__main__":
    run_smoke_test()
