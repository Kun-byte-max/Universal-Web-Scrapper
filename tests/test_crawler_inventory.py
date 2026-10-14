import json
import io
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import OUTPUT_DIR, settings
from app.models import ScrapeRequest, CrawlMode
from app.scraper.scrapy_engine.spiders.universal_spider import UniversalSitemapSpider
from app.scraper.scrapy_engine.pipelines import ScrapyExtractionPipeline
from app.scraper.scrapy_engine.items import PageItem, ProductItem, SitemapInventoryItem, UrlInventoryItem
from app.scraper.scrapy_engine.runner import ScrapyJobRunner

client = TestClient(app)


def test_url_inventory_lifecycle_transitions():
    """Verify that URL inventory enforces correct lifecycle transitions and protects terminal outcomes."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    # 1. Initial pending
    item_pending = spider.record_url_inventory(
        url="https://example.com/page-1",
        status="pending",
        reason="html_link",
        source_url="https://example.com",
        discovery_method="html_link",
        attempt_count=0
    )
    assert item_pending is not None
    assert item_pending["status"] == "pending"
    assert item_pending["attempt_count"] == 0
    assert item_pending["extraction_outcome"] == "not_attempted"

    # 2. Transition to terminal crawled
    item_crawled = spider.record_url_inventory(
        url="https://example.com/page-1",
        status="crawled",
        reason="success",
        http_status=200,
        content_type="text/html",
        attempt_count=1,
        extraction_outcome="extracted",
        page_extracted=True
    )
    assert item_crawled["status"] == "crawled"
    assert item_crawled["http_status"] == 200
    assert item_crawled["extraction_outcome"] == "extracted"
    assert item_crawled["completed_at"] is not None

    # 3. Subsequent late discovered event should NOT downgrade terminal crawled status
    item_late = spider.record_url_inventory(
        url="https://example.com/page-1",
        status="discovered",
        reason="sitemap_loc",
        source_url="https://example.com/sitemap.xml",
        discovery_method="sitemap"
    )
    assert item_late is None
    assert spider.duplicate_discoveries == 1
    # Canonical record remains crawled
    entry = spider.url_inventory["https://example.com/page-1"]
    assert entry["status"] == "crawled"
    assert entry["http_status"] == 200
    assert entry["extraction_outcome"] == "extracted"


def test_empty_and_suspiciously_short_content_not_mislabeled_as_http_error():
    """A successfully fetched page with empty or short content must have status=crawled and http_status=200."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    item_empty = spider.record_url_inventory(
        url="https://example.com/empty-page",
        status="crawled",
        reason="success",
        http_status=200,
        content_type="text/html",
        attempt_count=1,
        extraction_outcome="empty",
        page_extracted=True
    )
    assert item_empty["status"] == "crawled"
    assert item_empty["http_status"] == 200
    assert item_empty["extraction_outcome"] == "empty"

    item_short = spider.record_url_inventory(
        url="https://example.com/short-page",
        status="crawled",
        reason="success",
        http_status=200,
        content_type="text/html",
        attempt_count=1,
        extraction_outcome="suspiciously_short",
        page_extracted=True
    )
    assert item_short["status"] == "crawled"
    assert item_short["http_status"] == 200
    assert item_short["extraction_outcome"] == "suspiciously_short"


