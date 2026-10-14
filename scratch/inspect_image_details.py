import json
from pathlib import Path

job_dir = Path("output/3661078d-029d-44ca-a38a-9b6453effdaf")
products = json.load(open(job_dir / "products.json", "r", encoding="utf-8"))

med_gas = products[0]
print(f"Product: {med_gas['title']}")
print(f"Total structured images: {len(med_gas['images'])}")
print(f"Total legacy image_urls: {len(med_gas['image_urls'])}")

# Verification checks
all_have_url = all(bool(img.get("image_url")) for img in med_gas["images"])
print(f"All images have image_url: {all_have_url}")

legacy_set = set(med_gas["image_urls"])
all_in_legacy = all(img.get("image_url") in legacy_set for img in med_gas["images"])
print(f"All structured image URLs represented in legacy image_urls: {all_in_legacy}")

titles_count = sum(1 for img in med_gas["images"] if img.get("title"))
section_titles_count = sum(1 for img in med_gas["images"] if img.get("section_title"))
alts_count = sum(1 for img in med_gas["images"] if img.get("alt"))
captions_count = sum(1 for img in med_gas["images"] if img.get("caption"))

print(f"Images with title: {titles_count} / {len(med_gas['images'])}")
print(f"Images with section_title: {section_titles_count} / {len(med_gas['images'])}")
print(f"Images with alt: {alts_count} / {len(med_gas['images'])}")
print(f"Images with caption: {captions_count} / {len(med_gas['images'])}")

print("\nSample structured images:")
for i in [0, 1, 10, 20, 50, 78]:
    img = med_gas["images"][i]
    print(f"[{i+1}] URL: {img['image_url'].split('/')[-1]} | Title: {img['title']} | Section: {img['section_title']}")
