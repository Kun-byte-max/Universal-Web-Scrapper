import os
import json
import logging
import multiprocessing
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from app.config import settings, OUTPUT_DIR
from app.models import ScrapeRequest, ScrapeStats, ExtractedRecord

logger = logging.getLogger(__name__)

Tuple_ScrapyRunResult = Tuple[List[ExtractedRecord], ScrapeStats]

def _run_scrapy_process(target_url: str, mode: str, max_pages: Optional[int], max_records: Optional[int], delay_seconds: float, output_dir: str):
    """Sub-process entry point to run Scrapy CrawlerProcess cleanly in isolated Twisted reactor."""
    depth_limit = settings.AUTO_MAX_DEPTH if mode == "auto" else 0
    scrapy_settings = {
        'USER_AGENT': settings.USER_AGENT,
        'ROBOTSTXT_OBEY': False,
        'CONCURRENT_REQUESTS': 8,
        'DOWNLOAD_DELAY': delay_seconds,
        'DOWNLOAD_TIMEOUT': int(settings.REQUEST_TIMEOUT_SECONDS),
        'DOWNLOAD_MAXSIZE': settings.MAX_RESPONSE_BYTES,
        'DEPTH_LIMIT': depth_limit,
        'COOKIES_ENABLED': False,
        'TELNETCONSOLE_ENABLED': False,
        'LOG_LEVEL': 'INFO',
        'ALLOW_PRIVATE_IPS': settings.ALLOW_PRIVATE_IPS,
        'JOB_OUTPUT_DIR': output_dir,
        'DOWNLOADER_MIDDLEWARES': {
            'app.scraper.scrapy_engine.middlewares.SSRFDownloaderMiddleware': 500,
        },
        'ITEM_PIPELINES': {
            'app.scraper.scrapy_engine.pipelines.ScrapyExtractionPipeline': 300,
        }
    }

    from app.scraper.scrapy_engine.spiders.universal_spider import UniversalSitemapSpider

    process = CrawlerProcess(settings=scrapy_settings)
    process.crawl(
        UniversalSitemapSpider,
        target_url=target_url,
        mode=mode,
        max_pages=max_pages,
        max_records=max_records,
        delay_seconds=delay_seconds
    )
    process.start() # Blocks sub-process until crawl completes

