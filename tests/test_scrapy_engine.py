import os
import json
import pytest
from pathlib import Path
from scrapy.http import HtmlResponse, Request, TextResponse
from scrapy.exceptions import IgnoreRequest

from app.scraper.scrapy_engine.spiders.universal_spider import UniversalSitemapSpider
from app.scraper.scrapy_engine.middlewares import SSRFDownloaderMiddleware
from app.scraper.scrapy_engine.pipelines import ScrapyExtractionPipeline
from app.scraper.scrapy_engine.items import PageItem, ProductItem, SitemapInventoryItem

SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <sitemap>
      <loc>https://example.com/wp-sitemap-posts-product-1.xml</loc>
   </sitemap>
</sitemapindex>"""

SITEMAP_URLSET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>https://example.com/products/headphones</loc>
      <lastmod>2026-10-10</lastmod>
   </url>
</urlset>"""

HTML_WITH_DOWNLOADS = """<!DOCTYPE html>
<html>
<head><title>Product Spec Sheet</title></head>
<body>
    <h1>Manual & Catalogue</h1>
    <a href="/docs/manual.pdf">Download Manual PDF</a>
    <a href="/docs/spec.docx">Download Spec Word Document</a>
</body>
</html>"""

def test_ssrf_middleware_blocking():
    middleware = SSRFDownloaderMiddleware(allow_private_ips=False)
    spider = UniversalSitemapSpider(target_url="https://example.com")
    
    # Valid public URL request passes
    valid_req = Request("https://example.com/item")
    assert middleware.process_request(valid_req, spider) is None

    # Localhost request blocked
    blocked_req = Request("http://127.0.0.1/admin")
    with pytest.raises(IgnoreRequest, match="SSRF Protection Error"):
        middleware.process_request(blocked_req, spider)

def test_sitemap_index_and_urlset_parsing():
    spider = UniversalSitemapSpider(target_url="https://example.com", max_pages=10)
    
    # Parse sitemap index
    resp_index = TextResponse(
        url="https://example.com/wp-sitemap.xml",
        body=SITEMAP_INDEX_XML.encode('utf-8'),
        encoding='utf-8',
        status=200
    )
    items_index = list(spider.parse_sitemap_xml(resp_index))
    assert len(items_index) == 3
    assert isinstance(items_index[0], SitemapInventoryItem)

    assert items_index[0]['url'] == "https://example.com/wp-sitemap.xml"
    assert items_index[1]['url'] == "https://example.com/wp-sitemap-posts-product-1.xml"

    # Parse urlset
    resp_urlset = TextResponse(
        url="https://example.com/wp-sitemap-posts-product-1.xml",
        body=SITEMAP_URLSET_XML.encode('utf-8'),
        encoding='utf-8',
        status=200
    )
    items_urlset = list(spider.parse_sitemap_xml(resp_urlset))
    assert len(items_urlset) == 3
    assert isinstance(items_urlset[0], SitemapInventoryItem)
    assert items_urlset[1]['url'] == "https://example.com/products/headphones"


def test_page_parsing_and_document_discovery():
    spider = UniversalSitemapSpider(target_url="https://example.com", max_pages=10)
    resp = HtmlResponse(
        url="https://example.com/spec",
        body=HTML_WITH_DOWNLOADS.encode('utf-8'),
        encoding='utf-8',
        status=200
    )
    
    items = list(spider.parse_page(resp))
    assert len(items) >= 1
    page_item = items[0]
    assert isinstance(page_item, PageItem)
    assert page_item['title'] == "Product Spec Sheet"
    assert len(page_item['downloadable_files']) == 2
    assert page_item['downloadable_files'][0]['url'] == "https://example.com/docs/manual.pdf"

