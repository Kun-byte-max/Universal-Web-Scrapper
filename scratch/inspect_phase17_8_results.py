import json
from pathlib import Path

job_dir = Path("output/3661078d-029d-44ca-a38a-9b6453effdaf")

# 1. Inspect website_pages.json
pages_path = job_dir / "website_pages.json"
pages = json.load(open(pages_path, "r", encoding="utf-8"))
print(f"=== TOTAL VISITED PAGES: {len(pages)} ===")
for i, p in enumerate(pages, 1):
    print(f"Page {i}:")
    print(f"  URL: {p.get('page_url')}")
    print(f"  Title: {p.get('title')}")
    print(f"  Page Type: {p.get('page_type')}")
    print(f"  HTTP Status: {p.get('http_status')}")
    print(f"  Images on page: {len(p.get('images', []))}")

# 2. Inspect products.json
prods_path = job_dir / "products.json"
products = json.load(open(prods_path, "r", encoding="utf-8"))
print(f"\n=== TOTAL EXTRACTED PRODUCTS: {len(products)} ===")
for i, p in enumerate(products, 1):
    print(f"Product {i}:")
    print(f"  Title: {p.get('title')}")
    print(f"  Product URL: {p.get('product_url')}")
    print(f"  Source URL: {p.get('source_url')}")
    desc = p.get('description') or ''
    print(f"  Description: {desc[:90]}..." if len(desc) > 90 else f"  Description: {desc}")
    print(f"  Primary Image URL: {p.get('image_url')}")
    print(f"  Legacy Image URLs Count: {len(p.get('image_urls', []))}")
    print(f"  Structured Images Count: {len(p.get('images', []))}")
    imgs = p.get('images', [])
    if imgs:
        sample = imgs[0]
        print(f"  Sample Image 1: URL={sample.get('image_url')}, Title={sample.get('title')}, Section={sample.get('section_title')}")
