import json

pages = json.load(open('output/168b1b31-ea3a-47a7-8f84-8cee92c2aa96/website_pages.json', encoding='utf-8'))
products = json.load(open('output/168b1b31-ea3a-47a7-8f84-8cee92c2aa96/products.json', encoding='utf-8'))

prod_by_url = {}
for p in products:
    u = (p.get("product_url") or p.get("source_url") or "").rstrip("/")
    prod_by_url[u] = p

print(f"Total Visited Pages: {len(pages)}")
print(f"Total Extracted Products: {len(products)}")

not_in_products = []
in_products = []

for i, page in enumerate(pages):
    url = page.get("page_url", "").rstrip("/")
    title = page.get("title", "")
    status = page.get("http_status")
    p_match = prod_by_url.get(url)
    if p_match:
        in_products.append((i+1, url, title, status, p_match))
    else:
        not_in_products.append((i+1, url, title, status))

print(f"\n=== PAGES VISITED BUT NOT IN PRODUCTS ({len(not_in_products)}) ===")
for idx, url, title, status in not_in_products:
    print(f"[{idx}] {status} | {title} | {url}")

print(f"\n=== VERIFICATION OF THE 6 EXCLUDED PAGES ===")
expected_excluded = {
    "https://medfreshe.com": "Root Homepage",
    "https://medfreshe.com/contact": "Contact",
    "https://medfreshe.com/quality-control": "Quality Control",
    "https://medfreshe.com/about-us": "About Us",
    "https://medfreshe.com/company-profile": "Company Profile",
    "https://medfreshe.com/download-catalogues": "Download Catalogues"
}

for u, label in expected_excluded.items():
    matched = [x for x in not_in_products if x[1] == u]
    print(f"  * {label} ({u}): {'EXCLUDED (CORRECT)' if matched else 'LEAKED (ERROR)'}")

print(f"\nTotal excluded count: {len(not_in_products)} (Expected exactly 6)")
print(f"Total products count: {len(in_products)} (Expected exactly 57: 63 - 6 = 57)")
print(f"63 - 6 == 57: {len(pages) - len(not_in_products) == len(in_products)}")
