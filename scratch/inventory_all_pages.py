import json

pages = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/website_pages.json', encoding='utf-8'))
products = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/products.json', encoding='utf-8'))

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

print(f"\n=== PAGES VISITED AND EMITTED AS PRODUCTS ({len(in_products)}) ===")
for idx, url, title, status, p in in_products:
    num_imgs = len(p.get("images", []))
    print(f"[{idx}] {status} | imgs={num_imgs} | ProdTitle: '{p.get('title')}' | URL: {url}")
