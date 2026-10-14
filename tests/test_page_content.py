import pytest
from bs4 import BeautifulSoup

from app.scraper.page_content import extract_page_content, PageContentExtractor
from app.scraper.parser import PageParser
from app.scraper.scrapy_engine.spiders.universal_spider import UniversalSitemapSpider
from app.scraper.scrapy_engine.items import PageItem
from scrapy.http import HtmlResponse

TARGET_MEDFRESHE_FIXTURE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Modular OT/ICU/ER – Med freshe Private Limited</title>
</head>
<body>
    <header class="site-header">
        <nav class="navbar">
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>

    <div class="cookie-banner">
        <p>We use cookies to enhance your experience. Accept?</p>
    </div>

    <nav aria-label="breadcrumb">
        <ol class="breadcrumb">
            <li><a href="https://medfreshe.com/">Home</a></li>
            <li><a href="https://medfreshe.com/products/">Products</a></li>
            <li><span>Modular OT / ICU / ER</span></li>
        </ol>
    </nav>

    <main id="content" class="site-main">
        <h1 class="page-title">Modular OT/ICU/ER – Med freshe Private Limited</h1>

        <section class="intro-section">
            <h3>AN INTRODUCTION</h3>
            <h4>Modular OT / ICU / Emergency Room / OT Integration (MOT)</h4>
            <p>Historically, the term "operating theatre" referred to a non-sterile, tiered theatre or amphitheater in which students and other spectators could watch surgeons perform surgery. Contemporary operating rooms are devoid of a theatre setting, making the term "operating theatre" a misnomer.</p>
            <p>The most complex and challenging area of hospital construction is the operating department. Modular Operation Theatre (MOT) offers the advantage of speedy construction combined with design, future expansion and development in surgical technique whilst simultaneously providing a structure of the highest quality and standards.</p>
            <p>MOT, where most integrated functions are always required, such as hygiene must be preserved with safety facilities, equipment and device must be maintained any times. Furthermore, the working environment for medical staff such as doctors and nurses must be considered from the view point of human engineering.</p>
        </section>

        <section class="features-section">
            <h4>Features</h4>
            <ul>
                <li>A continuous flow of highly filtered bacteria-free air is reticulated under positive pressure into the operating field.</li>
                <li>Easy to clean steam cleaned, electro metric ideal for high humidity areas.</li>
                <li>Vapour permeability protects against growth of bacteria, mould and yeasts.</li>
                <li>High standard of asepsis and seamless economic structure.</li>
            </ul>
        </section>

        <section class="systems-section">
            <h4>Modular Operation Theatre (MOT)</h4>
            <p>Operation Theatre is that specialized facility of the hospital where life saving or life improving procedures are carried out under strict aseptic conditions.</p>
            <figure>
                <img src="/wp-content/uploads/2023/11/Modular-Operation-Theatre-MOT.jpg" alt="Modular OT Unit" title="MedFreshe MOT" />
                <figcaption>Complete pre-fabricated Modular Operation Theatre</figcaption>
            </figure>

            <h4>Modular ICU</h4>
            <p>Modular intensive care units are custom-built and designed, ensuring spaces can be quickly and easily modified.</p>
            <div class="image-card">
                <img src="/wp-content/uploads/2023/11/Modular-ICU.jpg" alt="Modular ICU System" />
                <span class="caption">Turnkey Modular ICU installation</span>
            </div>

            <h4>Main Equipment Specifications</h4>
            <table class="specs-table">
                <thead>
                    <tr>
                        <th>Equipment</th>
                        <th>Technical Specification</th>
                        <th>Standard Compliance</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Plenum Unit</td>
                        <td>Laminar Air Flow with terminal HEPA filter 0.3 micron</td>
                        <td>DIN:1946 Class 1A</td>
                    </tr>
                    <tr>
                        <td>Hermetically Sealed Door</td>
                        <td>Compact laminate board with microprocessor sliding automation</td>
                        <td>ISO 14644</td>
                    </tr>
                </tbody>
            </table>
        </section>
    </main>

    <footer class="site-footer">
        <p>© Copyright 2025. All Rights Reserved</p>
        <div class="footer-links">
            <a href="/privacy">Privacy Policy</a>
            <a href="/terms">Terms</a>
        </div>
    </footer>