def test_cross_origin_and_non_html_exclusions():
    """Cross-origin links and non-HTML assets must be recorded as skipped with proper reasons."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    # Cross origin
    item_co = spider.record_url_inventory(
        url="https://other-domain.com/about",
        status="skipped",
        reason="cross_origin",
        source_url="https://example.com",
        discovery_method="html_link",
        extraction_outcome="not_applicable"
    )
    assert item_co["status"] == "skipped"
    assert item_co["reason"] == "cross_origin"
    assert item_co["extraction_outcome"] == "not_applicable"

    # Non-HTML asset
    item_asset = spider.record_url_inventory(
        url="https://example.com/assets/manual.pdf",
        status="skipped",
        reason="non_html_asset",
        source_url="https://example.com",
        discovery_method="html_link",
        extraction_outcome="not_applicable"
    )
    assert item_asset["status"] == "skipped"
    assert item_asset["reason"] == "non_html_asset"
    assert item_asset["extraction_outcome"] == "not_applicable"


def test_pipeline_coverage_reconciliation_and_zero_denominators(tmp_path):
    """Pipeline calculates coverage summary with mathematical reconciliation and safe zero denominators."""
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")
    spider.stop_reason = "queue_exhausted"

    # Feed 1 crawled, 1 failed, 1 skipped, 1 pending
    pipeline.process_item(UrlInventoryItem(
        url="https://example.com/p1",
        status="crawled",
        reason="success",
        http_status=200,
        attempt_count=1,
        extraction_outcome="extracted",
        page_extracted=True,
        product_records_extracted=1
    ), spider)

    pipeline.process_item(UrlInventoryItem(
        url="https://example.com/p2",
        status="failed",
        reason="http_error",
        http_status=404,
        attempt_count=1,
        extraction_outcome="not_available",
        page_extracted=False
    ), spider)

    pipeline.process_item(UrlInventoryItem(
        url="https://external.com",
        status="skipped",
        reason="cross_origin",
        http_status=None,
        attempt_count=0,
        extraction_outcome="not_applicable"
    ), spider)

    pipeline.process_item(UrlInventoryItem(
        url="https://example.com/pending-page",
        status="pending",
        reason="html_link",
        http_status=None,
        attempt_count=0,
        extraction_outcome="not_attempted"
    ), spider)

    pipeline.close_spider(spider)

    report_path = tmp_path / "extraction_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    coverage = report.get("coverage_summary")
    assert coverage is not None

    # Total discovered must be exactly 4
    assert coverage["total_urls_discovered"] == 4
    assert coverage["pages_crawled_successfully"] == 1
    assert coverage["urls_failed"] == 1
    assert coverage["urls_skipped"] == 1
    assert coverage["urls_pending_or_unattempted"] == 1

    # Exact reconciliation check
    reconciled = (
        coverage["pages_crawled_successfully"]
        + coverage["urls_failed"]
        + coverage["urls_skipped"]
        + coverage["urls_pending_or_unattempted"]
    )
    assert reconciled == coverage["total_urls_discovered"]
    assert coverage["discrepancies"] == []

    # Rates:
    # Attempted = 2 (p1 and p2)
    assert coverage["urls_attempted"] == 2
    # Fetch success rate = 1 / 2 = 0.5
    assert coverage["fetch_success_rate"] == 0.5
    # Content extraction rate = 1 / 1 = 1.0
    assert coverage["content_extraction_rate"] == 1.0
    # URL accounting rate = (1 + 1 + 1) / 4 = 0.75
    assert coverage["url_accounting_rate"] == 0.75

    # crawl_complete must be False because 1 failed and 1 unattempted URL remained
    assert coverage["crawl_complete"] is False
    assert report["crawl_complete"] is False


def test_pipeline_zero_denominators_handling(tmp_path):
    """Pipeline handles zero denominators cleanly when inventory is empty."""
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")
    spider.stop_reason = "queue_exhausted"

    pipeline.close_spider(spider)

    report = json.loads((tmp_path / "extraction_report.json").read_text(encoding="utf-8"))
    coverage = report["coverage_summary"]

    assert coverage["total_urls_discovered"] == 0
    assert coverage["fetch_success_rate"] == 1.0
    assert coverage["content_extraction_rate"] == 1.0
    assert coverage["url_accounting_rate"] == 1.0
    assert coverage["crawl_complete"] is True


def test_strict_crawl_complete_semantics(tmp_path):
    """Crawl complete rule: True only when stop_reason is queue_exhausted, 0 failures, 0 unattempted, 0 depth drops."""
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")
    spider.stop_reason = "bounded_page_limit_reached" # Limit reached

    pipeline.process_item(UrlInventoryItem(
        url="https://example.com",
        status="crawled",
        reason="success",
        http_status=200,
        attempt_count=1,
        extraction_outcome="extracted",
        page_extracted=True
    ), spider)

    pipeline.close_spider(spider)

    report = json.loads((tmp_path / "extraction_report.json").read_text(encoding="utf-8"))
    assert report["coverage_summary"]["crawl_complete"] is False
    assert report["crawl_complete"] is False


def test_api_inventory_pagination_and_validation(tmp_path):
    """Test /api/jobs/{job_id}/inventory endpoint with pagination, status filtering, and validation."""
    job_id = "test-inventory-api-job"
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    items = [
        {"url": f"https://example.com/item-{i}", "status": "crawled" if i < 3 else "skipped", "reason": "success" if i < 3 else "cross_origin"}
        for i in range(5)
    ]
    with open(job_dir / "url_inventory.json", "w", encoding="utf-8") as f:
        json.dump(items, f)

    try:
        # 1. Page 1, size 2
        res = client.get(f"/api/jobs/{job_id}/inventory?page=1&page_size=2")
        assert res.status_code == 200
        data = res.json()
        assert data["total_items"] == 5
        assert data["total_pages"] == 3
        assert len(data["items"]) == 2
        assert data["items"][0]["url"] == "https://example.com/item-0"

        # 2. Status filter = skipped
        res_filter = client.get(f"/api/jobs/{job_id}/inventory?status=skipped")
        assert res_filter.status_code == 200
        filter_data = res_filter.json()
        assert filter_data["total_items"] == 2
        assert all(it["status"] == "skipped" for it in filter_data["items"])

        # 3. Validation: page < 1
        res_bad_page = client.get(f"/api/jobs/{job_id}/inventory?page=0")
        assert res_bad_page.status_code == 400
        assert "Invalid page" in res_bad_page.json()["detail"]

        # 4. Validation: page_size > 500
        res_bad_size = client.get(f"/api/jobs/{job_id}/inventory?page_size=600")
        assert res_bad_size.status_code == 400
        assert "Invalid page_size" in res_bad_size.json()["detail"]

        # 5. Validation: invalid status filter
        res_bad_status = client.get(f"/api/jobs/{job_id}/inventory?status=unknown_status")
        assert res_bad_status.status_code == 400
        assert "Invalid status filter" in res_bad_status.json()["detail"]

        # 6. Path traversal rejection
        res_traversal = client.get("/api/jobs/../etc/inventory")
        assert res_traversal.status_code in (400, 404)
    finally:
        # Cleanup
        if job_dir.exists():
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)


def test_zip_bundle_includes_url_inventory_when_present():
    """Verify ZIP bundle includes url_inventory.json when present while maintaining 4-file compatibility."""
    job_id = "test-bundle-inventory-job"
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        (job_dir / "products.json").write_text("[]", encoding="utf-8")
        (job_dir / "website_pages.json").write_text("[]", encoding="utf-8")
        (job_dir / "extraction_report.json").write_text("{}", encoding="utf-8")
        (job_dir / "sitemap_inventory.json").write_text("[]", encoding="utf-8")
        (job_dir / "url_inventory.json").write_text("[]", encoding="utf-8")

        res = client.get(f"/api/jobs/{job_id}/download/bundle")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"

        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            namelist = zf.namelist()
            assert "products.json" in namelist
            assert "website_pages.json" in namelist
            assert "extraction_report.json" in namelist
            assert "sitemap_inventory.json" in namelist
            assert "url_inventory.json" in namelist

        # Download artifact directly
        art_res = client.get(f"/api/jobs/{job_id}/download/inventory")
        assert art_res.status_code == 200
        assert art_res.headers["content-disposition"] == 'attachment; filename="url_inventory.json"'
    finally:
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)


def test_runner_partial_inventory_recovery(tmp_path):
    """ScrapyJobRunner recovers partial url inventory on simulated process crash and writes coverage_summary."""
    job_id = "test-runner-recovery-job"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write checkpoint files with valid items, canonical URL duplicates, and a malformed trailing line
    partial_inv = job_dir / ".partial_inventory.jsonl"
    with open(partial_inv, "w", encoding="utf-8") as f:
        # Valid crawled entry
        f.write(json.dumps({"url": "https://example.com/p1", "status": "crawled", "attempt_count": 1, "extraction_outcome": "extracted"}) + "\n")
        # Duplicate of p1 with uppercase scheme and fragment (to verify canonical deduplication)
        f.write(json.dumps({"url": "HTTPS://EXAMPLE.COM/p1#fragment", "status": "crawled", "attempt_count": 1, "extraction_outcome": "extracted"}) + "\n")
        # Valid pending entry
        f.write(json.dumps({"url": "https://example.com/p2", "status": "pending", "attempt_count": 0, "extraction_outcome": "not_attempted"}) + "\n")
        # Malformed incomplete JSON line (must not crash recovery)
        f.write('{"url": "https://example.com/truncated-line\n')

    # Partial pages checkpoint
    partial_pages = job_dir / ".partial_pages.jsonl"
    with open(partial_pages, "w", encoding="utf-8") as f:
        f.write(json.dumps({"page_url": "https://example.com/p1", "title": "P1"}) + "\n")
        f.write("malformed-page-json\n")

    # 2. Invoke actual production recovery helper with is_crash=True
    ScrapyJobRunner.recover_partial_artifacts(
        job_dir=job_dir,
        target_url="https://example.com",
        job_id=job_id,
        crawl_mode="bounded",
        is_crash=True,
        exit_code=137,
        max_pages=10,
        max_records=50
    )

    # 3. Verify url_inventory.json is synthesized and deduplicated
    inv_file = job_dir / "url_inventory.json"
    assert inv_file.exists()
    recovered_inv = json.loads(inv_file.read_text(encoding="utf-8"))
    assert len(recovered_inv) == 2  # deduplicated p1 + p2, malformed skipped
    inv_urls = {item["url"] for item in recovered_inv}
    assert "https://example.com/p1" in inv_urls
    assert "https://example.com/p2" in inv_urls

    # 4. Verify website_pages.json synthesized
    pages_file = job_dir / "website_pages.json"
    assert pages_file.exists()
    recovered_pages = json.loads(pages_file.read_text(encoding="utf-8"))
    assert len(recovered_pages) == 1

    # 5. Verify fallback extraction_report.json synthesized with coverage_summary
    report_file = job_dir / "extraction_report.json"
    assert report_file.exists()
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["crawl_complete"] is False
    assert report["stop_reason"] == "worker_error"
    assert "137" in report["errors"][0]

    cov = report["coverage_summary"]
    assert cov["crawl_complete"] is False
    assert cov["crawl_stop_reason"] == "worker_error"
    assert cov["total_urls_discovered"] == 2
    assert cov["pages_crawled_successfully"] == 1
    assert cov["urls_pending_or_unattempted"] == 1

    # 6. Verify existing final artifacts are NOT overwritten if called again
    original_report_content = report_file.read_text(encoding="utf-8")
    ScrapyJobRunner.recover_partial_artifacts(
        job_dir=job_dir,
        target_url="https://example.com",
        job_id=job_id,
        crawl_mode="bounded",
        is_timeout=True,  # different reason
        timeout_seconds=60
    )
    assert report_file.read_text(encoding="utf-8") == original_report_content


def test_redirects_and_retry_attempt_count():
    """Verify that redirects record redirect sources as skipped and preserve accurate attempt_count with retries."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    from scrapy.http import HtmlResponse, Request

    req = Request(
        url="https://example.com/dest",
        meta={
            "redirect_urls": ["https://example.com/source-old"],
            "retry_times": 2
        }
    )
    res = HtmlResponse(
        url="https://example.com/dest",
        request=req,
        body=b"<html><head><title>Dest</title></head><body><p>Hello world full content here</p></body></html>",
        encoding="utf-8"
    )

    items = list(spider.parse_page(res))
    assert isinstance(items[0], PageItem)

    # Check redirect source
    source_item = spider.url_inventory.get("https://example.com/source-old")
    assert source_item is not None
    assert source_item["status"] == "skipped"
    assert source_item["reason"] == "redirect"
    assert source_item["attempt_count"] == 1

    # Check destination
    dest_item = spider.url_inventory.get("https://example.com/dest")
    assert dest_item is not None
    assert dest_item["status"] == "crawled"
    assert dest_item["attempt_count"] == 3  # 1 initial + 2 retries


