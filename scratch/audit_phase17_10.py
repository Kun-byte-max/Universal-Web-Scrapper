import json
from pathlib import Path

job_dir = Path(r"C:\UNG\Web_scrapper\output\012698a0-709b-4e66-b1ff-c5d456dfa251")

print("=== 1. EXTRACTION REPORT ===")
report_path = job_dir / "extraction_report.json"
if report_path.exists():
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    print(json.dumps(report, indent=2))

print("\n=== 2. WEBSITE PAGES INSPECTION ===")
pages_path = job_dir / "website_pages.json"
pages = []
if pages_path.exists():
    with open(pages_path, "r", encoding="utf-8") as f:
        pages = json.load(f)
    print(f"Total pages in website_pages.json: {len(pages)}")
    
    # Check for specific pages
    print("\nTarget key URLs in website_pages.json:")
    for key_url in [
        "https://medfreshe.com/",
        "https://medfreshe.com/contact/",
        "https://medfreshe.com/quality-control/",
        "https://medfreshe.com/medical-gas-pipeline-system/",
        "https://medfreshe.com/about/",
        "https://medfreshe.com/about-us/",
        "https://medfreshe.com/services/"
    ]:
        matches = [p for p in pages if p.get("page_url") == key_url or p.get("page_url") == key_url.rstrip("/")]
        if matches:
            p = matches[0]
            print(f"  FOUND {key_url}: title='{p.get('title')}', page_type='{p.get('page_type')}', status={p.get('http_status')}")
        else:
            print(f"  NOT FOUND in website_pages.json: {key_url}")

print("\n=== 3. ALL VISITED PAGES LIST ===")
for i, p in enumerate(pages):
    print(f"  {i+1}. page_type='{p.get('page_type')}' status={p.get('http_status')} title='{p.get('title')}' -> {p.get('page_url')}")

print("\n=== 4. PRODUCTS INSPECTION ===")
products_path = job_dir / "products.json"
products = []
if products_path.exists():
    with open(products_path, "r", encoding="utf-8") as f:
        products = json.load(f)
    print(f"Total records in products.json: {len(products)}")
    
    # Check if root homepage, contact, or quality control leaked
    for p in products:
        u = p.get("product_url") or p.get("source_url") or ""
        t = p.get("title", "")
        if u.rstrip("/") in ["https://medfreshe.com", "https://medfreshe.com/contact", "https://medfreshe.com/quality-control"]:
            print(f"  [LEAK ALERT] Found generic/excluded page in products.json: url={u}, title='{t}'")
            
    print(f"\nAll product titles and URLs (total {len(products)}):")
    for i, p in enumerate(products):
        print(f"  {i+1}. '{p.get('title')}' -> {p.get('product_url') or p.get('source_url')} (imgs={len(p.get('images', []))})")

print("\n=== 5. MEDICAL GAS PIPELINE SYSTEM RECORD ===")
mgps_records = [p for p in products if "medical-gas-pipeline-system" in (p.get("product_url") or p.get("source_url") or "")]
if mgps_records:
    mgps = mgps_records[0]
    print(f"Title: {mgps.get('title')}")
    print(f"Source URL: {mgps.get('source_url')}")
    print(f"Product URL: {mgps.get('product_url')}")
    print(f"Primary image_url: {mgps.get('image_url')}")
    print(f"Legacy image_urls count: {len(mgps.get('image_urls', []))}")
    structured_imgs = mgps.get("images", [])
    print(f"Structured images count: {len(structured_imgs)}")
    
    # Check image attributes
    has_url = sum(1 for img in structured_imgs if img.get("image_url"))
    has_title = sum(1 for img in structured_imgs if img.get("title"))
    has_section = sum(1 for img in structured_imgs if img.get("section_title"))
    has_alt = sum(1 for img in structured_imgs if img.get("alt"))
    has_caption = sum(1 for img in structured_imgs if img.get("caption"))
    
    print(f" - Structured images with image_url: {has_url}/{len(structured_imgs)}")
    print(f" - Structured images with title: {has_title}/{len(structured_imgs)}")
    print(f" - Structured images with section_title: {has_section}/{len(structured_imgs)}")
    print(f" - Structured images with alt: {has_alt}/{len(structured_imgs)}")
    print(f" - Structured images with caption: {has_caption}/{len(structured_imgs)}")
    
    # URL parity check
    struct_urls = [img.get("image_url") for img in structured_imgs]
    legacy_urls = mgps.get("image_urls", [])
    print(f" - Struct URLs count vs Legacy URLs count: {len(struct_urls)} vs {len(legacy_urls)}")
    print(f" - Exact list match: {struct_urls == legacy_urls}")
    
    # Sample images
    print("\nSample structured images (first 8):")
    for i, img in enumerate(structured_imgs[:8]):
        print(f"  Image {i+1}:")
        print(f"    URL: {img.get('image_url')}")
        print(f"    Title: {img.get('title')}")
        print(f"    Section: {img.get('section_title')}")
        print(f"    Alt: {img.get('alt')}")
        print(f"    Caption: {img.get('caption')}")
else:
    print("Medical Gas Pipeline System NOT FOUND in products.json!")

print("\n=== 6. SITEMAP INVENTORY ===")
sitemap_path = job_dir / "sitemap_inventory.json"
if sitemap_path.exists():
    with open(sitemap_path, "r", encoding="utf-8") as f:
        print(f"sitemap_inventory.json content: {f.read()}")
