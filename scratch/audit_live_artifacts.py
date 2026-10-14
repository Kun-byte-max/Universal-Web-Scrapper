import json
from pathlib import Path

job_dir = Path("output/14f29647-0870-4831-a894-4df004ab4937")
pages_path = job_dir / "website_pages.json"
report_path = job_dir / "extraction_report.json"

pages = json.loads(pages_path.read_text(encoding="utf-8"))
report = json.loads(report_path.read_text(encoding="utf-8"))

p = pages[0]
pc = p["page_content"]
secs = pc["sections"]

print("=== 1. BASIC TYPES & LENGTHS ===")
print("main_text type:", type(p.get("main_text")).__name__, "| len:", len(p.get("main_text", "")))
print("full_text type:", type(pc.get("full_text")).__name__, "| len:", len(pc.get("full_text", "")))
print("paragraphs count:", len(p.get("paragraphs", [])))
print("lists count:", len(p.get("lists", [])))
print("tables count:", len(p.get("tables", [])))
print("images count (legacy):", len(p.get("images", [])))

print("\n=== 2. TOP-LEVEL SECTIONS & ORDER ===")
print("Number of top-level sections:", len(secs))
for i, s in enumerate(secs):
    print(f"  Section {i}: heading={s.get('heading')!r}, level={s.get('level')}, subtitle={s.get('subtitle')!r}, blocks={len(s.get('blocks', []))}, subsecs={len(s.get('subsections', []))}")

print("\n=== 3. PREAMBLE GALLERY AUDIT ===")
s0 = secs[0]
print("Section 0 heading is None?:", s0.get("heading") is None)
print("Section 0 block types:", set(b.get("type") for b in s0.get("blocks", [])))
print("Section 0 image count:", len(s0.get("blocks", [])))
s0_valid_urls = all(b.get("image_url", "").startswith("http") for b in s0.get("blocks", []))
print("All Section 0 image URLs valid http(s)?:", s0_valid_urls)
s0_captions = [b.get("caption") for b in s0.get("blocks", []) if b.get("caption")]
print(f"Section 0 captions present: {len(s0_captions)} of {len(s0.get('blocks', []))}")
print("Sample captions:", s0_captions[:3])

print("\n=== 4. AN INTRODUCTION AUDIT ===")
s1 = secs[1]
print("Section 1 heading:", s1.get("heading"))
print("Section 1 level:", s1.get("level"))
print("Section 1 subtitle:", s1.get("subtitle"))
print("Section 1 blocks count:", len(s1.get("blocks", [])))
print("Section 1 paragraphs:", [b.get("text")[:60] + "..." for b in s1.get("blocks", []) if b.get("type") == "paragraph"])
print("Section 1 subsections count:", len(s1.get("subsections", [])))

print("\n=== 5. FEATURES SECTION AUDIT ===")
features_sec = next((s for s in s1.get("subsections", []) if s.get("heading") == "Features"), None)
print("Features nested under AN INTRODUCTION?:", features_sec is not None)
if features_sec:
    print("Features level:", features_sec.get("level"))
    print("Features blocks:", [b.get("type") for b in features_sec.get("blocks", [])])
    f_list = next((b for b in features_sec.get("blocks", []) if b.get("type") == "list"), None)
    if f_list:
        print("Features list items count:", len(f_list.get("items", [])))
        print("Features sample item 0:", f_list.get("items", [])[0][:80] + "...")

print("\n=== 6. SUBSECTION ORDER AUDIT (FIRST 10) ===")
for i, sub in enumerate(s1.get("subsections", [])[:10]):
    print(f"  Subsec {i}: heading={sub.get('heading')!r}, level={sub.get('level')}, blocks={len(sub.get('blocks', []))}")

print("\n=== 7. MENU & FOOTER BOILERPLATE AUDIT ===")
full_text = pc.get("full_text", "")
main_text = p.get("main_text", "")
all_p_texts = " ".join(p.get("paragraphs", []))

boilerplate_terms = [
    "About Us Company Profile", "menu-main-menu", "mobile-menu", 
    "Copyright 2025", "All Rights Reserved", "We use cookies"
]
for term in boilerplate_terms:
    in_full = term in full_text
    in_main = term in main_text
    in_p = term in all_p_texts
    print(f"Term '{term}': in_full_text={in_full}, in_main_text={in_main}, in_paragraphs={in_p}")

print("\n=== 8. REPORT VS ACTUAL OUTPUT COUNTS ===")
print("Report pages_visited:", report.get("pages_visited"), "vs actual:", len(pages))
print("Report duration_seconds:", report.get("duration_seconds"))
print("Report stop_reason:", report.get("stop_reason"))
print("Report errors:", report.get("errors"))
print("Extraction report job_id:", report.get("job_id"))
