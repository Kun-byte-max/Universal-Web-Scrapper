import os
import json
import logging
import time
from pathlib import Path
from app.config import settings, OUTPUT_DIR
from app.scraper.normalizer import normalize_records
from app.scraper.scrapy_engine.items import PageItem, ProductItem, SitemapInventoryItem, UrlInventoryItem


logger = logging.getLogger(__name__)

class ScrapyExtractionPipeline:
    """Item pipeline to validate, normalize, deduplicate, and write JSON output files."""

    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.pages = []
        self.products = []
        self.inventory_map = {}
        self.url_inventory_map = {}
        self.seen_product_keys = set()
        self.seen_page_urls = set()
        self.errors = []
        self.start_time = time.time()
        self.sitemaps_discovered = set()

    @classmethod
    def from_crawler(cls, crawler):
        job_output_dir = crawler.settings.get('JOB_OUTPUT_DIR')
        pipeline = cls(output_dir=job_output_dir)
        pipeline.crawler = crawler
        return pipeline

    def process_item(self, item, spider=None):
        spider_inst = spider or getattr(self, 'crawler', None) and getattr(self.crawler, 'spider', None)

        if isinstance(item, PageItem):
            url = item.get('page_url')
            if url and url not in self.seen_page_urls:
                self.seen_page_urls.add(url)
                page_data = dict(item)
                self.pages.append(page_data)
                try:
                    with open(self.output_dir / ".partial_pages.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps(page_data, ensure_ascii=False) + "\n")
                except Exception as e:
                    logger.debug(f"Could not checkpoint partial page: {e}")
                
                # Check for downloadable files
                files = item.get('downloadable_files', [])
                if files and spider_inst and hasattr(spider_inst, 'stats'):
                    spider_inst.stats['files_discovered'] += len(files)

        elif isinstance(item, ProductItem):
            prod_dict = dict(item)
            title = prod_dict.get('title') or prod_dict.get('name')
            sku = prod_dict.get('sku')
            p_url = prod_dict.get('product_url')

            key = sku or p_url or title
            if key and key not in self.seen_product_keys:
                self.seen_product_keys.add(key)
                self.products.append(prod_dict)
                try:
                    with open(self.output_dir / ".partial_products.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps(prod_dict, ensure_ascii=False) + "\n")
                except Exception as e:
                    logger.debug(f"Could not checkpoint partial product: {e}")

        elif isinstance(item, SitemapInventoryItem):
            inv_dict = dict(item)
            s_url = inv_dict.get('sitemap_url') or inv_dict.get('url')
            if s_url:
                self.sitemaps_discovered.add(s_url)
            
            url_key = inv_dict.get('url') or s_url
            if url_key:
                # Update status if newly reported status is higher priority (crawled > failed > discovered)
                existing = self.inventory_map.get(url_key)
                if not existing or inv_dict.get('status') in ('crawled', 'failed'):
                    self.inventory_map[url_key] = inv_dict

        elif isinstance(item, UrlInventoryItem):
            inv_dict = dict(item)
            norm_url = inv_dict.get('url')
            if norm_url:
                existing = self.url_inventory_map.get(norm_url)
                terminal_states = {"crawled", "failed", "skipped"}
                if existing and existing.get("status") in terminal_states and inv_dict.get("status") not in terminal_states:
                    # Protect terminal state against non-terminal overwrite
                    pass
                else:
                    if existing:
                        existing.update(inv_dict)
                    else:
                        self.url_inventory_map[norm_url] = inv_dict

                try:
                    with open(self.output_dir / ".partial_inventory.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps(inv_dict, ensure_ascii=False) + "\n")
                except Exception as e:
                    logger.debug(f"Could not checkpoint partial inventory item: {e}")

        return item

    def close_spider(self, spider=None):
        spider_inst = spider or getattr(self, 'crawler', None) and getattr(self.crawler, 'spider', None)
        duration = round(time.time() - self.start_time, 2)
        target_url = getattr(spider_inst, 'target_url', '') if spider_inst else ''
        logger.info(f"close_spider called with spider_inst={spider_inst}, target_url='{target_url}', inventory_count={len(self.inventory_map)}")

        def _atomic_dump(data, target_path: Path):
            tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, target_path)

        # 1. website_pages.json
        _atomic_dump(self.pages, self.output_dir / "website_pages.json")

        # 2. products.json
        # Normalize product records
        normalized_prods = normalize_records(self.products, target_url)
        prod_data = [p.model_dump() for p in normalized_prods]
        _atomic_dump(prod_data, self.output_dir / "products.json")

        # 3. sitemap_inventory.json
        spider_sitemap_inventory = getattr(spider_inst, 'sitemap_inventory', {})
        for url_key, inv_item in spider_sitemap_inventory.items():
            if url_key not in self.inventory_map:
                self.inventory_map[url_key] = dict(inv_item)
        sitemap_inventory_list = list(self.inventory_map.values())
        _atomic_dump(sitemap_inventory_list, self.output_dir / "sitemap_inventory.json")

        # 4. url_inventory.json (Unified URL Inventory)
        spider_url_inventory = getattr(spider_inst, 'url_inventory', {})
        for norm_url, inv_entry in spider_url_inventory.items():
            if norm_url not in self.url_inventory_map:
                self.url_inventory_map[norm_url] = dict(inv_entry)
            else:
                existing = self.url_inventory_map[norm_url]
                if inv_entry.get("status") in {"crawled", "failed", "skipped"} and existing.get("status") not in {"crawled", "failed", "skipped"}:
                    existing.update(inv_entry)
                elif inv_entry.get("status") == "crawled" and existing.get("status") != "crawled":
                    existing.update(inv_entry)
                elif inv_entry.get("product_records_extracted", 0) > existing.get("product_records_extracted", 0):
                    existing["product_records_extracted"] = inv_entry.get("product_records_extracted", 0)

        all_inventory_records = list(self.url_inventory_map.values())
        _atomic_dump(all_inventory_records, self.output_dir / "url_inventory.json")

        # 5. extraction_report.json with additive coverage_summary
        crawl_mode = getattr(spider_inst, 'mode', 'bounded')
        stop_reason = getattr(spider_inst, 'stop_reason', 'queue_exhausted')

        # Detect depth cutoff from Scrapy stats
        depth_ignored = 0
        if hasattr(self, 'crawler') and getattr(self.crawler, 'stats', None):
            depth_ignored = self.crawler.stats.get_value("depth/request_ignored_count", 0)
        elif spider_inst and getattr(spider_inst, 'crawler', None) and getattr(spider_inst.crawler, 'stats', None):
            depth_ignored = spider_inst.crawler.stats.get_value("depth/request_ignored_count", 0)

        crawler_errors = getattr(spider_inst, 'crawler_errors', []) if spider_inst else []
        page_errors = getattr(spider_inst, 'page_errors', []) if spider_inst else []

        if stop_reason == "queue_exhausted":
            if depth_ignored > 0:
                stop_reason = "depth_limit_reached"
            elif page_errors:
                stop_reason = "download_error"

        user_max_pages = getattr(spider_inst, 'user_max_pages', None)
        user_max_records = getattr(spider_inst, 'user_max_records', None)

        if crawl_mode == "bounded":
            conf_pages = user_max_pages if user_max_pages is not None else getattr(spider_inst, 'max_pages', 50)
            conf_records = user_max_records if user_max_records is not None else getattr(spider_inst, 'max_records', 100)
        else:
            conf_pages = user_max_pages
            conf_records = user_max_records

        # Calculate Coverage Metrics
        total_discovered = len(all_inventory_records)
        crawled_urls = [u for u in all_inventory_records if u.get("status") == "crawled"]
        failed_urls = [u for u in all_inventory_records if u.get("status") == "failed"]
        skipped_urls = [u for u in all_inventory_records if u.get("status") == "skipped"]
        pending_or_unattempted_urls = [u for u in all_inventory_records if u.get("status") in ("discovered", "pending")]

        skipped_by_reason = {}
        for u in skipped_urls:
            r = u.get("reason") or "unspecified"
            skipped_by_reason[r] = skipped_by_reason.get(r, 0) + 1

        attempted_urls = [u for u in all_inventory_records if u.get("attempt_count", 0) > 0 or u.get("status") in ("crawled", "failed")]
        extracted_pages = [u for u in crawled_urls if u.get("extraction_outcome") == "extracted"]
        empty_pages = [u for u in crawled_urls if u.get("extraction_outcome") == "empty"]
        suspiciously_short_pages = [u for u in crawled_urls if u.get("extraction_outcome") == "suspiciously_short"]

        duplicate_discoveries = getattr(spider_inst, 'duplicate_discoveries', 0) if spider_inst else 0
        total_products_extracted = len(prod_data)

        # Rate calculations with zero denominator guards
        fetch_success_rate = (
            round(len(crawled_urls) / len(attempted_urls), 4)
            if len(attempted_urls) > 0
            else (1.0 if total_discovered == 0 else 0.0)
        )

        content_extraction_rate = (
            round(len(extracted_pages) / len(crawled_urls), 4)
            if len(crawled_urls) > 0
            else (1.0 if total_discovered == 0 else 0.0)
        )

        recorded_outcome_count = len(crawled_urls) + len(failed_urls) + len(skipped_urls)
        url_accounting_rate = (
            round(recorded_outcome_count / total_discovered, 4)
            if total_discovered > 0
            else 1.0
        )

        coverage_warnings = []
        coverage_discrepancies = []

        reconciled_sum = len(crawled_urls) + len(failed_urls) + len(skipped_urls) + len(pending_or_unattempted_urls)
        if reconciled_sum != total_discovered:
            coverage_discrepancies.append(
                f"Reconciliation mismatch: total discovered ({total_discovered}) != sum of status categories ({reconciled_sum})."
            )

        if pending_or_unattempted_urls:
            coverage_warnings.append(
                f"{len(pending_or_unattempted_urls)} discovered URL(s) remained unattempted because crawl ended with stop reason '{stop_reason}'."
            )

        if empty_pages:
            coverage_warnings.append(
                f"{len(empty_pages)} fetched page(s) yielded empty content."
            )

        if suspiciously_short_pages:
            coverage_warnings.append(
                f"{len(suspiciously_short_pages)} fetched page(s) yielded suspiciously short content."
            )

        if depth_ignored > 0:
            coverage_warnings.append(
                f"{depth_ignored} request(s) filtered by Scrapy depth limit middleware."
            )

        # Strict crawl_complete determination (Requirement 6 & Phase 20.2 reconciliation gate)
        is_crawl_complete = (
            stop_reason == "queue_exhausted"
            and len(failed_urls) == 0
            and len(pending_or_unattempted_urls) == 0
            and depth_ignored == 0
            and len(coverage_discrepancies) == 0
            and not getattr(spider_inst, 'root_url_failed', False)
        )

        coverage_summary = {
            "total_urls_discovered": total_discovered,
            "urls_attempted": len(attempted_urls),
            "pages_crawled_successfully": len(crawled_urls),
            "urls_failed": len(failed_urls),
            "urls_skipped": len(skipped_urls),
            "skipped_by_reason": skipped_by_reason,
            "urls_pending_or_unattempted": len(pending_or_unattempted_urls),
            "pages_extracted_successfully": len(extracted_pages),
            "pages_empty": len(empty_pages),
            "pages_suspiciously_short": len(suspiciously_short_pages),
            "product_records_extracted": total_products_extracted,
            "duplicate_discoveries": duplicate_discoveries,
            "crawl_stop_reason": stop_reason,
            "crawl_complete": is_crawl_complete,
            "fetch_success_rate": fetch_success_rate,
            "content_extraction_rate": content_extraction_rate,
            "url_accounting_rate": url_accounting_rate,
            "warnings": coverage_warnings,
            "discrepancies": coverage_discrepancies
        }

        report = {
            "target_url": target_url,
            "job_id": self.output_dir.name,
            "crawl_mode": crawl_mode,
            "stop_reason": stop_reason,
            "crawl_complete": is_crawl_complete,
            "sitemaps_discovered": list(self.sitemaps_discovered),
            "total_sitemaps": len(self.sitemaps_discovered),
            "total_urls_in_inventory": len(sitemap_inventory_list),
            "pages_discovered": getattr(spider_inst, 'pages_discovered_count', len(self.pages)),
            "pages_visited": len(self.pages),
            "products_extracted": len(prod_data),
            "records_extracted": getattr(spider_inst, 'records_extracted_count', len(prod_data)),
            "records_written": len(prod_data),
            "files_discovered": getattr(spider_inst, 'stats', {}).get('files_discovered', 0) if spider_inst else 0,
            "configured_limits": {
                "max_pages": conf_pages,
                "max_records": conf_records
            },
            "emergency_ceilings": {
                "max_pages": getattr(spider_inst, 'emergency_max_pages', getattr(settings, 'AUTO_MAX_PAGES', 500)),
                "max_records": getattr(spider_inst, 'emergency_max_records', getattr(settings, 'AUTO_MAX_RECORDS', 2500)),
                "max_depth": getattr(spider_inst, 'emergency_max_depth', getattr(settings, 'AUTO_MAX_DEPTH', 10)),
                "timeout_seconds": getattr(settings, 'AUTO_CRAWL_TIMEOUT_SECONDS', 600.0)
            },
            "duration_seconds": duration,
            "errors": crawler_errors,
            "coverage_summary": coverage_summary
        }
        _atomic_dump(report, self.output_dir / "extraction_report.json")

        # Clean up temporary scratch checkpoint files on successful completion
        for partial_file in (
            self.output_dir / ".partial_pages.jsonl",
            self.output_dir / ".partial_products.jsonl",
            self.output_dir / ".partial_inventory.jsonl"
        ):
            if partial_file.exists():
                try:
                    partial_file.unlink()
                except OSError:
                    pass

        logger.info(f"Spider finished. Output written to {self.output_dir}")

