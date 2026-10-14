import pytest
from unittest.mock import MagicMock
from scrapy.http import Request, Response, TextResponse, HtmlResponse
from twisted.python.failure import Failure

from app.scraper.scrapy_engine.spiders.universal_spider import (
    UniversalSitemapSpider,
    is_non_page_asset_url,
    NON_PAGE_EXTENSIONS
)
from app.scraper.scrapy_engine.items import (
    PageItem,
    ProductItem,
    SitemapInventoryItem
)
from app.scraper.scrapy_engine.pipelines import ScrapyExtractionPipeline
from app.scraper.parser import PageParser
from app.scraper.extractors import StrategyGeneralPage


# ==============================================================================
# TASK A: Prevent binary assets from entering HTML parsing
# ==============================================================================

def test_task_a_is_non_page_asset_url():
    """Verify non-page asset extension detection with query strings and fragments."""
    # Direct image links
    assert is_non_page_asset_url("https://example.com/image.jpg") is True
    assert is_non_page_asset_url("https://example.com/photo.PNG") is True
    assert is_non_page_asset_url("https://example.com/asset.webp") is True
    assert is_non_page_asset_url("https://example.com/logo.svg") is True

    # Document and archive links
    assert is_non_page_asset_url("https://example.com/manual.pdf") is True
    assert is_non_page_asset_url("https://example.com/data.zip") is True
    assert is_non_page_asset_url("https://example.com/sheet.xlsx") is True

    # Query strings and fragments do not defeat extension filtering
    assert is_non_page_asset_url("https://example.com/image.jpg?v=2.1#section") is True
    assert is_non_page_asset_url("https://example.com/catalog.pdf?token=abc.xyz") is True

    # Normal HTML pages with dots in query string are NOT blocked
    assert is_non_page_asset_url("https://example.com/product.html?version=1.0") is False
    assert is_non_page_asset_url("https://example.com/search?q=dr.smith&v=2.0") is False
    assert is_non_page_asset_url("https://example.com/medical-gas-pipeline-system/") is False
    assert is_non_page_asset_url("https://example.com/category/equipment") is False


def test_task_a_binary_links_not_scheduled_for_html_parsing():
    """Verify discover_links filtering in parse_page does not schedule non-page assets."""
    spider = UniversalSitemapSpider(target_url="https://example.com/product", mode="auto")
    
    html = """
    <html>
      <body>
        <h1>Hospital OT Equipment</h1>
        <p>Medical operating theatre equipment designed for modern hospital facilities and critical care units.</p>
        <p>Manufactured with high grade stainless steel for long term clinical reliability and durability.</p>
        <a href="/specsheet.pdf">Download PDF Specsheet</a>
        <a href="/large-photo.jpg">View High-Res Photo</a>
        <a href="/archive.zip">CAD Files Archive</a>
        <a href="/related-equipment">Next Equipment Model</a>
        <img src="/thumb.jpg" alt="OT Equipment Thumbnail" />
      </body>
    </html>
    """
    resp = HtmlResponse(url="https://example.com/product", body=html.encode('utf-8'), encoding='utf-8', status=200)
    
    results = list(spider.parse_page(resp))
    
    # Filter out items vs requests
    requests = [r for r in results if isinstance(r, Request)]
    scheduled_urls = [r.url for r in requests]
    
    # The normal HTML link must be scheduled
    assert "https://example.com/related-equipment" in scheduled_urls
    
    # The binary asset links MUST NOT be scheduled as pages
    assert "https://example.com/specsheet.pdf" not in scheduled_urls
    assert "https://example.com/large-photo.jpg" not in scheduled_urls
    assert "https://example.com/archive.zip" not in scheduled_urls


def test_task_a_non_text_response_guard_prevents_crash():
    """Verify non-TextResponse (binary Response) is skipped safely without AttributeError."""
    spider = UniversalSitemapSpider(target_url="https://example.com/image.jpg", mode="auto")
    
    # Standard Scrapy binary Response (not TextResponse)
    binary_resp = Response(
        url="https://example.com/image.jpg",
        body=b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01",
        status=200,
        headers={"Content-Type": b"image/jpeg"}
    )
    
    # Calling parse_page must NOT raise AttributeError: Response content isn't text
    results = list(spider.parse_page(binary_resp))
    assert len(results) == 0
    assert spider.pages_visited_count == 0


def test_task_a_product_images_preserved_in_metadata():
    """Verify HTML parsing still extracts product image metadata into images and image_urls."""
    spider = UniversalSitemapSpider(target_url="https://example.com/pipeline", mode="auto")
    
    html = """
    <html>
      <body>
        <h1>Medical Gas Pipeline System</h1>
        <h2>Bed Head Unit</h2>
        <p>Advanced gas distribution infrastructure designed for hospital life support systems.</p>
        <p>Complete system supporting oxygen, nitrous oxide, and medical vacuum with digital monitors.</p>
        <img src="/images/bed-unit.jpg" title="Bed Head Units" />
      </body>
    </html>
    """
    resp = HtmlResponse(url="https://example.com/pipeline", body=html.encode('utf-8'), encoding='utf-8', status=200)
    
    results = list(spider.parse_page(resp))
    prod_items = [r for r in results if isinstance(r, ProductItem)]
    assert len(prod_items) >= 1
    prod = prod_items[0]
    
    # Image URLs must be preserved in both legacy and structured metadata
    assert "https://example.com/images/bed-unit.jpg" in prod["image_urls"]
    assert len(prod["images"]) >= 1
    assert prod["images"][0]["image_url"] == "https://example.com/images/bed-unit.jpg"
    assert prod["images"][0]["section_title"] == "Bed Head Unit"


