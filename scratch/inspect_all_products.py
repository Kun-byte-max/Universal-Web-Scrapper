import json
from pathlib import Path

job_dir = Path("output/3661078d-029d-44ca-a38a-9b6453effdaf")
products = json.load(open(job_dir / "products.json", "r", encoding="utf-8"))

for i, p in enumerate(products, 1):
    imgs = p.get("images", [])
    img_urls = p.get("image_urls", [])
    print(f"Product {i}: {p['title']}")
    print(f"  URL: {p['product_url']}")
    print(f"  Primary Img: {p['image_url']}")
    print(f"  Legacy img_urls count: {len(img_urls)}")
    print(f"  Structured images count: {len(imgs)}")
    with_title = sum(1 for img in imgs if img.get("title"))
    with_sec = sum(1 for img in imgs if img.get("section_title"))
    print(f"  Structured with title: {with_title}, with section: {with_sec}")
