import json

products = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/products.json', encoding='utf-8'))

print(f"Total products: {len(products)}")

categories = {
    "Equipment & Systems": [],
    "Sub-components & Modular OT/ICU": [],
    "Engineering & Consultancy Services": [],
    "Generic Corporate / Uncertain": []
}

for p in products:
    title = p.get("title", "")
    url = p.get("product_url") or p.get("source_url") or ""
    imgs = len(p.get("images", []))
    
    if "company-profile" in url.lower():
        categories["Generic Corporate / Uncertain"].append((title, url, imgs, p.get("description")[:100]))
    elif "consultancy" in title.lower() or "designing" in title.lower():
        categories["Engineering & Consultancy Services"].append((title, url, imgs, p.get("description")[:100]))
    elif "/modular-ot-icu-er/" in url:
        categories["Sub-components & Modular OT/ICU"].append((title, url, imgs, p.get("description")[:100]))
    else:
        categories["Equipment & Systems"].append((title, url, imgs, p.get("description")[:100]))

for cat, items in categories.items():
    print(f"\n=== {cat} ({len(items)}) ===")
    for t, u, imgs, d in items:
        clean_t = t.split("–")[0].split("-")[0].strip()
        print(f"  * {clean_t} | imgs={imgs} | {u}")