def test_handle_error_failures_and_timeouts():
    """Verify that failure errback records failed status, accurate attempt count, and structured error details."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    from twisted.python.failure import Failure
    from scrapy.http import Request, Response

    # 1. HTTP 500 error with retry
    req = Request(url="https://example.com/server-error", meta={"retry_times": 1})
    resp = Response(url="https://example.com/server-error", status=500)
    exc = Exception("Internal Server Error")
    exc.response = resp
    fail = Failure(exc)
    fail.request = req

    spider.handle_error(fail)
    err_inv = spider.url_inventory.get("https://example.com/server-error")
    assert err_inv is not None
    assert err_inv["status"] == "failed"
    assert err_inv["reason"] == "http_error"
    assert err_inv["http_status"] == 500
    assert err_inv["attempt_count"] == 2
    assert err_inv["extraction_outcome"] == "not_available"

    # 2. Timeout error
    req_to = Request(url="https://example.com/timeout", meta={"retry_times": 0})
    exc_to = TimeoutError("Connection timed out after 30s")
    fail_to = Failure(exc_to)
    fail_to.request = req_to

    spider.handle_error(fail_to)
    to_inv = spider.url_inventory.get("https://example.com/timeout")
    assert to_inv is not None
    assert to_inv["status"] == "failed"
    assert to_inv["reason"] == "timeout"
    assert to_inv["attempt_count"] == 1


def test_page_limit_skipping_internal_links():
    """When max_pages is reached, newly discovered links must be recorded as skipped with reason=page_limit."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded", max_pages=1)
    spider.pages_visited_count = 0

    from scrapy.http import HtmlResponse, Request

    req = Request(url="https://example.com")
    html = """
    <html>
      <head><title>Home</title></head>
      <body>
        <a href="/page-new">New Page</a>
      </body>
    </html>
    """
    res = HtmlResponse(url="https://example.com", request=req, body=html.encode("utf-8"), encoding="utf-8")

    items = list(spider.parse_page(res))
    assert isinstance(items[0], PageItem)

    page_skip = spider.url_inventory.get("https://example.com/page-new")
    assert page_skip is not None
    assert page_skip["status"] == "skipped"
    assert page_skip["reason"] == "page_limit"
    assert page_skip["extraction_outcome"] == "not_attempted"