</body>
</html>
"""

def test_target_fixture_title_and_breadcrumbs():
    """Verify primary title and breadcrumbs extraction."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")

    assert res["page_title"] == "Modular OT/ICU/ER – Med freshe Private Limited"
    assert res["breadcrumbs"] == ["Home", "Products", "Modular OT / ICU / ER"]


def test_target_fixture_heading_and_subtitle():
    """Verify AN INTRODUCTION heading and associated subtitle extraction."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    sections = res["page_content"]["sections"]

    intro_sec = next((s for s in sections if s.get("heading") == "AN INTRODUCTION"), None)
    assert intro_sec is not None
    assert intro_sec["level"] == 3
    assert intro_sec["subtitle"] == "Modular OT / ICU / Emergency Room / OT Integration (MOT)"


def test_target_fixture_consecutive_paragraphs_in_order():
    """Verify multiple consecutive introduction paragraphs are preserved in order."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    sections = res["page_content"]["sections"]

    intro_sec = next((s for s in sections if s.get("heading") == "AN INTRODUCTION"), None)
    assert intro_sec is not None
    
    para_blocks = [b for b in intro_sec["blocks"] if b["type"] == "paragraph"]
    assert len(para_blocks) == 3
    assert "operating theatre" in para_blocks[0]["text"]
    assert "The most complex and challenging area" in para_blocks[1]["text"]
    assert "MOT, where most integrated functions are always required" in para_blocks[2]["text"]


def test_target_fixture_nested_features_section_and_list():
    """Verify nested Features section and all list items are retained."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    sections = res["page_content"]["sections"]

    # Either as subsection of intro or sibling section
    all_sections = []
    def flatten(sec_list):
        for s in sec_list:
            all_sections.append(s)
            flatten(s.get("subsections", []))
    flatten(sections)

    features_sec = next((s for s in all_sections if s.get("heading") == "Features"), None)
    assert features_sec is not None
    assert features_sec["level"] == 4

    list_blocks = [b for b in features_sec["blocks"] if b["type"] == "list"]
    assert len(list_blocks) == 1
    assert list_blocks[0]["ordered"] is False
    assert len(list_blocks[0]["items"]) == 4
    assert "bacteria-free air" in list_blocks[0]["items"][0]
    assert "High standard of asepsis" in list_blocks[0]["items"][3]


def test_target_fixture_table_structure_preserved():
    """Verify structured table with headers and all rows preserved."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    
    tables = res["tables"]
    assert len(tables) >= 1
    table = tables[0]
    assert table["headers"] == ["Equipment", "Technical Specification", "Standard Compliance"]
    assert len(table["rows"]) == 2
    assert table["rows"][0][0] == "Plenum Unit"
    assert "DIN:1946" in table["rows"][0][2]
    assert table["rows"][1][0] == "Hermetically Sealed Door"
    assert "ISO 14644" in table["rows"][1][2]


def test_target_fixture_images_with_captions_and_order():
    """Verify images in document order with valid URLs, alt, title, and captions."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    
    sections = res["page_content"]["sections"]
    all_images = []
    def collect_imgs(sec_list):
        for s in sec_list:
            for b in s.get("blocks", []):
                if b["type"] == "image":
                    all_images.append(b)
            collect_imgs(s.get("subsections", []))
    collect_imgs(sections)

    assert len(all_images) == 2
    
    # Image 1: figcaption
    assert all_images[0]["image_url"] == "https://medfreshe.com/wp-content/uploads/2023/11/Modular-Operation-Theatre-MOT.jpg"
    assert all_images[0]["alt"] == "Modular OT Unit"
    assert all_images[0]["title"] == "MedFreshe MOT"
    assert all_images[0]["caption"] == "Complete pre-fabricated Modular Operation Theatre"

    # Image 2: adjacent caption container
    assert all_images[1]["image_url"] == "https://medfreshe.com/wp-content/uploads/2023/11/Modular-ICU.jpg"
    assert all_images[1]["alt"] == "Modular ICU System"
    assert all_images[1]["caption"] == "Turnkey Modular ICU installation"


def test_full_text_reconstruction():
    """Verify full-text reconstruction preserves reading order without duplication."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    full_text = res["page_content"]["full_text"]

    assert "AN INTRODUCTION" in full_text
    assert "Modular OT / ICU / Emergency Room / OT Integration (MOT)" in full_text
    assert "operating theatre" in full_text
    assert "Features" in full_text
    assert "bacteria-free air" in full_text
    assert "Plenum Unit" in full_text
    assert "DIN:1946" in full_text

    # Verify footer copyright is NOT in full_text
    assert "© Copyright 2025. All Rights Reserved" not in full_text
    # Verify cookie banner is NOT in full_text
    assert "We use cookies" not in full_text


