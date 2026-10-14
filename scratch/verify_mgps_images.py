import json

pages = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/website_pages.json', encoding='utf-8'))
products = json.load(open('output/012698a0-709b-4e66-b1ff-c5d456dfa251/products.json', encoding='utf-8'))

mgps_prod = [p for p in products if "medical-gas-pipeline-system" in (p.get("product_url") or "")][0]
mgps_page = [p for p in pages if "medical-gas-pipeline-system" in p.get("page_url", "")][0]

structured_images = mgps_prod.get("images", [])
legacy_image_urls = mgps_prod.get("image_urls", [])

print("=== IMAGE METADATA METRICS ===")
print(f"Total structured images: {len(structured_images)}")
print(f"Total legacy image_urls: {len(legacy_image_urls)}")
print(f"Primary image_url: {mgps_prod.get('image_url')}")
print(f"URL Parity (struct URLs == legacy URLs): {[img.get('image_url') for img in structured_images] == legacy_image_urls}")

# Duplicates check
struct_urls = [img.get('image_url') for img in structured_images]
unique_struct_urls = set(struct_urls)
print(f"Unique image URLs in structured images: {len(unique_struct_urls)} / {len(struct_urls)}")

# Field presence
has_url = sum(1 for img in structured_images if img.get("image_url"))
has_title = sum(1 for img in structured_images if img.get("title"))
has_section = sum(1 for img in structured_images if img.get("section_title"))
has_alt = sum(1 for img in structured_images if img.get("alt"))
has_caption = sum(1 for img in structured_images if img.get("caption"))

print(f"Presence of image_url: {has_url}/{len(structured_images)} ({has_url/len(structured_images)*100:.1f}%)")
print(f"Presence of title: {has_title}/{len(structured_images)} ({has_title/len(structured_images)*100:.1f}%)")
print(f"Presence of section_title: {has_section}/{len(structured_images)} ({has_section/len(structured_images)*100:.1f}%)")
print(f"Presence of alt: {has_alt}/{len(structured_images)} ({has_alt/len(structured_images)*100:.1f}%)")
print(f"Presence of caption: {has_caption}/{len(structured_images)} ({has_caption/len(structured_images)*100:.1f}%)")

print("\n=== SAMPLE STRUCTURED IMAGES CHECK ===")
# Let's inspect sections present across all 79 images
sections = {}
for img in structured_images:
    sec = img.get("section_title") or "NONE"
    sections[sec] = sections.get(sec, 0) + 1
print("Section title distribution:")
for sec, cnt in sections.items():
    print(f"  * '{sec}': {cnt} images")

print("\nSample 10 structured images:")
for i in [0, 1, 10, 20, 30, 40, 50, 60, 70, 78]:
    img = structured_images[i]
    print(f"Image [{i+1}]:")
    print(f"  URL: {img.get('image_url')}")
    print(f"  Title: {img.get('title')}")
    print(f"  Section: {img.get('section_title')}")
    print(f"  Alt: {img.get('alt')}")
    print(f"  Caption: {img.get('caption')}")
