import json
from pathlib import Path

job_dir = Path("output/b22b2788-d60b-46b6-800b-9d8c2d86bb9c")

report = json.loads((job_dir / "extraction_report.json").read_text(encoding="utf-8"))
pages = json.loads((job_dir / "website_pages.json").read_text(encoding="utf-8"))
products = json.loads((job_dir / "products.json").read_text(encoding="utf-8"))

print("=== BOOKS TO SCRAPE EXTRACTION REPORT ===")
print(json.dumps(report, indent=2))

print(f"\nTotal pages: {len(pages)}")
print(f"Total products: {len(products)}")

print("\n=== SAMPLE EXTRACTED BOOKS (First 5 of 20) ===")
for i, p in enumerate(products[:5]):
    print(f"Book {i+1}:")
    print(f"  Title: {p.get('title')}")
    print(f"  Price: {p.get('price')} {p.get('currency')}")
    print(f"  Product URL: {p.get('product_url')}")
    print(f"  Image URL: {p.get('image_url')}")
    print(f"  Structured Images Count: {len(p.get('images', []))}")
    if p.get('images'):
        img0 = p['images'][0]
        print(f"  Sample Image: url={img0.get('image_url')}, alt='{img0.get('alt')}', section='{img0.get('section_title')}'")

print("\n=== BOOK EXTRACTION METRICS ===")
has_title = sum(1 for p in products if p.get('title'))
has_price = sum(1 for p in products if p.get('price') is not None)
has_img = sum(1 for p in products if p.get('image_url'))
has_url = sum(1 for p in products if p.get('product_url'))

print(f"Titles populated: {has_title}/{len(products)} ({has_title/len(products)*100:.1f}%)")
print(f"Prices populated: {has_price}/{len(products)} ({has_price/len(products)*100:.1f}%)")
print(f"Images populated: {has_img}/{len(products)} ({has_img/len(products)*100:.1f}%)")
print(f"Product URLs populated: {has_url}/{len(products)} ({has_url/len(products)*100:.1f}%)")
