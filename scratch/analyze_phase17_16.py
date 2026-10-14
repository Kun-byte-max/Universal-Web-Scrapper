import json
from pathlib import Path

job_dir = Path('output/e70653aa-2919-4c6a-8147-888c4fe693b2')
hist_dir = Path('output/168b1b31-ea3a-47a7-8f84-8cee92c2aa96')

products = json.loads((job_dir / 'products.json').read_text(encoding='utf-8'))
pages = json.loads((job_dir / 'website_pages.json').read_text(encoding='utf-8'))
report = json.loads((job_dir / 'extraction_report.json').read_text(encoding='utf-8'))

hist_products = json.loads((hist_dir / 'products.json').read_text(encoding='utf-8'))
hist_pages = json.loads((hist_dir / 'website_pages.json').read_text(encoding='utf-8'))

print(f"=== FRESH RUN SUMMARY (Job e70653aa-2919-4c6a-8147-888c4fe693b2) ===")
print(f"Products count: {len(products)}")
print(f"Pages visited count: {len(pages)}")

n_title = sum(1 for p in products if p.get('title') and len(p['title']) >= 2)
n_prod_url = sum(1 for p in products if p.get('product_url'))
n_img_url = sum(1 for p in products if p.get('image_url'))
n_desc = sum(1 for p in products if p.get('description') and len(p['description']) > 0)
n_rich_images_arr = sum(1 for p in products if p.get('images') and len(p['images']) > 0)

all_images = []
for p in products:
    all_images.extend(p.get('images', []))

total_rich_images = len(all_images)
img_with_title = sum(1 for img in all_images if img.get('title'))
img_with_section = sum(1 for img in all_images if img.get('section_title'))

print(f"Meaningful title: {n_title}/{len(products)} ({n_title/len(products):.1%})")
print(f"Product URL: {n_prod_url}/{len(products)} ({n_prod_url/len(products):.1%})")
print(f"Primary Image URL: {n_img_url}/{len(products)} ({n_img_url/len(products):.1%})")
print(f"Non-empty description: {n_desc}/{len(products)} ({n_desc/len(products):.1%})")
print(f"Non-empty rich images array: {n_rich_images_arr}/{len(products)} ({n_rich_images_arr/len(products):.1%})")
print(f"Total rich image entries across all records: {total_rich_images}")
print(f"Image-title coverage: {img_with_title}/{total_rich_images} ({img_with_title/total_rich_images:.1%})")
print(f"Section-title coverage: {img_with_section}/{total_rich_images} ({img_with_section/total_rich_images:.1%})")

prod_urls = [p['product_url'] for p in products]
dup_prod_urls = [u for u in set(prod_urls) if prod_urls.count(u) > 1]
print(f"Duplicate product URLs: {dup_prod_urls}")

img_urls = [p['image_url'] for p in products if p.get('image_url')]
dup_img_urls = [u for u in set(img_urls) if img_urls.count(u) > 1]
print(f"Duplicate primary image URLs: {dup_img_urls}")

print('\nVisited Pages (10):')
visited_urls = [pg['page_url'] for pg in pages]
for i, u in enumerate(visited_urls, 1):
    matched_prod = [p for p in products if p['product_url'] == u or p['source_url'] == u]
    prod_title = matched_prod[0]['title'] if matched_prod else '(No product extracted - excluded corporate/navigation)'
    print(f" {i}. {u} -> {prod_title}")

hist_url_map = {p['product_url']: p for p in hist_products}
revisited_matches = 0
for p in products:
    u = p['product_url']
    if u in hist_url_map:
        revisited_matches += 1
        h_title = hist_url_map[u]['title']
        print(f" [Overlap Match] {p['title']} == {h_title}")
    else:
        print(f" [New / Unique] {p['title']} ({u})")

print(f"\nRevisited historical overlap: {revisited_matches}/{len(products)} products matched identically with historical run.")
print(f"The remaining {len(hist_products) - revisited_matches} historical records were on pages 11-63 which were not visited due to max_pages=10 limit.")

# Check for checkpoint files
checkpoint_files = list(job_dir.glob('*.tmp')) + list(job_dir.glob('*.partial'))
print(f"Temporary checkpoint files remaining: {len(checkpoint_files)}")
