import json
from pathlib import Path

job_dir = Path("output/c60f96e0-835a-4076-b5f7-7481564df6dd")

report = json.loads((job_dir / "extraction_report.json").read_text(encoding="utf-8"))
pages = json.loads((job_dir / "website_pages.json").read_text(encoding="utf-8"))
products = json.loads((job_dir / "products.json").read_text(encoding="utf-8"))

print("=== QUOTES TO SCRAPE EXTRACTION REPORT ===")
print(json.dumps(report, indent=2))

print(f"\nTotal pages visited: {len(pages)}")
for i, p in enumerate(pages):
    print(f"Page {i+1}: {p.get('page_url')} | Title: '{p.get('title')}'")

print(f"\nTotal products extracted: {len(products)}")
for i, p in enumerate(products):
    print(f"\nRecord {i+1}:")
    print(f"  Title: {p.get('title')}")
    print(f"  Description: {p.get('description')}")
    print(f"  Product URL: {p.get('product_url')}")
    print(f"  Source URL: {p.get('source_url')}")
    print(f"  Price: {p.get('price')} {p.get('currency')}")
    print(f"  Images: {len(p.get('images', []))}")
