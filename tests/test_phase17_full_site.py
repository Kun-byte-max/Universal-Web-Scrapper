import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scrapy.http import HtmlResponse, Request, TextResponse

from app.models import ScrapeRequest, CrawlMode
from app.config import settings
from app.scraper.scrapy_engine.spiders.universal_spider import UniversalSitemapSpider
from app.scraper.scrapy_engine.pipelines import ScrapyExtractionPipeline
from app.scraper.scrapy_engine.items import PageItem, ProductItem, SitemapInventoryItem

# 1. URL-only requests resolve to auto mode
def test_scrape_request_auto_mode_resolution():
    req = ScrapeRequest(url="https://example.com/")
    assert req.mode == CrawlMode.AUTO
    assert req.max_pages is None
    assert req.max_records is None

# 2. Explicit page/record limits preserve bounded behavior
def test_bounded_mode_preserves_limits():
    req = ScrapeRequest(url="https://example.com/", max_pages=10, max_records=20)
    assert req.mode == CrawlMode.BOUNDED
    assert req.max_pages == 10
    assert req.max_records == 20

# 3. Explicit mode validation and conflict resolution
def test_explicit_mode_validation_conflict():
    # Explicit auto with limits must raise validation error
    with pytest.raises(ValueError, match="Cannot specify max_pages or max_records when mode is 'auto'"):
        ScrapeRequest(url="https://example.com/", mode="auto", max_pages=10)

    # Explicit bounded without limits applies backward-compatible defaults
    req_bounded = ScrapeRequest(url="https://example.com/", mode="bounded")
    assert req_bounded.mode == CrawlMode.BOUNDED
    assert req_bounded.max_pages == 5
    assert req_bounded.max_records == 50

# 4. Auto mode traverses at least 12 linked pages, exceeding former default of 5
def test_auto_mode_crawls_12_linked_pages():
    spider = UniversalSitemapSpider(target_url="https://example.com/page0", mode="auto")
    assert spider.mode == "auto"
    assert spider.max_pages == settings.AUTO_MAX_PAGES

    # Simulate crawling 12 consecutive pages
    visited_pages = []
    for i in range(12):
        next_link = f"https://example.com/page{i+1}" if i < 11 else ""
        html = f"""<html><body><h1>Page {i}</h1><a href="{next_link}">Next</a></body></html>"""
        resp = HtmlResponse(url=f"https://example.com/page{i}", body=html.encode('utf-8'), encoding='utf-8', status=200)
        items = list(spider.parse_page(resp))
        visited_pages.append(items)

    assert spider.pages_visited_count == 12
    assert spider.stop_reason == "queue_exhausted"
    assert spider.crawl_complete is True

# 5. Auto mode follows a finite pagination chain
def test_auto_mode_follows_pagination_chain():
    spider = UniversalSitemapSpider(target_url="https://example.com/catalog?page=1", mode="auto")
    
    # Page 1 links to Page 2
    html_p1 = """<html><body><h1>Catalog</h1><a href="/catalog?page=2">Next Page</a></body></html>"""
    resp1 = HtmlResponse(url="https://example.com/catalog?page=1", body=html_p1.encode('utf-8'), encoding='utf-8', status=200)
    items1 = list(spider.parse_page(resp1))
    requests1 = [i for i in items1 if isinstance(i, Request)]
    assert len(requests1) == 1
    assert requests1[0].url == "https://example.com/catalog?page=2"

    # Page 2 links to Page 3
    html_p2 = """<html><body><h1>Catalog</h1><a href="/catalog?page=3">Next Page</a></body></html>"""
    resp2 = HtmlResponse(url="https://example.com/catalog?page=2", body=html_p2.encode('utf-8'), encoding='utf-8', status=200)
    items2 = list(spider.parse_page(resp2))
    requests2 = [i for i in items2 if isinstance(i, Request)]
    assert len(requests2) == 1
    assert requests2[0].url == "https://example.com/catalog?page=3"

    # Page 3 has no further next link
    html_p3 = """<html><body><h1>Catalog</h1><p>End of results</p></body></html>"""
    resp3 = HtmlResponse(url="https://example.com/catalog?page=3", body=html_p3.encode('utf-8'), encoding='utf-8', status=200)
    items3 = list(spider.parse_page(resp3))
    requests3 = [i for i in items3 if isinstance(i, Request)]
    assert len(requests3) == 0

    assert spider.pages_visited_count == 3
    assert spider.stop_reason == "queue_exhausted"
    assert spider.crawl_complete is True

