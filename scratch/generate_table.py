import json

pages = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/website_pages.json', encoding='utf-8'))
products = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/products.json', encoding='utf-8'))

prod_by_url = {}
for p in products:
    u = (p.get("product_url") or p.get("source_url") or "").rstrip("/")
    prod_by_url[u] = p

print("| # | Visited URL | Status | Page Title | In `products.json` | Category / Evidence |")
print("|---|---|---|---|---|---|")

for i, page in enumerate(pages):
    url = page.get("page_url", "").rstrip("/")
    title = page.get("title", "").replace("|", "-").replace("–", "-").replace("—", "-").strip()
    status = page.get("http_status")
    p_match = prod_by_url.get(url)
    
    in_prod = "YES" if p_match else "NO"
    
    if not p_match:
        if url == "https://medfreshe.com":
            cat = "SUPPRESSED: Root Homepage Guard (Phase 17.9)"
        elif "contact" in url:
            cat = "SUPPRESSED: Generic Title Guard ('contact')"
        elif "quality-control" in url:
            cat = "SUPPRESSED: Generic Title Guard ('quality control')"
        elif "about-us" in url:
            cat = "SUPPRESSED: Generic Title Guard ('about us')"
        elif "download-catalogues" in url:
            cat = "SUPPRESSED: Insufficient product/B2B content"
        else:
            cat = "SUPPRESSED: General Page Heuristic"
    else:
        num_imgs = len(p_match.get("images", []))
        if "company-profile" in url:
            cat = f"Generic Corporate (Uncertain) | imgs={num_imgs}"
        elif "consultancy" in url or "turnkey" in url:
            cat = f"Engineering/Consultancy Service | imgs={num_imgs}"
        elif "/modular-ot-icu-er/" in url:
            cat = f"Modular Sub-Component / Equipment | imgs={num_imgs}"
        else:
            cat = f"Valid B2B Medical Equipment | imgs={num_imgs}"
            
    print(f"| {i+1} | `{url}` | {status} | {title} | **{in_prod}** | {cat} |")