def test_safety_limit_warning_and_incomplete_status():
    """Verify a configured safety limit produces warnings and complete: false."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    # Set tight limit of 3 blocks
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/", max_blocks=3)

    assert res["content_extraction"]["complete"] is False
    assert len(res["content_extraction"]["warnings"]) >= 1
    assert "safety limit reached" in res["content_extraction"]["warnings"][0].lower()


def test_navigation_and_footer_chrome_excluded():
    """Verify navigation menus, cookie banners, and footer chrome are excluded from article blocks."""
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    paragraphs = res["paragraphs"]

    assert not any("We use cookies" in p for p in paragraphs)
    assert not any("© Copyright" in p for p in paragraphs)
    assert not any("Privacy Policy" in p for p in paragraphs)


def test_empty_and_malformed_html_safety():
    """Verify empty, malformed, and heading-less pages do not crash."""
    empty_soup = BeautifulSoup("", "html.parser")
    res_empty = extract_page_content(empty_soup, "https://example.com/empty")
    assert res_empty["page_title"] == ""
    assert res_empty["page_content"]["sections"] == []
    assert res_empty["content_extraction"]["complete"] is False
    assert res_empty["content_extraction"]["status"] == "empty"
    assert len(res_empty["content_extraction"]["warnings"]) == 1
    assert "empty" in res_empty["content_extraction"]["warnings"][0].lower()

    malformed_html = "<html><body><h4>Broken</h4><p>Unclosed paragraph<div><span>Deep text</div></body>"
    malformed_soup = BeautifulSoup(malformed_html, "html.parser")
    res_malformed = extract_page_content(malformed_soup, "https://example.com/broken")
    assert res_malformed["content_extraction"]["complete"] is True
    assert res_malformed["content_extraction"]["status"] == "complete"
    assert res_malformed["content_extraction"]["warnings"] == []
    assert len(res_malformed["paragraphs"]) >= 1


def test_spider_yields_pageitem_with_phase19_fields():
    """Verify UniversalSitemapSpider yields PageItem populated with all Phase 19 fields."""
    spider = UniversalSitemapSpider(target_url="https://medfreshe.com/modular-ot-icu-er/")
    resp = HtmlResponse(
        url="https://medfreshe.com/modular-ot-icu-er/",
        body=TARGET_MEDFRESHE_FIXTURE.encode("utf-8"),
        encoding="utf-8",
        status=200
    )

    items = list(spider.parse_page(resp))
    page_items = [i for i in items if isinstance(i, PageItem)]
    assert len(page_items) == 1
    p_item = page_items[0]

    # Legacy fields
    assert p_item["page_url"] == "https://medfreshe.com/modular-ot-icu-er/"
    assert p_item["title"] == "Modular OT/ICU/ER – Med freshe Private Limited"
    assert "h3" in p_item["headings"]
    assert p_item["headings"]["h3"] == ["AN INTRODUCTION"]
    assert len(p_item["paragraphs"]) >= 3
    assert len(p_item["breadcrumbs"]) == 3
    assert len(p_item["tables"]) == 1
    assert len(p_item["lists"]) == 1

    # New Phase 19 fields
    assert "page_content" in p_item
    assert p_item["page_content"]["title"] == "Modular OT/ICU/ER – Med freshe Private Limited"
    assert len(p_item["page_content"]["sections"]) >= 1
    assert "Features" in p_item["page_content"]["full_text"]

    assert "content_extraction" in p_item
    assert p_item["content_extraction"]["method"] == "html_dom"
    assert p_item["content_extraction"]["complete"] is True
    assert p_item["content_extraction"]["warnings"] == []


def test_product_classification_rules_preserve_generic_exclusions():
    """Requirement 15: Verify product-classification rules continue rejecting generic Contact, Quality Control, and Homepage pages."""
    test_cases = [
        ("https://medfreshe.com/", "Med freshe Private Limited – Med Freshe Pvt Ltd", "Home"),
        ("https://medfreshe.com/contact/", "Contact Us – Med freshe Private Limited", "Contact Us"),
        ("https://medfreshe.com/quality-control/", "Quality Control – Med freshe Private Limited", "Quality Assurance"),
    ]
    for url, doc_title, h1 in test_cases:
        html = f"""
        <html>
          <head><title>{doc_title}</title></head>
          <body>
            <h1>{h1}</h1>
            <p>Corporate information text describing company standards, team contact details, and certifications.</p>
            <p>Our quality management systems ensure strict adherence to all ISO and industry guidelines.</p>
          </body>
        </html>
        """
        parser = PageParser(html, url)
        records, _ = parser.parse_records()
        assert len(records) == 0, f"Expected exclusion for {url}, but got {len(records)}"


def test_legitimate_b2b_product_extraction_preserves_image_metadata():
    """Requirement 16: Verify legitimate B2B product pages extract product items with complete image metadata."""
    html = """
    <html>
      <head><title>Operation Theatre Table Hydraulic Model – Med freshe</title></head>
      <body>
        <main>
          <h1>Operation Theatre Table Hydraulic Model</h1>
          <div class="product-info">
            <span class="sku">SKU: OT-TAB-200</span>
            <span class="price">$4,500.00</span>
          </div>
          <p>Heavy duty stainless steel hydraulic surgical table designed for multi-discipline operating theaters.</p>
          <figure>
            <img src="/images/ot-table-hydraulic.jpg" alt="OT Table Front View" title="Hydraulic OT Table" />
            <figcaption>Hydraulic surgical table in elevated position</figcaption>
          </figure>
        </main>
      </body>
    </html>
    """
    parser = PageParser(html, "https://medfreshe.com/products/ot-table-hydraulic/")
    records, _ = parser.parse_records()
    assert len(records) == 1
    rec = records[0]
    assert rec["title"] == "Operation Theatre Table Hydraulic Model"
    assert rec["sku"] == "SKU: OT-TAB-200"
    assert rec["price"] == 4500.0
    assert len(rec["images"]) >= 1
    assert rec["images"][0]["caption"] == "Hydraulic surgical table in elevated position"


def test_cms_prose_in_h4_converted_to_paragraphs():
    """Verify long prose erroneously wrapped in <h4> by visual CMS builders is parsed as paragraphs."""
    html = """
    <html><body>
        <main>
            <h3>AN INTRODUCTION</h3>
            <h4>Modular OT / ICU / Emergency Room / OT Integration (MOT)</h4>
            <h4>Historically, the term "operating theatre" referred to a non-sterile, tiered theatre or amphitheater in which students and other spectators could watch surgeons perform surgery. Contemporary operating rooms are devoid of a theatre setting, making the term "operating theatre" a misnomer.</h4>
            <h4>The most complex and challenging area of hospital construction is the operating department. Modular Operation Theatre offers the advantage of speedy construction combined with design, future expansion and development in surgical technique.</h4>
            <h4>Features</h4>
            <h4>A continuous flow of highly filtered bacteria-free air is reticulated under positive pressure into the operating field and air contaminants generated during surgery are removed from the site.</h4>
        </main>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot-icu-er/")
    
    sections = res["page_content"]["sections"]
    intro_sec = next((s for s in sections if s.get("heading") == "AN INTRODUCTION"), None)
    assert intro_sec is not None
    assert intro_sec["subtitle"] == "Modular OT / ICU / Emergency Room / OT Integration (MOT)"
    
    para_blocks = [b for b in intro_sec["blocks"] if b["type"] == "paragraph"]
    # The two long prose <h4> tags must be converted into paragraph blocks
    assert len(para_blocks) >= 2
    assert "operating theatre" in para_blocks[0]["text"]
    assert "The most complex and challenging area" in para_blocks[1]["text"]