# 6. Nested sitemaps dispatch all eligible URLs within test fixture
def test_nested_sitemaps_dispatches_all_urls():
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="auto")
    
    index_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
       <sitemap><loc>https://example.com/sub-sitemap1.xml</loc></sitemap>
       <sitemap><loc>https://example.com/sub-sitemap2.xml</loc></sitemap>
    </sitemapindex>"""

    resp_index = TextResponse(url="https://example.com/sitemap_index.xml", body=index_xml.encode('utf-8'), encoding='utf-8', status=200)
    items_index = list(spider.parse_sitemap_xml(resp_index))
    child_requests = [i for i in items_index if isinstance(i, Request)]
    assert len(child_requests) == 2
    assert child_requests[0].url == "https://example.com/sub-sitemap1.xml"
    assert child_requests[1].url == "https://example.com/sub-sitemap2.xml"

    # Sub-sitemap with 10 URLs
    sub_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">""" + "".join([f"<url><loc>https://example.com/item{i}</loc></url>" for i in range(10)]) + "</urlset>"

    resp_sub = TextResponse(url="https://example.com/sub-sitemap1.xml", body=sub_xml.encode('utf-8'), encoding='utf-8', status=200)
    items_sub = list(spider.parse_sitemap_xml(resp_sub))
    page_requests = [i for i in items_sub if isinstance(i, Request)]
    assert len(page_requests) == 10

# 7. Duplicate URLs are not fetched twice
def test_duplicate_urls_not_fetched_twice():
    spider = UniversalSitemapSpider(target_url="https://example.com/p1", mode="auto")
    html = "<html><body><h1>Page 1</h1></body></html>"
    resp = HtmlResponse(url="https://example.com/p1", body=html.encode('utf-8'), encoding='utf-8', status=200)

    # First visit
    items1 = list(spider.parse_page(resp))
    assert len(items1) >= 1
    assert spider.pages_visited_count == 1

    # Second visit with same URL
    items2 = list(spider.parse_page(resp))
    assert len(items2) == 0
    assert spider.pages_visited_count == 1

# 8. External-origin links remain excluded
def test_external_origin_links_excluded():
    spider = UniversalSitemapSpider(target_url="https://example.com/start", mode="auto")
    html = """<html><body>
        <a href="https://example.com/internal">Internal</a>
        <a href="https://otherdomain.com/external">External</a>
        <a href="https://sub.example.com/subdomain">Subdomain</a>
    </body></html>"""
    resp = HtmlResponse(url="https://example.com/start", body=html.encode('utf-8'), encoding='utf-8', status=200)
    items = list(spider.parse_page(resp))
    reqs = [i for i in items if isinstance(i, Request)]
    assert len(reqs) == 1
    assert reqs[0].url == "https://example.com/internal"

# 9. Auto mode extracts 75 valid records on a fixture page, exceeding former default of 50
def test_auto_mode_extracts_75_records():
    spider = UniversalSitemapSpider(target_url="https://example.com/shop", mode="auto")
    
    # 75 product cards on a single listing page
    cards = "".join([f'<div class="product-card"><h3>Item {i}</h3><span class="price">${i+1}.00</span><a href="/p/{i}">View</a></div>' for i in range(75)])
    html = f"<html><body><h1>Shop</h1>{cards}</body></html>"
    resp = HtmlResponse(url="https://example.com/shop", body=html.encode('utf-8'), encoding='utf-8', status=200)

    items = list(spider.parse_page(resp))
    prod_items = [i for i in items if isinstance(i, ProductItem)]
    assert len(prod_items) == 75
    assert spider.records_extracted_count == 75