def test_discovered_to_pending_to_crawled_lifecycle():
    """Verify clean full lifecycle progression: discovered -> pending -> crawled."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    # 1. Discovered
    item_disc = spider.record_url_inventory(
        url="https://example.com/item",
        status="discovered",
        reason="start_url"
    )
    assert item_disc["status"] == "discovered"

    # 2. Transition to pending
    item_pend = spider.record_url_inventory(
        url="https://example.com/item",
        status="pending",
        reason="scheduled"
    )
    assert item_pend["status"] == "pending"

    # 3. Transition to crawled
    item_crawl = spider.record_url_inventory(
        url="https://example.com/item",
        status="crawled",
        reason="success",
        http_status=200,
        extraction_outcome="extracted",
        page_extracted=True
    )
    assert item_crawl["status"] == "crawled"
    assert item_crawl["extraction_outcome"] == "extracted"
    assert spider.url_inventory["https://example.com/item"]["status"] == "crawled"


def test_crawled_url_cannot_be_downgraded_by_limit_or_duplicate():
    """A crawled URL must resist downgrades to skipped/failed and protect its extraction outcome."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    spider.record_url_inventory(
        url="https://example.com/page-1",
        status="crawled",
        reason="success",
        http_status=200,
        extraction_outcome="extracted",
        page_extracted=True,
        product_records_extracted=3
    )

    # 1. Late limit skip attempt must NOT downgrade status or reset extraction outcome
    res_skip = spider.record_url_inventory(
        url="https://example.com/page-1",
        status="skipped",
        reason="page_limit",
        extraction_outcome="not_attempted"
    )
    assert res_skip is None
    entry = spider.url_inventory["https://example.com/page-1"]
    assert entry["status"] == "crawled"
    assert entry["reason"] == "success"
    assert entry["extraction_outcome"] == "extracted"
    assert entry["product_records_extracted"] == 3

    # 2. Late failed attempt must NOT downgrade crawled status
    res_fail = spider.record_url_inventory(
        url="https://example.com/page-1",
        status="failed",
        reason="http_error",
        http_status=500
    )
    assert res_fail is None
    assert entry["status"] == "crawled"
    assert entry["http_status"] == 200

    # 3. Late duplicate discovery attempt with not_attempted must NOT clobber extracted outcome
    res_disc = spider.record_url_inventory(
        url="https://example.com/page-1",
        status="discovered",
        reason="sitemap_loc",
        extraction_outcome="not_attempted"
    )
    assert res_disc is None
    assert entry["status"] == "crawled"
    assert entry["extraction_outcome"] == "extracted"