def test_target_fixture_contains_intro_paragraphs_and_features_section_not_merely_title_and_first_desc():
    """
    Explicit regression test:
    Asserts that the target-like fixture contains the introduction paragraphs and Features section,
    not merely the page title and first description snippet.
    """
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    parser = PageParser(TARGET_MEDFRESHE_FIXTURE, "https://medfreshe.com/modular-ot-icu-er/")
    res = parser.parse_page_content()

    content = res["page_content"]
    assert content["title"] == "Modular OT/ICU/ER – Med freshe Private Limited"

    # 1. Introduction paragraphs are completely preserved
    intro_sec = next((s for s in content["sections"] if s.get("heading") == "AN INTRODUCTION"), None)
    assert intro_sec is not None, "AN INTRODUCTION section must be present"
    assert intro_sec.get("subtitle") == "Modular OT / ICU / Emergency Room / OT Integration (MOT)"
    
    intro_paras = [b["text"] for b in intro_sec.get("blocks", []) if b.get("type") == "paragraph"]
    assert len(intro_paras) >= 3, f"Expected at least 3 intro paragraphs, found {len(intro_paras)}"
    assert "Historically, the term \"operating theatre\"" in intro_paras[0]
    assert "The most complex and challenging area of hospital construction" in intro_paras[1]
    assert "MOT, where most integrated functions are always required" in intro_paras[2]

    # 2. Features section is completely preserved
    features_sec = next((s for s in intro_sec.get("subsections", []) if s.get("heading") == "Features"), None)
    if not features_sec:
        # Check top-level or other subsections
        features_sec = next((s for s in content["sections"] if s.get("heading") == "Features"), None)
    assert features_sec is not None, "Features section must be present"
    
    feature_lists = [b for b in features_sec.get("blocks", []) if b.get("type") == "list"]
    assert len(feature_lists) >= 1, "Features list block must be present"
    assert len(feature_lists[0]["items"]) >= 4, "Features list must retain all 4 list items"

    # 3. Full text is comprehensive
    full_text = content["full_text"]
    for p in intro_paras:
        assert p in full_text
    for item in feature_lists[0]["items"]:
        assert item in full_text