# ==============================================================================
# TASK B: Separate asset download failures from eligible page failures
# ==============================================================================

def test_task_b_oversized_pdf_failure_does_not_fail_crawl_completeness(tmp_path):
    """Verify asset error does not mark crawl incomplete when all HTML pages succeed."""
    spider = UniversalSitemapSpider(target_url="https://example.com/page1", mode="auto")
    pipeline = ScrapyExtractionPipeline(output_dir=str(tmp_path))
    
    # 1. Process legitimate HTML page
    html = "<html><body><h1>Product 1</h1><p>Description line one for the equipment.</p><p>Description line two for durability.</p></body></html>"
    resp = HtmlResponse(url="https://example.com/page1", body=html.encode('utf-8'), encoding='utf-8', status=200)
    for item in spider.parse_page(resp):
        if not isinstance(item, Request):
            pipeline.process_item(item, spider=spider)
            
    # 2. Simulate oversized PDF failure (asset error)
    req_pdf = Request("https://example.com/catalogs/heavy.pdf")
    fail_pdf = Failure(Exception("Download cancelled: larger than download max size (10485760)"))
    fail_pdf.request = req_pdf
    spider.handle_error(fail_pdf)
    
    # Asset error recorded, but stop_reason should remain queue_exhausted
    assert len(spider.asset_errors) == 1
    assert len(spider.page_errors) == 0
    assert spider.stop_reason == "queue_exhausted"
    assert spider.crawl_complete is True
    
    # Pipeline output check
    pipeline.close_spider(spider=spider)
    
    import json
    report = json.loads((tmp_path / "extraction_report.json").read_text(encoding="utf-8"))
    assert report["stop_reason"] == "queue_exhausted"
    assert report["crawl_complete"] is True
    assert len(report["errors"]) == 1
    assert "[Asset Error]" in report["errors"][0]


def test_task_b_eligible_html_page_failure_marks_crawl_incomplete(tmp_path):
    """Verify eligible HTML page failure properly sets download_error and crawl_complete=False."""
    spider = UniversalSitemapSpider(target_url="https://example.com/page1", mode="auto")
    pipeline = ScrapyExtractionPipeline(output_dir=str(tmp_path))
    
    # Page 1 succeeds
    html = "<html><body><h1>Product 1</h1><p>Description paragraph one.</p><p>Description paragraph two.</p></body></html>"
    resp = HtmlResponse(url="https://example.com/page1", body=html.encode('utf-8'), encoding='utf-8', status=200)
    for item in spider.parse_page(resp):
        if not isinstance(item, Request):
            pipeline.process_item(item, spider=spider)
            
    # Page 2 fails (HTML page error)
    req_page2 = Request("https://example.com/page2")
    fail_page2 = Failure(Exception("Connection timed out"))
    fail_page2.request = req_page2
    spider.handle_error(fail_page2)
    
    assert len(spider.page_errors) == 1
    assert spider.stop_reason == "download_error"
    assert spider.crawl_complete is False
    
    pipeline.close_spider(spider=spider)
    
    import json
    report = json.loads((tmp_path / "extraction_report.json").read_text(encoding="utf-8"))
    assert report["stop_reason"] == "download_error"
    assert report["crawl_complete"] is False
    assert len(report["errors"]) == 1
    assert "[Page Error]" in report["errors"][0]


def test_task_b_mixed_asset_and_html_failures_preserves_page_failure(tmp_path):
    """Verify HTML failure takes precedence over later asset failure."""
    spider = UniversalSitemapSpider(target_url="https://example.com/page1", mode="auto")
    pipeline = ScrapyExtractionPipeline(output_dir=str(tmp_path))
    
    # 1. HTML page failure occurs
    req_page = Request("https://example.com/page-broken")
    fail_page = Failure(Exception("500 Server Error"))
    fail_page.request = req_page
    spider.handle_error(fail_page)
    
    # 2. Asset failure occurs
    req_asset = Request("https://example.com/large-catalog.pdf")
    fail_asset = Failure(Exception("Download cancelled: larger than download max size"))
    fail_asset.request = req_asset
    spider.handle_error(fail_asset)
    
    assert len(spider.page_errors) == 1
    assert len(spider.asset_errors) == 1
    assert len(spider.crawler_errors) == 2
    assert spider.stop_reason == "download_error"
    assert spider.crawl_complete is False
    
    pipeline.close_spider(spider=spider)
    
    import json
    report = json.loads((tmp_path / "extraction_report.json").read_text(encoding="utf-8"))
    assert report["stop_reason"] == "download_error"
    assert report["crawl_complete"] is False
    assert len(report["errors"]) == 2


