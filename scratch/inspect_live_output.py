import json
from pathlib import Path

job_dir = Path("output/f3dac070-496f-4770-951c-53c13aa9f4ab")
pages_file = job_dir / "website_pages.json"

pages = json.loads(pages_file.read_text(encoding="utf-8"))
print(f"Total pages in website_pages.json: {len(pages)}")

page = pages[0]
print(f"\nPage URL: {page.get('page_url')}")
print(f"Title: {page.get('title')}")
print(f"HTTP Status: {page.get('http_status')}")

# Legacy fields
print(f"\n=== LEGACY COMPATIBILITY FIELDS ===")
print(f"Headings keys: {list(page.get('headings', {}).keys())}")
for h_tag, h_list in page.get('headings', {}).items():
    if h_list:
        print(f"  {h_tag}: {len(h_list)} items -> first 3: {h_list[:3]}")

print(f"Paragraphs count: {len(page.get('paragraphs', []))}")
if page.get('paragraphs'):
    print(f"  Paragraph 0 (first 100 chars): {page.get('paragraphs')[0][:100]}...")
    print(f"  Paragraph 1 (first 100 chars): {page.get('paragraphs')[1][:100]}...")

print(f"Main text length: {len(page.get('main_text', ''))}")
print(f"  Main text snippet (first 150 chars): {page.get('main_text', '')[:150]}...")
print(f"Lists count: {len(page.get('lists', []))}")
print(f"Tables count: {len(page.get('tables', []))}")
print(f"Breadcrumbs: {page.get('breadcrumbs', [])}")
print(f"Images count: {len(page.get('images', []))}")

# Phase 19 fields
print(f"\n=== PHASE 19 STRUCTURED PAGE CONTENT ===")
content_ext = page.get("content_extraction", {})
print(f"Content extraction method: {content_ext.get('method')}")
print(f"Content extraction complete: {content_ext.get('complete')}")
print(f"Content extraction warnings: {content_ext.get('warnings')}")

pc = page.get("page_content", {})
print(f"Page content title: {pc.get('title')}")
sections = pc.get("sections", [])
print(f"Top-level sections count: {len(sections)}")

def inspect_sections(sec_list, indent=0):
    for i, s in enumerate(sec_list):
        sp = "  " * indent
        h = s.get("heading")
        lvl = s.get("level")
        sub = s.get("subtitle")
        blocks = s.get("blocks", [])
        subsecs = s.get("subsections", [])
        block_types = [b.get("type") for b in blocks]
        print(f"{sp}[{lvl or 'root'}] Heading: '{h}' | Subtitle: '{sub}' | Blocks: {len(blocks)} {block_types} | Subsections: {len(subsecs)}")
        for b in blocks:
            b_type = b.get("type")
            if b_type == "paragraph":
                print(f"{sp}    -> P: {b.get('text')[:70]}...")
            elif b_type == "list":
                print(f"{sp}    -> List: {len(b.get('items', []))} items -> {b.get('items', [])[:2]}")
            elif b_type == "image":
                print(f"{sp}    -> Image: URL={b.get('image_url')[:50]}... | title={b.get('title')} | caption={b.get('caption')}")
            elif b_type == "table":
                print(f"{sp}    -> Table: headers={b.get('headers')} | rows={len(b.get('rows', []))}")
            else:
                print(f"{sp}    -> {b_type}: {str(b)[:70]}")
        if subsecs:
            inspect_sections(subsecs, indent + 1)

inspect_sections(sections)

full_text = pc.get("full_text", "")
print(f"\nFull text length: {len(full_text)}")
print(f"Full text first 400 chars:\n{full_text[:400]}")
