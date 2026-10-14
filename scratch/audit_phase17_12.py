import json
from pathlib import Path

job_id = "168b1b31-ea3a-47a7-8f84-8cee92c2aa96"
output_dir = Path(f"output/{job_id}")

print("=== 1. EXTRACTION REPORT ===")
report_file = output_dir / "extraction_report.json"
report = json.loads(report_file.read_text(encoding="utf-8"))
print(json.dumps(report, indent=2))

print("\n=== 2. WEBSITE PAGES AUDIT ===")
pages_file = output_dir / "website_pages.json"
pages = json.loads(pages_file.read_text(encoding="utf-8"))
print(f"Total pages in website_pages.json: {len(pages)}")

print("\n=== 3. PRODUCTS AUDIT ===")
products_file = output_dir / "products.json"
products = json.loads(products_file.read_text(encoding="utf-8"))
print(f"Total records in products.json: {len(products)}")

# Check exclusion of generic pages
prod_urls = { (p.get("product_url") or p.get("source_url") or "").rstrip("/") for p in products }
prod_titles = [ p.get("title") for p in products ]

excluded_checks = [
    ("https://medfreshe.com", "Root Homepage"),
    ("https://medfreshe.com/contact", "Contact"),
    ("https://medfreshe.com/about-us", "About Us"),
    ("https://medfreshe.com/quality-control", "Quality Control"),
    ("https://medfreshe.com/company-profile", "Company Profile"),
    ("https://medfreshe.com/download-catalogues", "Download Catalogues")
]

print("\n--- Excluded Generic Pages Check ---")
for url, name in excluded_checks:
    in_prod = url in prod_urls
    print(f"  {name} ({url}): In products.json? {in_prod} (PASS: {not in_prod})")

# Check if any product title contains Company Profile
cp_titles = [t for t in prod_titles if "company profile" in t.lower()]
print(f"  Products with 'Company Profile' in title: {cp_titles} (PASS: {len(cp_titles) == 0})")

print("\n=== 4. MEDICAL GAS PIPELINE SYSTEM RECORD ===")
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
    
    # URL parity check
    struct_urls = [img.get("image_url") for img in structured_imgs]
    legacy_urls = mgps.get("image_urls", [])
    parity = (struct_urls == legacy_urls)
    print(f"URL parity (struct == legacy): {parity}")
    
    # Attribute coverage
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
else:
    print("Medical Gas Pipeline System NOT FOUND!")

print("\n=== 5. SITEMAP INVENTORY ===")
sitemap_file = output_dir / "sitemap_inventory.json"
sitemap_content = sitemap_file.read_text(encoding="utf-8")
print(f"sitemap_inventory.json content: {sitemap_content}")

print("\n=== 6. CHECK FOR LOG EXCEPTIONS IN task-1761.log ===")
log_path = Path(r"C:\Users\Comp85\.gemini\antigravity-ide\brain\310e96d8-4e98-4a94-9292-dd00d3646d70\.system_generated\tasks\task-1761.log")
if log_path.exists():
    log_text = log_path.read_text(encoding="utf-8", errors="ignore")
    import re
    attr_errors = len(re.findall(r"AttributeError", log_text))
    text_errors = len(re.findall(r"Response content isn't text", log_text))
    tracebacks = len(re.findall(r"Traceback \(most recent call last\):", log_text))
    spider_errs = len(re.findall(r"Spider error processing", log_text))
    
    print(f"AttributeError count in log: {attr_errors}")
    print(f"'Response content isn't text' count in log: {text_errors}")
    print(f"Traceback count in log: {tracebacks}")
    print(f"Spider error processing count in log: {spider_errs}")