def test_preamble_content_and_menu_exclusion_regression():
    """
    Phase 19.1 Regression:
    1. Pre-heading content (e.g. image gallery before AN INTRODUCTION) is retained in an unheaded preamble section,
       and the first real heading starts at top level in sections rather than nesting inside the preamble.
    2. Mobile and header navigation menus (classes mobile-menu-wrapper, top-menu-container, menu) are excluded from content blocks.
    """
    html = """
    <html>
      <head><title>Modular OT – Med Freshe</title></head>
      <body>
        <div class="mobile-menu-wrapper">
          <ul class="menu">
            <li><a href="/home">Home Menu</a></li>
            <li><a href="/products">Products Menu</a></li>
          </ul>
        </div>
        <div class="top-menu-container">
          <ul class="nav-menu">
            <li><a href="/about">About Menu</a></li>
          </ul>
        </div>
        <div class="post-formatting">
          <div class="gallery">
            <figure><img src="/img/mot-gallery.jpg" alt="Gallery Photo 1" /></figure>
          </div>
          <h3>AN INTRODUCTION</h3>
          <h4>Modular OT / ICU / ER (MOT)</h4>
          <p>Introduction prose describing hospital modular operating theatres.</p>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://medfreshe.com/modular-ot/")

    sections = res["page_content"]["sections"]
    assert len(sections) == 2, f"Expected 2 top-level sections (preamble + intro), found {len(sections)}"

    # Section 0: Preamble gallery image
    sec0 = sections[0]
    assert sec0["heading"] is None
    assert len(sec0["blocks"]) == 1
    assert sec0["blocks"][0]["type"] == "image"
    assert "/img/mot-gallery.jpg" in sec0["blocks"][0]["image_url"]

    # Section 1: Top-level AN INTRODUCTION section
    sec1 = sections[1]
    assert sec1["heading"] == "AN INTRODUCTION"
    assert sec1["subtitle"] == "Modular OT / ICU / ER (MOT)"
    assert len(sec1["blocks"]) == 1
    assert "Introduction prose" in sec1["blocks"][0]["text"]

    # Menus excluded from full_text
    full_text = res["page_content"]["full_text"]
    assert "Home Menu" not in full_text
    assert "Products Menu" not in full_text
    assert "About Menu" not in full_text


def test_title_only_page_reports_suspiciously_short():
    """Step 2: Verify title-only page is marked incomplete with a suspicious-short warning."""
    html = "<html><head><title>Under Construction</title></head><body><h1>Under Construction</h1></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/construction")

    assert res["page_title"] == "Under Construction"
    assert res["content_extraction"]["complete"] is False
    assert res["content_extraction"]["status"] == "suspiciously_short"
    assert len(res["content_extraction"]["warnings"]) == 1
    assert "suspiciously short" in res["content_extraction"]["warnings"][0].lower()
    assert "Under Construction" in res["content_extraction"]["warnings"][0]


def test_small_legitimate_prose_page_is_complete_without_warnings():
    """Step 2: Verify a page with few words but legitimate content is marked complete without false warnings."""
    html = "<html><body><h1>Notice</h1><p>Our office is closed today for annual inventory.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/notice")

    assert res["page_title"] == "Notice"
    assert res["content_extraction"]["complete"] is True
    assert res["content_extraction"]["status"] == "complete"
    assert res["content_extraction"]["warnings"] == []
    assert len(res["paragraphs"]) == 1
    assert "Our office is closed" in res["paragraphs"][0]


def test_structured_content_with_little_prose_is_complete_without_warnings():
    """Step 2: Verify pages with little prose but structured content (e.g. tables or lists) are marked complete."""
    html = """
    <html>
      <head><title>Office Timetable</title></head>
      <body>
        <table>
          <tr><th>Day</th><th>Hours</th></tr>
          <tr><td>Monday</td><td>09:00 - 17:00</td></tr>
          <tr><td>Tuesday</td><td>09:00 - 17:00</td></tr>
        </table>
        <ul>
          <li>Emergency support available 24/7</li>
        </ul>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/hours")

    assert res["page_title"] == "Office Timetable"
    assert res["content_extraction"]["complete"] is True
    assert res["content_extraction"]["status"] == "complete"
    assert res["content_extraction"]["warnings"] == []
    assert len(res["tables"]) == 1
    assert len(res["lists"]) == 1