def test_failed_url_can_transition_to_crawled_on_successful_retry():
    """An earlier failed attempt must legitimately transition to crawled when a retry succeeds."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    # 1. Initial failure
    item_fail = spider.record_url_inventory(
        url="https://example.com/flaky",
        status="failed",
        reason="http_error",
        http_status=500,
        attempt_count=1,
        error_type="HttpError",
        error_message="500 Internal Server Error"
    )
    assert item_fail["status"] == "failed"
    assert item_fail["http_status"] == 500

    # Late limit skip must NOT overwrite failed status
    res_skip = spider.record_url_inventory(
        url="https://example.com/flaky",
        status="skipped",
        reason="page_limit"
    )
    assert res_skip is None
    assert spider.url_inventory["https://example.com/flaky"]["status"] == "failed"

    # 2. Successful retry upgrade
    item_succ = spider.record_url_inventory(
        url="https://example.com/flaky",
        status="crawled",
        reason="success",
        http_status=200,
        attempt_count=2,
        extraction_outcome="extracted",
        page_extracted=True
    )
    assert item_succ is not None
    assert item_succ["status"] == "crawled"
    assert item_succ["http_status"] == 200
    assert item_succ["attempt_count"] == 2
    assert item_succ["error_type"] is None
    assert item_succ["error_message"] is None

    # Canonical inventory entry is now crawled
    entry = spider.url_inventory["https://example.com/flaky"]
    assert entry["status"] == "crawled"
    assert entry["http_status"] == 200


def test_sitemap_limit_does_not_downgrade_previously_crawled_url():
    """Sitemap processing after page limit ceiling does not downgrade already crawled URLs."""
    from scrapy.http import TextResponse, Request

    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded", max_pages=1)

    # Simulate that https://example.com/already-crawled has already been crawled
    spider.record_url_inventory(
        url="https://example.com/already-crawled",
        status="crawled",
        reason="success",
        http_status=200,
        attempt_count=1,
        extraction_outcome="extracted",
        page_extracted=True
    )
    spider.pages_visited_count = 1  # Hit max_pages ceiling

    # Parse a sitemap containing the already crawled page AND a new page
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/already-crawled</loc></url>
      <url><loc>https://example.com/brand-new-page</loc></url>
    </urlset>
    """
    req = Request(url="https://example.com/sitemap.xml")
    resp = TextResponse(url="https://example.com/sitemap.xml", request=req, body=sitemap_xml.encode("utf-8"), encoding="utf-8")

    results = list(spider.parse_sitemap_xml(resp))

    # The already crawled entry must remain crawled
    already = spider.url_inventory.get("https://example.com/already-crawled")
    assert already is not None
    assert already["status"] == "crawled"
    assert already["extraction_outcome"] == "extracted"

    # The brand new page must be skipped due to page limit
    new_entry = spider.url_inventory.get("https://example.com/brand-new-page")
    assert new_entry is not None
    assert new_entry["status"] == "skipped"
    assert new_entry["reason"] == "page_limit"