class ScrapyJobRunner:
    """Async runner communicating with the Scrapy sub-process."""

    @staticmethod
    def recover_partial_artifacts(
        job_dir: Path,
        target_url: str,
        job_id: str,
        crawl_mode: str = "bounded",
        is_timeout: bool = False,
        is_crash: bool = False,
        exit_code: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        max_pages: Optional[int] = None,
        max_records: Optional[int] = None
    ) -> None:
        """Recover partial checkpointed items and synthesize a truthful report if process halted abnormally."""
        products_file = job_dir / "products.json"
        report_file = job_dir / "extraction_report.json"
        pages_file = job_dir / "website_pages.json"
        inventory_file = job_dir / "url_inventory.json"
        partial_prods_file = job_dir / ".partial_products.jsonl"
        partial_pages_file = job_dir / ".partial_pages.jsonl"
        partial_inv_file = job_dir / ".partial_inventory.jsonl"

        # 1. Recover partial products if products.json is missing
        if not products_file.exists() and partial_prods_file.exists():
            recovered_raw = []
            try:
                with open(partial_prods_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                recovered_raw.append(json.loads(line))
                            except Exception:
                                pass
                if recovered_raw:
                    from app.scraper.normalizer import normalize_records
                    norm_prods = normalize_records(recovered_raw, target_url)
                    prod_data = [p.model_dump() for p in norm_prods]
                    with open(products_file, "w", encoding="utf-8") as f:
                        json.dump(prod_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Error recovering partial products: {e}")

        # 2. Recover partial pages if website_pages.json is missing
        if not pages_file.exists() and partial_pages_file.exists():
            recovered_pages = []
            try:
                with open(partial_pages_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                recovered_pages.append(json.loads(line))
                            except Exception:
                                pass
                if recovered_pages:
                    with open(pages_file, "w", encoding="utf-8") as f:
                        json.dump(recovered_pages, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Error recovering partial pages: {e}")

        # 3. Recover partial inventory if url_inventory.json is missing
        if not inventory_file.exists() and partial_inv_file.exists():
            recovered_inventory = {}
            try:
                from app.scraper.normalizer import normalize_url
                with open(partial_inv_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                inv_obj = json.loads(line)
                                raw_u = inv_obj.get("url")
                                u = normalize_url(raw_u) if raw_u else None
                                if u:
                                    inv_obj["url"] = u
                                    recovered_inventory[u] = inv_obj
                            except Exception:
                                pass
                if recovered_inventory:
                    with open(inventory_file, "w", encoding="utf-8") as f:
                        json.dump(list(recovered_inventory.values()), f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Error recovering partial inventory: {e}")

        # 4. If report file does not exist due to timeout or crash, write truthful partial report
        if not report_file.exists():
            extracted_records_count = 0
            if products_file.exists():
                try:
                    with open(products_file, "r", encoding="utf-8") as pf:
                        extracted_records_count = len(json.load(pf))
                except Exception:
                    pass

            pages_count = 0
            if pages_file.exists():
                try:
                    with open(pages_file, "r", encoding="utf-8") as pf:
                        pages_count = len(json.load(pf))
                except Exception:
                    pass

            if is_timeout:
                error_msg = f"Crawl process exceeded timeout limit of {timeout_seconds}s and was terminated."
                stop_reason = "timeout"
            elif is_crash:
                error_msg = f"Worker process crashed abnormally with exit code {exit_code}."
                stop_reason = "worker_error"
            else:
                error_msg = "Worker process exited abnormally before output serialization."
                stop_reason = "worker_error"

            inv_items = []
            if inventory_file.exists():
                try:
                    with open(inventory_file, "r", encoding="utf-8") as f:
                        inv_items = json.load(f)
                except Exception:
                    pass

            total_inv = len(inv_items)
            crawled_urls = [u for u in inv_items if u.get("status") == "crawled"]
            failed_urls = [u for u in inv_items if u.get("status") == "failed"]
            skipped_urls = [u for u in inv_items if u.get("status") == "skipped"]
            pending_urls = [u for u in inv_items if u.get("status") in ("discovered", "pending")]

            attempted_count = len([u for u in inv_items if u.get("attempt_count", 0) > 0 or u.get("status") in ("crawled", "failed")])
            c_extracted = len([u for u in crawled_urls if u.get("extraction_outcome") == "extracted"])
            c_empty = len([u for u in crawled_urls if u.get("extraction_outcome") == "empty"])
            c_short = len([u for u in crawled_urls if u.get("extraction_outcome") == "suspiciously_short"])

            coverage_summary = {
                "total_urls_discovered": total_inv,
                "urls_attempted": attempted_count,
                "pages_crawled_successfully": len(crawled_urls),
                "urls_failed": len(failed_urls),
                "urls_skipped": len(skipped_urls),
                "skipped_by_reason": {},
                "urls_pending_or_unattempted": len(pending_urls),
                "pages_extracted_successfully": c_extracted,
                "pages_empty": c_empty,
                "pages_suspiciously_short": c_short,
                "product_records_extracted": extracted_records_count,
                "duplicate_discoveries": 0,
                "crawl_stop_reason": stop_reason,
                "crawl_complete": False,
                "fetch_success_rate": round(len(crawled_urls) / attempted_count, 4) if attempted_count > 0 else (1.0 if total_inv == 0 else 0.0),
                "content_extraction_rate": round(c_extracted / len(crawled_urls), 4) if len(crawled_urls) > 0 else (1.0 if total_inv == 0 else 0.0),
                "url_accounting_rate": round((len(crawled_urls) + len(failed_urls) + len(skipped_urls)) / total_inv, 4) if total_inv > 0 else 1.0,
                "warnings": [error_msg],
                "discrepancies": []
            }

            partial_report = {
                "target_url": target_url,
                "job_id": job_id,
                "crawl_mode": crawl_mode,
                "stop_reason": stop_reason,
                "crawl_complete": False,
                "sitemaps_discovered": [],
                "total_sitemaps": 0,
                "total_urls_in_inventory": total_inv,
                "pages_discovered": None,
                "pages_visited": pages_count,
                "products_extracted": extracted_records_count,
                "records_extracted": extracted_records_count,
                "records_written": extracted_records_count,
                "files_discovered": 0,
                "configured_limits": {
                    "max_pages": max_pages,
                    "max_records": max_records
                },
                "emergency_ceilings": {
                    "max_pages": settings.AUTO_MAX_PAGES,
                    "max_records": settings.AUTO_MAX_RECORDS,
                    "max_depth": settings.AUTO_MAX_DEPTH,
                    "timeout_seconds": timeout_seconds
                },
                "duration_seconds": timeout_seconds if is_timeout else 0.0,
                "errors": [error_msg],
                "coverage_summary": coverage_summary
            }
            with open(report_file, "w", encoding="utf-8") as rf:
                json.dump(partial_report, rf, indent=2, ensure_ascii=False)

    @staticmethod
    def run_job(request: ScrapeRequest, job_id: str, progress_callback=None) -> Tuple_ScrapyRunResult:
        job_dir = OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        mode_str = request.mode.value if hasattr(request.mode, 'value') else str(request.mode or 'auto')
        timeout_seconds = float(settings.AUTO_CRAWL_TIMEOUT_SECONDS if mode_str == 'auto' else 300.0)

        if progress_callback:
            progress_callback(10.0, f"Launching Scrapy engine ({mode_str} mode) for {request.url}", ScrapeStats())

        proc = multiprocessing.Process(
            target=_run_scrapy_process,
            args=(request.url, mode_str, request.max_pages, request.max_records, request.delay_seconds, str(job_dir))
        )
        proc.start()
        proc.join(timeout=timeout_seconds)

        is_timeout = False
        if proc.is_alive():
            logger.warning(f"Worker process for job {job_id} exceeded timeout {timeout_seconds}s. Terminating.")
            is_timeout = True
            proc.terminate()
            proc.join(timeout=5.0)
            if proc.is_alive():
                proc.kill()
                proc.join()

        exit_code = proc.exitcode
        is_crash = (not is_timeout) and (exit_code is not None and exit_code != 0)

        # Read results from generated JSON files
        products_file = job_dir / "products.json"
        report_file = job_dir / "extraction_report.json"
        pages_file = job_dir / "website_pages.json"
        inventory_file = job_dir / "url_inventory.json"
        partial_prods_file = job_dir / ".partial_products.jsonl"
        partial_pages_file = job_dir / ".partial_pages.jsonl"
        partial_inv_file = job_dir / ".partial_inventory.jsonl"

        # If child died before close_spider, recover partial checkpointed items
        ScrapyJobRunner.recover_partial_artifacts(
            job_dir=job_dir,
            target_url=request.url,
            job_id=job_id,
            crawl_mode=mode_str,
            is_timeout=is_timeout,
            is_crash=is_crash,
            exit_code=exit_code,
            timeout_seconds=timeout_seconds,
            max_pages=request.max_pages,
            max_records=request.max_records
        )

        extracted_records = []
        if products_file.exists():
            with open(products_file, "r", encoding="utf-8") as f:
                try:
                    raw_prods = json.load(f)
                    for item in raw_prods:
                        extracted_records.append(ExtractedRecord(**item))
                except Exception as e:
                    logger.warning(f"Error reading products.json: {e}")

        stats = ScrapeStats()
        if report_file.exists():
            with open(report_file, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                stats.pages_visited = report_data.get("pages_visited", 0)
                stats.records_extracted = len(extracted_records)
                stats.duration_seconds = report_data.get("duration_seconds", 0.0)
                stats.errors = report_data.get("errors", [])
                stats.stop_reason = report_data.get("stop_reason", "worker_error" if is_crash else ("timeout" if is_timeout else "queue_exhausted"))
                stats.crawl_complete = report_data.get("crawl_complete", False if (is_timeout or is_crash) else True)
        else:
            stats.stop_reason = "timeout" if is_timeout else "worker_error"
            stats.crawl_complete = False

        if is_crash and not any("crashed" in err.lower() or "exit code" in err.lower() for err in stats.errors):
            stats.errors.append(f"Worker process crashed with exit code {exit_code}")

        if progress_callback:
            if is_timeout:
                completion_msg = f"Scrapy job terminated due to timeout. Recovered {len(extracted_records)} products."
            elif is_crash:
                completion_msg = f"Scrapy job failed: worker process crashed with exit code {exit_code}."
            else:
                formatted_reason = stats.stop_reason.replace('_', ' ').title()
                completion_msg = f"Scrapy job finished ({formatted_reason}). Extracted {len(extracted_records)} products."
            progress_callback(100.0, completion_msg, stats)

        return extracted_records, stats

Tuple_ScrapyRunResult = tuple[list, ScrapeStats]