def test_safety_limit_and_completeness_fields_survive_serialization():
    """Step 2: Verify warnings, status, and completeness fields survive JSON serialization."""
    import json
    from itemadapter import ItemAdapter
    
    # 1. Test safety limit exceeded serialization
    soup_limit = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    res_limit = extract_page_content(soup_limit, "https://medfreshe.com/modular-ot/", max_blocks=2)
    assert res_limit["content_extraction"]["complete"] is False
    assert res_limit["content_extraction"]["status"] == "limit_exceeded"

    spider = UniversalSitemapSpider(target_url="https://medfreshe.com/modular-ot/")
    resp = HtmlResponse(
        url="https://medfreshe.com/modular-ot/",
        body=TARGET_MEDFRESHE_FIXTURE.encode("utf-8"),
        encoding="utf-8",
        status=200
    )
    items = list(spider.parse_page(resp))
    p_item = [i for i in items if isinstance(i, PageItem)][0]

    # Convert to dict and JSON serialize
    serialized = json.dumps(ItemAdapter(p_item).asdict())
    deserialized = json.loads(serialized)

    assert "content_extraction" in deserialized
    ext = deserialized["content_extraction"]
    assert ext["method"] == "html_dom"
    assert ext["complete"] is True
    assert ext["status"] == "complete"
    assert ext["warnings"] == []


def test_nav_with_menu_item_children_excluded():
    """Step 3: Verify a real <nav> with .menu-item children is completely excluded as navigation chrome."""
    html = """
    <html>
      <body>
        <nav class="main-navigation">
          <ul class="menu">
            <li class="menu-item"><a href="/">Home</a></li>
            <li class="menu-item"><a href="/about">About</a></li>
          </ul>
        </nav>
        <main>
          <h1>Actual Article Title</h1>
          <p>Real article content that must be extracted.</p>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/article")

    full_text = res["page_content"]["full_text"]
    assert "Real article content" in full_text
    assert "Home" not in full_text
    assert "About" not in full_text
    assert not any("Home" in p for p in res["paragraphs"])


def test_legitimate_food_menu_content_retained():
    """Step 3: Verify legitimate restaurant food menu with .menu and .menu-item classes is retained."""
    html = """
    <html>
      <head><title>Bistro Menu – Bella Italia</title></head>
      <body>
        <header class="site-header">
          <nav><a href="/">Home</a></nav>
        </header>
        <main>
          <h1>Dinner Menu</h1>
          <div class="restaurant-menu menu">
            <h3>Appetizers</h3>
            <div class="menu-item">
              <h4>Bruschetta al Pomodoro</h4>
              <p>Toasted ciabatta with heirloom tomatoes, garlic, extra virgin olive oil, and fresh basil.</p>
            </div>
            <div class="menu-item">
              <h4>Calamari Fritti</h4>
              <p>Crispy fried squid rings served with house spicy marinara and lemon wedges.</p>
            </div>
          </div>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/dinner-menu")

    assert res["content_extraction"]["complete"] is True
    assert res["content_extraction"]["status"] == "complete"
    assert res["content_extraction"]["warnings"] == []

    full_text = res["page_content"]["full_text"]
    assert "Bruschetta al Pomodoro" in full_text
    assert "Toasted ciabatta with heirloom tomatoes" in full_text
    assert "Calamari Fritti" in full_text
    assert "Crispy fried squid rings" in full_text

    # Header navigation excluded
    assert "Home" not in full_text


