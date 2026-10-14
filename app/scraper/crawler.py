import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Callable, Tuple
from urllib.parse import urlparse

from app.models import ScrapeRequest, ExtractedRecord, ScrapeStats
from app.scraper.fetcher import HTTPFetcher
from app.scraper.browser import PlaywrightFetcher
from app.scraper.parser import PageParser
from app.scraper.normalizer import normalize_records
from app.scraper.safety import normalize_url

logger = logging.getLogger(__name__)

Tuple_CrawlResult = Tuple[List[ExtractedRecord], ScrapeStats]

class MultiPageCrawler:
    """Async multi-page web crawler and extraction orchestrator."""

    def __init__(self, request: ScrapeRequest, progress_callback: Optional[Callable[[float, str, ScrapeStats], None]] = None):
        self.request = request
        self.progress_callback = progress_callback
        self.http_fetcher = HTTPFetcher()
        self.browser_fetcher = PlaywrightFetcher()
        self.visited_urls = set()
        self.queue = [normalize_url(request.url)]
        self.raw_records: List[Dict[str, Any]] = []
        self.stats = ScrapeStats(start_time=time.strftime("%Y-%m-%d %H:%M:%S"))

    async def run(self) -> Tuple_CrawlResult:

        start_ts = time.time()
        
        while self.queue and len(self.visited_urls) < self.request.max_pages:
            current_url = self.queue.pop(0)
            if current_url in self.visited_urls:
                continue

            self.visited_urls.add(current_url)
            self.stats.pages_visited += 1

            # Progress update
            progress_pct = (len(self.visited_urls) / self.request.max_pages) * 100.0
            msg = f"Fetching page {len(self.visited_urls)}/{self.request.max_pages}: {current_url}"
            if self.progress_callback:
                self.progress_callback(progress_pct, msg, self.stats)

            # 1. Fetch via HTTP
            html, status, final_url, error = await self.http_fetcher.fetch(current_url)
            
            # 2. Browser fallback if HTTP failed or gave empty content and fallback requested
            if (not html or status != 200) and self.request.use_browser_fallback:
                msg = f"HTTP fetch failed for {current_url} ({error}). Trying Playwright browser fallback..."
                if self.progress_callback:
                    self.progress_callback(progress_pct, msg, self.stats)
                
                html, status, final_url, error = await self.browser_fetcher.fetch(current_url)

            if error:
                self.stats.errors.append(f"{current_url}: {error}")
                continue

            if not html:
                self.stats.errors.append(f"{current_url}: Empty response content")
                continue

            # 3. Parse page
            parser = PageParser(html, final_url)
            page_records, strategy = parser.parse_records()

            # If 0 records extracted from HTTP and browser fallback enabled, attempt browser render
            if not page_records and self.request.use_browser_fallback and not error:
                msg = f"No records found with HTTP parser on {current_url}. Trying Playwright browser fallback..."
                if self.progress_callback:
                    self.progress_callback(progress_pct, msg, self.stats)
                
                b_html, b_status, b_final_url, b_err = await self.browser_fetcher.fetch(current_url)
                if b_html and not b_err:
                    b_parser = PageParser(b_html, b_final_url)
                    b_records, b_strat = b_parser.parse_records()
                    if b_records:
                        page_records = b_records
                        parser = b_parser

            self.raw_records.extend(page_records)
            
            # 4. Discover same-origin links
            new_links = parser.discover_links()
            for link in new_links:
                if link not in self.visited_urls and link not in self.queue:
                    self.queue.append(link)

            # Check max records threshold
            current_normalized = normalize_records(self.raw_records, self.request.url)
            self.stats.records_extracted = len(current_normalized)

            if self.stats.records_extracted >= self.request.max_records:
                break

            # Polite crawl delay
            if self.request.delay_seconds > 0:
                await asyncio.sleep(self.request.delay_seconds)

        end_ts = time.time()
        self.stats.duration_seconds = round(end_ts - start_ts, 2)
        self.stats.end_time = time.strftime("%Y-%m-%d %H:%M:%S")

        # Final normalization & deduplication bounded by max_records
        final_records = normalize_records(self.raw_records, self.request.url)[:self.request.max_records]
        self.stats.records_extracted = len(final_records)

        if self.progress_callback:
            self.progress_callback(100.0, "Scrape completed successfully", self.stats)

        return final_records, self.stats

Tuple_CrawlResult = tuple[List[ExtractedRecord], ScrapeStats]