# ==============================================================================
# TASK C: Correct sitemap errback behavior
# ==============================================================================

def test_task_c_sitemap_errback_returns_inventory_item_without_generator_issue():
    """Verify handle_sitemap_error returns a valid list of SitemapInventoryItem."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="auto")
    req = Request("https://example.com/discovered-sitemap.xml")
    fail = Failure(Exception("DNS resolution failed"))
    fail.request = req
    
    items = list(spider.handle_sitemap_error(fail))
    assert len(items) == 1
    assert isinstance(items[0], SitemapInventoryItem)
    assert items[0]["url"] == "https://example.com/discovered-sitemap.xml"
    assert items[0]["status"] == "failed"
    assert "DNS resolution failed" in items[0]["reason"]
    assert "https://example.com/discovered-sitemap.xml" in spider.sitemap_inventory


def test_task_c_probe_candidate_failure_does_not_pollute_inventory(tmp_path):
    """Verify probe candidate 404 does not create fake sitemap items in inventory."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="auto")
    pipeline = ScrapyExtractionPipeline(output_dir=str(tmp_path))
    
    # Simulate a probe candidate response (status 404)
    probe_resp = Response(
        url="https://example.com/wp-sitemap.xml",
        status=404,
        request=Request("https://example.com/wp-sitemap.xml", meta={"is_candidate_probe": True})
    )
    
    # parse_sitemap_or_robots should return nothing for unverified candidate probe 404
    items = list(spider.parse_sitemap_or_robots(probe_resp))
    assert len(items) == 0
    
    pipeline.close_spider(spider=spider)
    
    import json
    inventory = json.loads((tmp_path / "sitemap_inventory.json").read_text(encoding="utf-8"))
    assert inventory == []


# ==============================================================================
# TASK D: Correct corporate profile classification
# ==============================================================================

def test_task_d_company_profile_excluded_from_products():
    """Verify company profile page is excluded from product records even with multiple paragraphs."""
    html_profile = """
    <html>
      <head><title>Company Profile – Med freshe Private Limited</title></head>
      <body>
        <h1>Company Profile</h1>
        <p>Corporate Brief : Unison Narula Group (UNG) is into Healthcare and Waste Management since 1953.</p>
        <p>Under healthcare division of UNG there are many activities from furnishing hospitals on turnkey basis, complete hospital consultation and planning.</p>
        <p>UNG companies are ISO 9001, ISO 13485, ISO 18001 & ISO 19001 certified and products are CE marked.</p>
      </body>
    </html>
    """
    parser = PageParser(html_profile, "https://medfreshe.com/company-profile/")
    records, strategy = parser.parse_records()
    
    # Must NOT be extracted as a product record
    assert len(records) == 0


def test_task_d_legitimate_equipment_with_incidental_company_name_retained():
    """Verify legitimate equipment with incidental 'company' in title or body is preserved."""
    html_equipment = """
    <html>
      <head><title>Company Medical Gas Pipeline System – Med freshe</title></head>
      <body>
        <h1>Company Medical Gas Pipeline System</h1>
        <h2>Bed Head Unit</h2>
        <p>Manufactured by the company to provide continuous supply of medical oxygen and nitrous oxide.</p>
        <p>Heavy duty aluminum alloy trunking with gas terminal units and low voltage electrical sockets.</p>
        <img src="/images/mgps-unit.jpg" alt="Medical Gas Unit" />
      </body>
    </html>
    """
    parser = PageParser(html_equipment, "https://medfreshe.com/company-medical-gas/")
    records, strategy = parser.parse_records()
    
    # Legitimate equipment MUST be retained
    assert len(records) == 1
    assert "Company Medical Gas Pipeline System" in records[0]["title"]
    assert len(records[0]["images"]) >= 1


def test_task_d_existing_exclusions_preserved():
    """Verify existing exclusions for Homepage, Contact, About Us, Quality Control remain intact."""
    test_cases = [
        ("https://medfreshe.com/", "Med freshe Private Limited – Med Freshe Pvt Ltd", "Home"),
        ("https://medfreshe.com/contact/", "Contact – Med freshe Private Limited", "Contact Us"),
        ("https://medfreshe.com/about-us/", "About Us – Med freshe Private Limited", "About Us"),
        ("https://medfreshe.com/quality-control/", "Quality Control – Med freshe Private Limited", "Quality Assurance"),
    ]
    
    for url, doc_title, h1 in test_cases:
        html = f"""
        <html>
          <head><title>{doc_title}</title></head>
          <body>
            <h1>{h1}</h1>
            <p>Generic corporate informational text describing operations and contact information.</p>
            <p>Additional paragraph detailing quality procedures and corporate office location.</p>
          </body>
        </html>
        """
        parser = PageParser(html, url)
        records, _ = parser.parse_records()
        assert len(records) == 0, f"Expected exclusion for {url}, but got {len(records)} records"