def test_pipeline_output_four_files(tmp_path):
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    spider = UniversalSitemapSpider(target_url="https://example.com")

    # Add items
    page = PageItem(page_url="https://example.com/p1", title="Page 1", http_status=200)
    prod = ProductItem(title="Gadget", price=19.99, product_url="https://example.com/p1", source_url="https://example.com")
    inv = SitemapInventoryItem(url="https://example.com/p1", sitemap_url="https://example.com/sitemap.xml", status="crawled")

    pipeline.process_item(page, spider)
    pipeline.process_item(prod, spider)
    pipeline.process_item(inv, spider)

    pipeline.close_spider(spider)

    assert (tmp_path / "website_pages.json").exists()
    assert (tmp_path / "products.json").exists()
    assert (tmp_path / "sitemap_inventory.json").exists()
    assert (tmp_path / "extraction_report.json").exists()

    with open(tmp_path / "products.json", "r", encoding="utf-8") as f:
        prods = json.load(f)
        assert len(prods) == 1
        assert prods[0]["title"] == "Gadget"
        assert prods[0]["price"] == 19.99

    with open(tmp_path / "extraction_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)
        assert report["target_url"] == "https://example.com/"
        assert report["total_urls_in_inventory"] == 1

def test_static_page_no_false_product():
    html_contact = """<!DOCTYPE html><html><head><title>Contact – Med freshe Private Limited</title></head><body><h1>Contact Us</h1><p>Address : UNG Tower, 3rd Floor, Building No. 2 & 3, Central Market, Punjabi Bagh West, New Delhi-110026, INDIA.</p><p>Phone : (+91-11) 4545 9999 (Hunting Lines), (+91-11) 2522 8890 | Fax : (+91-11) 2522 8702.</p><img src="/img/office.jpg" alt="Office"></body></html>"""
    spider = UniversalSitemapSpider(target_url="https://example.com/contact")
    resp = HtmlResponse(url="https://example.com/contact", body=html_contact.encode('utf-8'), encoding='utf-8', status=200)
    
    items = list(spider.parse_page(resp))
    # Should contain PageItem, but NO ProductItem
    page_items = [i for i in items if isinstance(i, PageItem)]
    prod_items = [i for i in items if isinstance(i, ProductItem)]
    
    assert len(page_items) == 1
    assert len(prod_items) == 0
    assert "Contact" in page_items[0]['title']

def test_url_normalization_homepage():
    from app.scraper.safety import normalize_url
    assert normalize_url("https://example.com") == "https://example.com/"
    assert normalize_url("https://example.com/") == "https://example.com/"
    assert normalize_url("https://EXAMPLE.COM/Shop/") == "https://example.com/Shop/"

def test_sitemap_failure_recording():
    from twisted.python.failure import Failure
    from scrapy.http import Request
    spider = UniversalSitemapSpider(target_url="https://example.com")
    req = Request("https://example.com/sitemap.xml")
    fail = Failure(Exception("404 Not Found"))
    fail.request = req
    
    items = list(spider.handle_sitemap_error(fail))
    assert len(items) == 1
    assert isinstance(items[0], SitemapInventoryItem)
    assert items[0]['url'] == "https://example.com/sitemap.xml"
    assert items[0]['status'] == "failed"
    assert "404 Not Found" in items[0]['reason']

def test_sitemap_invalid_xml_inventory():
    spider = UniversalSitemapSpider(target_url="https://example.com")
    resp = TextResponse(
        url="https://example.com/corrupt_sitemap.xml",
        body="<sitemapindex>CORRUPT_XML_WITHOUT_END_TAG".encode('utf-8'),
        encoding='utf-8',
        status=200
    )
    items = list(spider.parse_sitemap_xml(resp))
    assert len(items) == 1
    assert isinstance(items[0], SitemapInventoryItem)
    assert items[0]['url'] == "https://example.com/corrupt_sitemap.xml"
    assert items[0]['status'] == "failed"
    assert "XML Parse Error" in items[0]['reason']

def test_configured_limits_report_accuracy(tmp_path):
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    spider = UniversalSitemapSpider(target_url="https://example.com", max_pages=10, max_records=20)
    pipeline.close_spider(spider)

    with open(tmp_path / "extraction_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)
        assert report["configured_limits"]["max_pages"] == 10
        assert report["configured_limits"]["max_records"] == 20

def test_configured_limits_report_accuracy_crawler_context(tmp_path):
    class MockCrawler:
        def __init__(self, spider_inst):
            self.spider = spider_inst

    spider = UniversalSitemapSpider(target_url="https://example.com", max_pages=15, max_records=25)
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    pipeline.crawler = MockCrawler(spider)
    
    # Pass spider=None to test crawler context resolution
    pipeline.close_spider(spider=None)

    with open(tmp_path / "extraction_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)
        assert report["configured_limits"]["max_pages"] == 15
        assert report["configured_limits"]["max_records"] == 25

def test_spider_to_product_item_image_metadata_retention(tmp_path):
    html_gallery = """
    <!DOCTYPE html>
    <html>
    <body>
        <main>
            <h1>Medical Gas Pipeline System</h1>
            <p>Comprehensive medical gas equipment installation for modern hospitals.</p>
            <h2>Intensive Care Unit</h2>
            <figure>
                <img src="/img/icu1.jpg" alt="Vertical Type ICU" title="Vertical Type ICU Title">
                <figcaption>Vertical Type ICU Caption</figcaption>
            </figure>
        </main>
    </body>
    </html>
    """
    spider = UniversalSitemapSpider(target_url="https://example.com/gas-pipeline")
    resp = HtmlResponse(
        url="https://example.com/gas-pipeline",
        body=html_gallery.encode("utf-8"),
        encoding="utf-8",
        status=200
    )

    items = list(spider.parse_page(resp))
    prod_items = [i for i in items if isinstance(i, ProductItem)]
    assert len(prod_items) == 1
    prod = prod_items[0]

    assert "images" in prod
    assert len(prod["images"]) == 1
    img = prod["images"][0]
    assert img["image_url"] == "https://example.com/img/icu1.jpg"
    assert img["title"] == "Vertical Type ICU Caption"
    assert img["section_title"] == "Intensive Care Unit"

    # Verify pipeline preserves and serializes images into products.json
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    pipeline.process_item(prod, spider)
    pipeline.close_spider(spider)

    with open(tmp_path / "products.json", "r", encoding="utf-8") as f:
        saved_products = json.load(f)

    assert len(saved_products) == 1
    saved_img = saved_products[0]["images"][0]
    assert saved_img["image_url"] == "https://example.com/img/icu1.jpg"
    assert saved_img["title"] == "Vertical Type ICU Caption"
    assert saved_img["section_title"] == "Intensive Care Unit"


