import json

pages = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/website_pages.json', encoding='utf-8'))
products = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/products.json', encoding='utf-8'))

print(f"Total pages visited: {len(pages)}")
print(f"Total products extracted: {len(products)}")

# Create lookup of products by URL
prod_urls = set()
for p in products:
    u = p.get("product_url") or p.get("source_url")
    if u:
        prod_urls.add(u.rstrip("/"))

print("\n--- Key Pages Classification Check ---")
for target in [
    "https://medfreshe.com",
    "https://medfreshe.com/contact",
    "https://medfreshe.com/quality-control",
    "https://medfreshe.com/medical-gas-pipeline-system",
    "https://medfreshe.com/automated-pharmacy-dispensing-system",
    "https://medfreshe.com/electric-track-vehicle",
    "https://medfreshe.com/oxygen-generation-system",
    "https://medfreshe.com/smart-bin-system",
    "https://medfreshe.com/hospital-consultancy-designing-on-turnkey-basis",
    "https://medfreshe.com/pneumatic-tube-system",
    "https://medfreshe.com/company-profile",
    "https://medfreshe.com/pneumatic-waste-laundry-collection-system"
]:
    # find in pages
    matching_pages = [p for p in pages if p['page_url'].rstrip("/") == target]
    in_pages = len(matching_pages) > 0
    page_type = matching_pages[0].get('page_type') if in_pages else 'NOT_VISITED'
    title = matching_pages[0].get('title') if in_pages else 'N/A'
    in_products = target in prod_urls
    print(f"Target: {target}")
    print(f"  Visited: {in_pages} | Page Type: {page_type} | In Products: {in_products} | Title: {title}")