def test_product_specification_sidebar_retained():
    """Step 3: Verify product specifications inside a sidebar container are retained as legitimate content."""
    html = """
    <html>
      <head><title>Industrial Centrifuge Model 5000</title></head>
      <body>
        <main>
          <h1>Industrial Centrifuge Model 5000</h1>
          <p>High speed precision laboratory centrifuge with programmable microprocessor control.</p>
          <div class="product-sidebar sidebar">
            <h3>Technical Specifications</h3>
            <p>Maximum Rotor Speed: 15,000 RPM with digital feedback control.</p>
            <table>
              <tr><th>Parameter</th><th>Value</th></tr>
              <tr><td>Capacity</td><td>4 x 250 mL</td></tr>
              <tr><td>Max RCF</td><td>21,380 x g</td></tr>
            </table>
          </div>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/centrifuge-5000")

    assert res["content_extraction"]["complete"] is True
    assert res["content_extraction"]["status"] == "complete"

    full_text = res["page_content"]["full_text"]
    assert "Industrial Centrifuge Model 5000" in full_text
    assert "Technical Specifications" in full_text
    assert "Maximum Rotor Speed" in full_text
    assert "Capacity" in full_text
    assert "21,380 x g" in full_text
    assert len(res["tables"]) == 1


def test_site_header_and_navigation_wrappers_exclude_boilerplate():
    """Step 3: Verify site header, cookie notices, and navigation boilerplate wrappers are excluded."""
    html = """
    <html>
      <body>
        <div class="site-header">
          <div class="header-navigation mobile-menu-wrapper">
            <a href="/login">User Login</a>
            <a href="/cart">Shopping Cart (0)</a>
          </div>
        </div>
        <div class="cookie-banner consent-notice">
          <p>We value your privacy. Manage tracking preferences.</p>
        </div>
        <main>
          <h1>Company Overview</h1>
          <p>We design and manufacture medical technology solutions worldwide.</p>
        </main>
        <div class="site-footer">
          <p>© 2026 Company Inc. All rights reserved.</p>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/about")

    full_text = res["page_content"]["full_text"]
    assert "We design and manufacture medical technology solutions" in full_text
    assert "User Login" not in full_text
    assert "Shopping Cart" not in full_text
    assert "Manage tracking preferences" not in full_text
    assert "All rights reserved" not in full_text


def test_cms_h4_single_sentence_prose_becomes_paragraph():
    """Verify single-sentence descriptive prose inside <h4> is converted to paragraph blocks."""
    html = """
    <html>
      <body>
        <main>
          <h1>Modular Operating Systems</h1>
          <h3>AN INTRODUCTION</h3>
          <h4>The modular operation theatre (MOT) integrated approach to the construction and co-ordination of operating Theatre.</h4>
          <p>Operation Theatre is that specialized facility of the hospital where procedures are carried out.</p>
          <h4>Surgical Scrub Station</h4>
          <h4>The unit is made of high quality stainless steel (304 / 316).</h4>
          <p>Features knee-touch or sensor activation.</p>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/modular-ot/")
    sections = res["page_content"]["sections"]

    # Verify intro section has the h4 prose as a paragraph
    intro = next((s for s in sections if s.get("heading") == "AN INTRODUCTION"), None)
    assert intro is not None
    intro_paras = [b["text"] for b in intro["blocks"] if b["type"] == "paragraph"]
    assert any("The modular operation theatre (MOT) integrated approach" in p for p in intro_paras)

    # Verify Surgical Scrub Station has the stainless steel sentence as a paragraph
    scrub = next((s for s in sections if s.get("heading") == "Surgical Scrub Station"), None)
    assert scrub is not None
    scrub_paras = [b["text"] for b in scrub["blocks"] if b["type"] == "paragraph"]
    assert any("The unit is made of high quality stainless steel" in p for p in scrub_paras)


def test_cms_sibling_sections_unnested_from_intro():
    """Verify standalone sibling sections are not nested under AN INTRODUCTION."""
    html = """
    <html>
      <body>
        <main>
          <h1>Modular OT Solutions</h1>
          <h3>AN INTRODUCTION</h3>
          <p>Introductory background and clinical context.</p>
          <h4>Features</h4>
          <ul>
            <li>Continuous laminar airflow</li>
            <li>HEPA filtration ISO 14644</li>
          </ul>
          <h4>Main Systems / Equipment</h4>
          <ul>
            <li>Plenum Unit</li>
            <li>Control Panel</li>
          </ul>
          <h4>Modular ICU</h4>
          <p>Custom-built intensive care environment.</p>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/ot-solutions/")
    sections = res["page_content"]["sections"]

    # All major sections should be top-level siblings in sections
    section_headings = [s.get("heading") for s in sections]
    assert "AN INTRODUCTION" in section_headings
    assert "Features" in section_headings
    assert "Main Systems / Equipment" in section_headings
    assert "Modular ICU" in section_headings

    # Intro section should NOT contain Features or Modular ICU in its subsections
    intro = next(s for s in sections if s.get("heading") == "AN INTRODUCTION")
    assert len(intro.get("subsections", [])) == 0