def test_duplicate_url_discovery_does_not_create_second_canonical_entry():
    """Duplicate URL discoveries normalize to the same canonical key and do not inflate inventory count."""
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")

    # Discover URL in different formats (casing and fragment)
    spider.record_url_inventory(url="https://example.com/product", status="pending", reason="html_link")
    spider.record_url_inventory(url="https://example.com/product#section2", status="pending", reason="html_link")
    spider.record_url_inventory(url="HTTPS://EXAMPLE.COM/product", status="discovered", reason="sitemap")

    assert len(spider.url_inventory) == 1
    assert "https://example.com/product" in spider.url_inventory
    assert spider.duplicate_discoveries == 2


def test_crawl_complete_blocked_by_reconciliation_discrepancy(tmp_path):
    """crawl_complete must be False if coverage_discrepancies is non-empty, even with queue_exhausted."""
    pipeline = ScrapyExtractionPipeline(output_dir=tmp_path)
    spider = UniversalSitemapSpider(target_url="https://example.com", mode="bounded")
    spider.stop_reason = "queue_exhausted"

    # Inject an inventory entry with an abnormal status that triggers a discrepancy
    bad_entry = {
        "url": "https://example.com/corrupt",
        "status": "unknown_illegal_status",
        "reason": "bug",
        "attempt_count": 0,
        "extraction_outcome": "not_attempted"
    }
    spider.url_inventory["https://example.com/corrupt"] = bad_entry

    pipeline.close_spider(spider)

    report_path = tmp_path / "extraction_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cov = report["coverage_summary"]

    assert len(cov["discrepancies"]) > 0
    assert cov["crawl_complete"] is False
    assert report["crawl_complete"] is False