# 10. Emergency page ceiling stops scheduling and reports incomplete crawling
def test_emergency_page_ceiling_stops_scheduling(tmp_path):
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="auto")
    # Set a small emergency page ceiling to simulate limit breach
    spider.emergency_max_pages = 3
    spider.max_pages = 3

    for i in range(5):
        html = f"""<html><body><h1>Page {i}</h1><a href="/next{i}">Next</a></body></html>"""
        resp = HtmlResponse(url=f"https://example.com/p{i}", body=html.encode('utf-8'), encoding='utf-8', status=200)
        list(spider.parse_page(resp))

    assert spider.pages_visited_count == 3
    assert spider.stop_reason == "emergency_page_ceiling_reached"
    assert spider.crawl_complete is False

    # Check extraction_report output
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    pipeline.close_spider(spider)

    with open(tmp_path / "extraction_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)

    assert report["crawl_mode"] == "auto"
    assert report["stop_reason"] == "emergency_page_ceiling_reached"
    assert report["crawl_complete"] is False

# 11. Emergency record ceiling stops extraction and reports incomplete crawling
def test_emergency_record_ceiling_stops_extraction(tmp_path):
    spider = UniversalSitemapSpider(target_url="https://example.com/catalog", mode="auto")
    spider.emergency_max_records = 5
    spider.max_records = 5

    cards = "".join([f'<div class="product-card"><h3>Product {i}</h3><span class="price">${10+i}.00</span><a href="/p/{i}">View</a></div>' for i in range(10)])
    html = f"<html><body><h1>Catalog</h1>{cards}</body></html>"
    resp = HtmlResponse(url="https://example.com/catalog", body=html.encode('utf-8'), encoding='utf-8', status=200)

    items = list(spider.parse_page(resp))
    prods = [i for i in items if isinstance(i, ProductItem)]
    assert len(prods) == 5
    assert spider.records_extracted_count == 5
    assert spider.stop_reason == "emergency_record_ceiling_reached"
    assert spider.crawl_complete is False

    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    for p in prods:
        pipeline.process_item(p, spider)
    pipeline.close_spider(spider)

    with open(tmp_path / "extraction_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)

    assert report["stop_reason"] == "emergency_record_ceiling_reached"
    assert report["crawl_complete"] is False
    assert report["records_extracted"] == 5

# 12. Timeout handling terminates worker and reports partial status honestly
def test_timeout_handling_terminates_worker():
    from app.scraper.scrapy_engine.runner import ScrapyJobRunner
    from app.config import OUTPUT_DIR

    req = ScrapeRequest(url="https://example.com/infinite")
    
    # Mock Process to simulate a timed-out worker process
    mock_proc = MagicMock()
    mock_proc.is_alive.side_effect = [True, True, False] # alive on first join, alive on terminate, dead on kill

    with patch("multiprocessing.Process", return_value=mock_proc), \
         patch("app.config.settings.AUTO_CRAWL_TIMEOUT_SECONDS", 0.01):
        extracted, stats = ScrapyJobRunner.run_job(req, "test_timeout_job")

    report_file = OUTPUT_DIR / "test_timeout_job" / "extraction_report.json"
    assert report_file.exists()
    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    assert report["crawl_mode"] == "auto"
    assert report["stop_reason"] == "timeout"
    assert report["crawl_complete"] is False
    assert "timeout" in report["errors"][0].lower()

# 13. DOWNLOAD_MAXSIZE is configured in Scrapy settings
def test_download_maxsize_configured_in_scrapy_settings():
    from app.scraper.scrapy_engine.runner import _run_scrapy_process
    
    with patch("app.scraper.scrapy_engine.runner.CrawlerProcess") as MockCrawlerProcess:
        mock_instance = MagicMock()
        MockCrawlerProcess.return_value = mock_instance
        _run_scrapy_process("https://example.com", "auto", None, None, 0.5, "out_test")

        assert MockCrawlerProcess.called
        call_kwargs = MockCrawlerProcess.call_args[1]
        scrapy_settings = call_kwargs["settings"]
        assert "DOWNLOAD_MAXSIZE" in scrapy_settings
        assert scrapy_settings["DOWNLOAD_MAXSIZE"] == settings.MAX_RESPONSE_BYTES
        assert scrapy_settings["DEPTH_LIMIT"] == settings.AUTO_MAX_DEPTH

# 14. Existing structured image objects and legacy image_url/image_urls remain intact
def test_image_metadata_remains_intact(tmp_path):
    html = """
    <html><body>
        <h1>Equipment System</h1>
        <p>Medical equipment for modern hospital installations.</p>
        <h2>ICU Department</h2>
        <div class="panel-grid-cell">
            <div class="widget_sow-editor"><p><strong>Vertical ICU Unit</strong></p></div>
            <div class="widget_sow-image"><img src="/img/icu.jpg" alt="" /></div>
        </div>
    </body></html>
    """
    spider = UniversalSitemapSpider(target_url="https://example.com/system", mode="auto")
    resp = HtmlResponse(url="https://example.com/system", body=html.encode('utf-8'), encoding='utf-8', status=200)

    items = list(spider.parse_page(resp))
    prods = [i for i in items if isinstance(i, ProductItem)]
    assert len(prods) == 1
    prod = prods[0]

    assert prod["image_url"] == "https://example.com/img/icu.jpg"
    assert prod["image_urls"] == ["https://example.com/img/icu.jpg"]
    assert len(prod["images"]) == 1
    assert prod["images"][0]["title"] == "Vertical ICU Unit"
    assert prod["images"][0]["section_title"] == "ICU Department"

    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    pipeline.process_item(prod, spider)
    pipeline.close_spider(spider)

    with open(tmp_path / "products.json", "r", encoding="utf-8") as f:
        saved = json.load(f)

    assert saved[0]["image_url"] == "https://example.com/img/icu.jpg"
    assert saved[0]["image_urls"] == ["https://example.com/img/icu.jpg"]
    assert saved[0]["images"][0]["title"] == "Vertical ICU Unit"
    assert saved[0]["images"][0]["section_title"] == "ICU Department"

# 15. Existing report fields are preserved in extraction_report.json
def test_existing_report_fields_preserved(tmp_path):
    spider = UniversalSitemapSpider(target_url="https://example.com/p", mode="auto")
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    pipeline.close_spider(spider)

    with open(tmp_path / "extraction_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)

    # All legacy fields must exist
    legacy_keys = [
        "target_url", "job_id", "sitemaps_discovered", "total_sitemaps",
        "total_urls_in_inventory", "pages_visited", "products_extracted",
        "files_discovered", "configured_limits", "duration_seconds", "errors"
    ]
    for key in legacy_keys:
        assert key in report

    # New fields must exist
    new_keys = ["crawl_mode", "stop_reason", "crawl_complete", "records_extracted", "records_written", "emergency_ceilings"]
    for key in new_keys:
        assert key in report

# 16. Bounded mode explicitly respects user limits
def test_bounded_mode_respects_user_limits(tmp_path):
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded", max_pages=2, max_records=3)
    assert spider.mode == "bounded"
    assert spider.max_pages == 2
    assert spider.max_records == 3

    for i in range(4):
        html = f"""<html><body><h1>Page {i}</h1><a href="/p{i+1}">Next</a></body></html>"""
        resp = HtmlResponse(url=f"https://example.com/p{i}", body=html.encode('utf-8'), encoding='utf-8', status=200)
        list(spider.parse_page(resp))

    assert spider.pages_visited_count == 2
    assert spider.stop_reason == "bounded_page_limit_reached"
    assert spider.crawl_complete is False

# 17. PHASE 17.3: Direct spider constructor mode resolution
def test_direct_spider_constructor_mode_resolution():
    # A. Direct caller specifying max_pages without mode resolves to bounded
    s1 = UniversalSitemapSpider(target_url="https://example.com", max_pages=10)
    assert s1.mode == "bounded"
    assert s1.max_pages == 10
    assert s1.max_records == 50

    # B. Direct caller specifying max_records without mode resolves to bounded
    s2 = UniversalSitemapSpider(target_url="https://example.com", max_records=20)
    assert s2.mode == "bounded"
    assert s2.max_pages == 5
    assert s2.max_records == 20

    # C. Direct caller with no limits and no mode resolves to auto with emergency ceilings
    s3 = UniversalSitemapSpider(target_url="https://example.com")
    assert s3.mode == "auto"
    assert s3.max_pages == settings.AUTO_MAX_PAGES
    assert s3.max_records == settings.AUTO_MAX_RECORDS

    # D. Explicit mode="auto" uses emergency ceilings
    s4 = UniversalSitemapSpider(target_url="https://example.com", mode="auto")
    assert s4.mode == "auto"
    assert s4.max_pages == settings.AUTO_MAX_PAGES
    assert s4.max_records == settings.AUTO_MAX_RECORDS

    # E. Explicit mode="bounded" with omitted limits preserves bounded defaults
    s5 = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")
    assert s5.mode == "bounded"
    assert s5.max_pages == 5
    assert s5.max_records == 50

# 18. PHASE 17.3: Record ceiling stops further extraction and child page scheduling
def test_record_ceiling_stops_further_extraction_and_scheduling():
    spider = UniversalSitemapSpider(target_url="https://example.com/p1", mode="bounded", max_pages=10, max_records=2)
    assert spider.max_records == 2

    # Page 1 contains 3 product items and a link to Page 2
    cards = "".join([f'<div class="product-card"><h3>Product {i}</h3><span class="price">${i+1}.00</span><a href="/p/{i}">View</a></div>' for i in range(3)])
    html_p1 = f"""<html><body><h1>Catalog</h1><a href="/p2">Page 2</a>{cards}</body></html>"""
    resp_p1 = HtmlResponse(url="https://example.com/p1", body=html_p1.encode('utf-8'), encoding='utf-8', status=200)

    items_p1 = list(spider.parse_page(resp_p1))
    prods_p1 = [i for i in items_p1 if isinstance(i, ProductItem)]
    reqs_p1 = [i for i in items_p1 if isinstance(i, Request)]

    # Exactly 2 products yielded (third product ignored)
    assert len(prods_p1) == 2
    assert spider.records_extracted_count == 2
    assert spider.stop_reason == "bounded_record_limit_reached"
    assert spider.crawl_complete is False

    # Link to Page 2 must NOT be scheduled because record ceiling was reached
    assert len(reqs_p1) == 0

    # In-flight response arriving after ceiling reached: emits PageItem but does not extract records or queue links
    html_p2 = """<html><body><h1>Catalog Page 2</h1><a href="/p3">Page 3</a><div class="product-card"><h3>Late Product</h3><span class="price">$99.00</span></div></body></html>"""
    resp_p2 = HtmlResponse(url="https://example.com/p2", body=html_p2.encode('utf-8'), encoding='utf-8', status=200)
    items_p2 = list(spider.parse_page(resp_p2))

    prods_p2 = [i for i in items_p2 if isinstance(i, ProductItem)]
    reqs_p2 = [i for i in items_p2 if isinstance(i, Request)]
    pages_p2 = [i for i in items_p2 if isinstance(i, PageItem)]

    assert len(pages_p2) == 1  # Metadata preserved
    assert len(prods_p2) == 0  # No extraction
    assert len(reqs_p2) == 0   # No scheduling
    assert spider.records_extracted_count == 2

# 19. PHASE 17.3: Truthful stop_reason and completion reporting on errors and depth cutoff
def test_truthful_stop_reason_and_completion_reporting(tmp_path):
    from twisted.python.failure import Failure

    # A. Request error updates stop_reason and marks crawl_complete=False
    spider1 = UniversalSitemapSpider(target_url="https://example.com/test", mode="auto")
    dummy_req = Request("https://example.com/failed_page")
    fail = Failure(Exception("Connection reset by peer"))
    fail.request = dummy_req
    spider1.handle_error(fail)

    assert spider1.stop_reason == "download_error"
    assert spider1.crawl_complete is False
    assert len(spider1.crawler_errors) == 1

    pipeline1 = ScrapyExtractionPipeline(output_dir=tmp_path / "t1")
    pipeline1.close_spider(spider1)

    with open(tmp_path / "t1" / "extraction_report.json", "r", encoding="utf-8") as f:
        rep1 = json.load(f)
    assert rep1["stop_reason"] == "download_error"
    assert rep1["crawl_complete"] is False

    # B. Depth limit cutoff detected from crawler stats
    class MockCrawlerWithStats:
        class MockStats:
            def get_value(self, key, default=0):
                if key == "depth/request_ignored_count":
                    return 5
                return default
        def __init__(self, spider_inst):
            self.spider = spider_inst
            self.stats = self.MockStats()

    spider2 = UniversalSitemapSpider(target_url="https://example.com/test", mode="auto")
    pipeline2 = ScrapyExtractionPipeline(output_dir=tmp_path / "t2")
    pipeline2.crawler = MockCrawlerWithStats(spider2)
    pipeline2.close_spider(spider2)

    with open(tmp_path / "t2" / "extraction_report.json", "r", encoding="utf-8") as f:
        rep2 = json.load(f)
    assert rep2["stop_reason"] == "depth_limit_reached"
    assert rep2["crawl_complete"] is False

# 20. PHASE 17.3: Runner timeout and crash reflect FAILED status in API
@pytest.mark.asyncio
async def test_runner_timeout_and_crash_api_job_status():
    from app.api.routes import run_scrape_job, jobs_db
    from app.models import JobStatus, JobResponse
    from app.scraper.scrapy_engine.runner import ScrapyJobRunner

    req = ScrapeRequest(url="https://example.com/timeout")
    job_id = "test_api_fail_job"
    jobs_db[job_id] = JobResponse(
        job_id=job_id,
        status=JobStatus.RUNNING,
        target_url=req.url
    )

    # Simulate timeout worker
    mock_proc = MagicMock()
    mock_proc.is_alive.side_effect = [True, True, False]
    mock_proc.exitcode = None

    with patch("multiprocessing.Process", return_value=mock_proc), \
         patch("app.config.settings.AUTO_CRAWL_TIMEOUT_SECONDS", 0.01):
        await run_scrape_job(job_id, req)

    job = jobs_db[job_id]
    assert job.status == JobStatus.FAILED
    assert job.stats.stop_reason == "timeout"
    assert job.stats.crawl_complete is False
    assert "timed out" in job.status_message.lower()

# 21. PHASE 17.3: Timeout partial checkpoint recovery
def test_timeout_checkpoint_recovery(tmp_path):
    from app.scraper.scrapy_engine.runner import ScrapyJobRunner
    from app.config import OUTPUT_DIR

    job_id = "test_recovery_job"
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Simulate a checkpointed .partial_products.jsonl written during crawl before termination
    partial_file = job_dir / ".partial_products.jsonl"
    with open(partial_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"title": "Recovered Item 1", "price": 10.0, "source_url": "https://example.com/p1"}) + "\n")
        f.write(json.dumps({"title": "Recovered Item 2", "price": 20.0, "source_url": "https://example.com/p2"}) + "\n")

    # If products.json does not exist, running the runner on timeout should recover items into products.json
    mock_proc = MagicMock()
    mock_proc.is_alive.side_effect = [True, True, False]
    mock_proc.exitcode = None

    req = ScrapeRequest(url="https://example.com")
    with patch("multiprocessing.Process", return_value=mock_proc), \
         patch("app.config.settings.AUTO_CRAWL_TIMEOUT_SECONDS", 0.01):
        records, stats = ScrapyJobRunner.run_job(req, job_id)

    assert len(records) == 2
    assert records[0].title == "Recovered Item 1"
    assert records[1].title == "Recovered Item 2"
    assert (job_dir / "products.json").exists()