def test_completeness_of_all_blocks_headings_paragraphs_lists_images_links_downloads():
    """Verify complete extraction of headings, paragraphs, lists, images, tables, links, and downloads."""
    html = """
    <html>
      <body>
        <main>
          <h1>Complete Surgical Suite</h1>
          <h3>Overview</h3>
          <p>State-of-the-art operating rooms engineered for maximum clinical efficiency.</p>
          <figure>
            <img src="/img/suite.jpg" alt="Surgical Suite Diagram" title="Architecture 2026" />
            <figcaption>Engineering schematic of sterile airflow</figcaption>
          </figure>
          <h4>Key Features</h4>
          <ol>
            <li>Positive pressure ventilation</li>
            <li>Anti-microbial seamless cladding</li>
          </ol>
          <h4>Technical Specifications</h4>
          <table>
            <thead>
              <tr><th>Component</th><th>Standard</th></tr>
            </thead>
            <tbody>
              <tr><td>Air Handling</td><td>DIN 1946</td></tr>
            </tbody>
          </table>
          <div class="downloads-panel">
            <a href="/downloads/brochure.pdf">Download Technical Brochure (PDF)</a>
            <a href="https://partner.com/specifications">External Reference Spec</a>
          </div>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = extract_page_content(soup, "https://example.com/suite/")

    # 1. Paragraphs
    all_paras = res["paragraphs"]
    assert len(all_paras) >= 1
    assert "State-of-the-art operating rooms" in all_paras[0]

    # 2. Lists
    all_lists = res["lists"]
    assert len(all_lists) >= 1
    assert "Positive pressure ventilation" in all_lists[0][0]
    assert "Anti-microbial seamless cladding" in all_lists[0][1]

    # 3. Tables
    all_tables = res["tables"]
    assert len(all_tables) == 1
    assert all_tables[0]["headers"] == ["Component", "Standard"]
    assert all_tables[0]["rows"] == [["Air Handling", "DIN 1946"]]

    # 4. Images
    sections = res["page_content"]["sections"]
    img_blocks = []
    link_blocks = []
    def collect(sec_list):
        for s in sec_list:
            for b in s.get("blocks", []):
                if b["type"] == "image":
                    img_blocks.append(b)
                elif b["type"] == "link":
                    link_blocks.append(b)
            collect(s.get("subsections", []))
    collect(sections)

    assert len(img_blocks) == 1
    assert img_blocks[0]["image_url"] == "https://example.com/img/suite.jpg"
    assert img_blocks[0]["alt"] == "Surgical Suite Diagram"
    assert img_blocks[0]["caption"] == "Engineering schematic of sterile airflow"

    # 5. Downloadable asset link & external link
    assert len(link_blocks) >= 2
    pdf_link = next((l for l in link_blocks if "brochure.pdf" in l["url"]), None)
    assert pdf_link is not None
    assert pdf_link["is_asset"] is True
    assert "Download Technical Brochure" in pdf_link["text"]

    ext_link = next((l for l in link_blocks if "partner.com" in l["url"]), None)
    assert ext_link is not None
    assert ext_link["is_asset"] is False



