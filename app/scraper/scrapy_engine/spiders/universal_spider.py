import re
import gzip
import time
import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
from typing import List, Dict, Any, Optional

import scrapy
from scrapy.http import Request, Response, TextResponse

from app.scraper.scrapy_engine.items import (
    PageItem,
    ProductItem,
    SitemapInventoryItem,
    UrlInventoryItem,
    ExtractionReportItem
)
from app.scraper.parser import PageParser
from app.scraper.safety import is_same_origin, normalize_url
from app.scraper.extractors import clean_text

logger = logging.getLogger(__name__)

DOC_EXTENSIONS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.csv')

NON_PAGE_EXTENSIONS = (
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp', '.tiff', '.tif',
    # Documents / Archives
    '.pdf', '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.csv',
    # Media
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', '.wav',
    # Web assets / code / data feeds
    '.css', '.js', '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.xml', '.json'
)

def is_non_page_asset_url(url: str) -> bool:
    """
    Check if a URL points to a known non-page asset extension.
    Correctly ignores query strings and fragments by inspecting urlparse(url).path.
    Does not block HTML pages with dots in query parameters.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in NON_PAGE_EXTENSIONS)
    except Exception:
        return False

# Event-driven valid lifecycle transitions:
# - discovered: unqueued initial discovery, can transition to pending, crawled, failed, or skipped
# - pending: scheduled for fetch, can transition to crawled (success), failed (error), or skipped (redirect/non-html)
# - skipped: excluded by rule, can only be upgraded by an actual fetch result (crawled or failed)
# - failed: fetch error, can transition to crawled if a subsequent retry attempt succeeds
# - crawled: terminal success state, cannot transition to any other status
VALID_LIFECYCLE_TRANSITIONS = {
    "discovered": {"pending", "crawled", "failed", "skipped"},
    "pending": {"crawled", "failed", "skipped"},
    "skipped": {"crawled", "failed"},
    "failed": {"crawled"},
    "crawled": set(),
}

class UniversalSitemapSpider(scrapy.Spider):
    name = "universal_sitemap_spider"

    def __init__(self, target_url: str = "", mode: Optional[str] = None, max_pages: Optional[int] = None, max_records: Optional[int] = None, delay_seconds: float = 0.5, *args, **kwargs):
        super().__init__(*args, **kwargs)
        raw_url = target_url or kwargs.get('target_url') or (args[0] if args else "")
        self.raw_target_url = str(raw_url) if raw_url else ""
        self.target_url = normalize_url(self.raw_target_url) if self.raw_target_url else ""
        self.start_urls = [self.target_url] if self.target_url else []

        # Determine mode
        mode_arg = mode if mode is not None else kwargs.get('mode')
        if mode_arg is None or str(mode_arg).strip() == "":
            if max_pages is not None or max_records is not None:
                self.mode = "bounded"
            else:
                self.mode = "auto"
        else:
            self.mode = str(mode_arg).strip().lower()

        from app.config import settings
        self.emergency_max_pages = getattr(settings, 'AUTO_MAX_PAGES', 500)
        self.emergency_max_records = getattr(settings, 'AUTO_MAX_RECORDS', 2500)
        self.emergency_max_depth = getattr(settings, 'AUTO_MAX_DEPTH', 10)

        # User specified limits
        self.user_max_pages = int(max_pages) if max_pages is not None else None
        self.user_max_records = int(max_records) if max_records is not None else None

        # Effective limits applied during crawling
        if self.mode == "bounded":
            self.max_pages = self.user_max_pages if self.user_max_pages is not None else 5
            self.max_records = self.user_max_records if self.user_max_records is not None else 50
        else:
            self.max_pages = self.emergency_max_pages
            self.max_records = self.emergency_max_records

        self.delay_seconds = float(delay_seconds)
        
        parsed = urlparse(self.target_url) if self.target_url else urlparse("https://example.com")
        netloc = parsed.netloc.lower()
        host = netloc.split(":")[0]
        if host.startswith("www."):
            self.allowed_domains = [host, host[4:]]
        elif host:
            self.allowed_domains = [host, f"www.{host}"]
        else:
            self.allowed_domains = []

        self.origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
        
        self.pages_visited_count = 0
        self.records_extracted_count = 0
        self.visited_page_urls = set()
        self.discovered_urls = set()
        if self.target_url:
            self.discovered_urls.add(self.target_url)

        self.crawler_errors = []
        self.page_errors = []
        self.asset_errors = []
        self.sitemap_candidate_failures = {}
        self.sitemap_candidates_attempted = set()
        self.sitemap_inventory = {}
        self.url_inventory: Dict[str, Dict[str, Any]] = {}
        self.duplicate_discoveries = 0
        self.root_url_failed = False
        self.stats = {'files_discovered': 0}
        self.stop_reason = "queue_exhausted"
        self.crawl_complete = True

    def record_url_inventory(
        self,
        url: str,
        status: str,
        reason: str,
        source_url: Optional[str] = None,
        discovery_method: Optional[str] = None,
        http_status: Optional[int] = None,
        content_type: Optional[str] = None,
        attempt_count: int = 0,
        depth: Optional[int] = None,
        extraction_outcome: str = "not_attempted",
        page_extracted: bool = False,
        product_records_extracted: int = 0,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Optional[UrlInventoryItem]:
        """Record or update a canonical URL inventory entry, enforcing state transition rules."""
        norm_url = normalize_url(url)
        if not norm_url:
            return None

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        existing = self.url_inventory.get(norm_url)

        if existing:
            current_status = existing.get("status")

            # Check if this is an update with the same status
            if status == current_status:
                if status in {"crawled", "failed"}:
                    # Legitimate in-place update for crawled/failed (e.g. metadata, retries, products)
                    if reason:
                        existing["reason"] = reason
                    if http_status is not None:
                        existing["http_status"] = http_status
                    if content_type is not None:
                        existing["content_type"] = content_type
                    if attempt_count > 0:
                        existing["attempt_count"] = max(existing.get("attempt_count", 0), attempt_count)
                    if depth is not None:
                        existing["depth"] = depth
                    if extraction_outcome != "not_attempted":
                        existing["extraction_outcome"] = extraction_outcome
                    if page_extracted:
                        existing["page_extracted"] = True
                    if product_records_extracted > 0:
                        existing["product_records_extracted"] = max(
                            existing.get("product_records_extracted", 0), product_records_extracted
                        )
                    if error_type is not None:
                        existing["error_type"] = error_type
                    if error_message is not None:
                        existing["error_message"] = error_message
                    return UrlInventoryItem(**existing)
                else:
                    # Duplicate discovery or redundant skip/pending notification
                    self.duplicate_discoveries += 1
                    if attempt_count > 0:
                        existing["attempt_count"] = max(existing.get("attempt_count", 0), attempt_count)
                    return None

            # Status transition requested: verify validity against lifecycle rules
            allowed_next_states = VALID_LIFECYCLE_TRANSITIONS.get(current_status, set())
            if status not in allowed_next_states:
                # Invalid transition (e.g. crawled -> skipped, crawled -> failed, failed -> skipped)
                self.duplicate_discoveries += 1
                if attempt_count > 0:
                    existing["attempt_count"] = max(existing.get("attempt_count", 0), attempt_count)
                return None

            # Valid lifecycle transition: apply state change and update fields
            existing["status"] = status
            if reason:
                existing["reason"] = reason
            if http_status is not None:
                existing["http_status"] = http_status
            if content_type is not None:
                existing["content_type"] = content_type
            if attempt_count > 0:
                existing["attempt_count"] = max(existing.get("attempt_count", 0), attempt_count)
            if depth is not None:
                existing["depth"] = depth
            if extraction_outcome != "not_attempted":
                existing["extraction_outcome"] = extraction_outcome
            if page_extracted:
                existing["page_extracted"] = True
            if product_records_extracted > 0:
                existing["product_records_extracted"] = max(
                    existing.get("product_records_extracted", 0), product_records_extracted
                )

            if status == "crawled":
                # Clear previous failure markers if this is a successful retry
                existing["error_type"] = None
                existing["error_message"] = None
                existing["completed_at"] = now
            elif status == "failed":
                if error_type is not None:
                    existing["error_type"] = error_type
                if error_message is not None:
                    existing["error_message"] = error_message
                existing["completed_at"] = now
            elif status == "skipped":
                existing["completed_at"] = now

            return UrlInventoryItem(**existing)

        entry = {
            "url": norm_url,
            "source_url": source_url,
            "discovery_method": discovery_method or "unknown",
            "status": status,
            "reason": reason,
            "http_status": http_status,
            "content_type": content_type,
            "attempt_count": attempt_count,
            "depth": depth,
            "discovered_at": now,
            "completed_at": now if status in {"crawled", "failed", "skipped"} else None,
            "extraction_outcome": extraction_outcome,
            "page_extracted": page_extracted,
            "product_records_extracted": product_records_extracted,
            "error_type": error_type,
            "error_message": error_message
        }
        self.url_inventory[norm_url] = entry
        self.discovered_urls.add(norm_url)
        return UrlInventoryItem(**entry)

    @property
    def pages_discovered_count(self) -> int:
        return len(self.discovered_urls)

    def parse(self, response: Response):
        return self.parse_page(response)

    def start_requests(self):
        self.logger.info(f"UniversalSitemapSpider.start_requests called with target_url='{self.target_url}'")
        if not self.target_url:
            self.logger.warning("No target_url specified in start_requests.")
            return

        self.record_url_inventory(
            url=self.target_url,
            status="pending",
            reason="start_url",
            discovery_method="start_url",
            attempt_count=0
        )

        yield Request(
            url=self.target_url,
            callback=self.parse_page,
            errback=self.handle_error,
            dont_filter=True,
            meta={'sitemap_source': None, 'lastmod': None, 'is_start_url': True}
        )

        # 2. Dynamic sitemap candidate URLs with high priority
        sitemap_candidates = [
            f"{self.origin}/robots.txt",
            f"{self.origin}/wp-sitemap.xml",
            f"{self.origin}/sitemap.xml",
            f"{self.origin}/sitemap_index.xml"
        ]

        for s_url in sitemap_candidates:
            self.sitemap_candidates_attempted.add(s_url)
            yield Request(
                url=s_url,
                callback=self.parse_sitemap_or_robots,
                errback=self.handle_sitemap_error,
                dont_filter=True,
                priority=100,
                meta={'is_candidate_probe': True}
            )


    def parse_sitemap_or_robots(self, response: Response):
        self.logger.info(f"parse_sitemap_or_robots received url={response.url} status={response.status}")
        if response.status != 200:
            is_candidate = response.meta.get("is_candidate_probe", False)
            if not is_candidate:
                yield SitemapInventoryItem(
                    url=response.url,
                    sitemap_url=response.url,
                    lastmod=None,
                    status="failed",
                    reason=f"HTTP {response.status}"
                )
            return

        yield SitemapInventoryItem(
            url=response.url,
            sitemap_url=response.url,
            lastmod=None,
            status="crawled",
            reason="Root sitemap or robots.txt"
        )

        if response.url.endswith("/robots.txt"):
            for line in response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    s_url = line.split(":", 1)[1].strip()
                    self.logger.info(f"Found sitemap in robots.txt: {s_url}")
                    yield SitemapInventoryItem(
                        url=s_url,
                        sitemap_url=response.url,
                        lastmod=None,
                        status="discovered",
                        reason="Discovered from robots.txt"
                    )
                    yield Request(url=s_url, callback=self.parse_sitemap_xml, errback=self.handle_sitemap_error, dont_filter=True)
        else:
            yield from self.parse_sitemap_xml(response)



    def parse_sitemap_xml(self, response: Response):
        if response.status != 200:
            yield SitemapInventoryItem(
                url=response.url,
                sitemap_url=response.url,
                lastmod=None,
                status="failed",
                reason=f"HTTP {response.status}"
            )
            return

        body = response.body
        # Handle Gzip compressed sitemaps
        if response.url.endswith(".gz") or body[:2] == b'\x1f\x8b':
            try:
                body = gzip.decompress(body)
            except Exception as e:
                logger.warning(f"Could not decompress gzip sitemap {response.url}: {e}")
                yield SitemapInventoryItem(
                    url=response.url,
                    sitemap_url=response.url,
                    lastmod=None,
                    status="failed",
                    reason=f"Gzip Decompress Error: {e}"
                )
                return

        try:
            root = ET.fromstring(body)
        except Exception as e:
            logger.debug(f"XML parse error for sitemap {response.url}: {e}")
            yield SitemapInventoryItem(
                url=response.url,
                sitemap_url=response.url,
                lastmod=None,
                status="failed",
                reason=f"XML Parse Error: {e}"
            )
            return

        yield SitemapInventoryItem(
            url=response.url,
            sitemap_url=response.url,
            lastmod=None,
            status="crawled",
            reason="Parsed sitemap XML"
        )

        # Handle XML namespaces
        tag = root.tag
        ns = ""
        if "}" in tag:
            ns = tag.split("}")[0] + "}"

        # 1. Sitemap Index (<sitemapindex>)
        if tag.endswith("sitemapindex"):
            for sm in root.findall(f"{ns}sitemap"):
                loc_el = sm.find(f"{ns}loc")
                if loc_el is not None and loc_el.text:
                    child_s_url = loc_el.text.strip()
                    yield SitemapInventoryItem(
                        url=child_s_url,
                        sitemap_url=response.url,
                        lastmod=None,
                        status="discovered",
                        reason="Child sitemap index"
                    )
                    yield Request(
                        url=child_s_url,
                        callback=self.parse_sitemap_xml,
                        errback=self.handle_sitemap_error,
                        dont_filter=True,
                        priority=100
                    )


        # 2. Urlset (<urlset>)
        elif tag.endswith("urlset"):
            for url_node in root.findall(f"{ns}url"):
                loc_el = url_node.find(f"{ns}loc")
                lastmod_el = url_node.find(f"{ns}lastmod")
                
                if loc_el is not None and loc_el.text:
                    page_url = normalize_url(loc_el.text.strip())
                    lastmod = lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else None

                    yield SitemapInventoryItem(
                        url=page_url,
                        sitemap_url=response.url,
                        lastmod=lastmod,
                        status="discovered",
                        reason="Sitemap URL"
                    )

                    norm_page = normalize_url(page_url)
                    existing_entry = self.url_inventory.get(norm_page)
                    existing_status = existing_entry.get("status") if existing_entry else None

                    # If already crawled, record duplicate discovery and do not re-process or skip
                    if existing_status == "crawled":
                        self.duplicate_discoveries += 1
                        continue

                    self.discovered_urls.add(page_url)
                    if self.pages_visited_count < self.max_pages and self.records_extracted_count < self.max_records:
                        if existing_status == "pending":
                            self.duplicate_discoveries += 1
                            continue
                        self.record_url_inventory(
                            url=page_url,
                            status="pending",
                            reason="sitemap_loc",
                            source_url=response.url,
                            discovery_method="sitemap",
                            attempt_count=0
                        )
                        yield Request(
                            url=page_url,
                            callback=self.parse_page,
                            errback=self.handle_error,
                            meta={'sitemap_source': response.url, 'lastmod': lastmod}
                        )
                    else:
                        limit_reason = "record_limit" if self.records_extracted_count >= self.max_records else "page_limit"
                        self.record_url_inventory(
                            url=page_url,
                            status="skipped",
                            reason=limit_reason,
                            source_url=response.url,
                            discovery_method="sitemap",
                            extraction_outcome="not_attempted"
                        )
                        if self.stop_reason == "queue_exhausted":
                            self.stop_reason = f"emergency_{limit_reason}_ceiling_reached" if self.mode == "auto" else f"bounded_{limit_reason}_reached"
                            self.crawl_complete = False


    def parse_page(self, response: Response):
        if not isinstance(response, TextResponse):
            logger.debug(f"Skipping non-text response at {response.url} (type: {type(response).__name__})")
            self.record_url_inventory(
                url=response.url,
                status="skipped",
                reason="non_html_asset",
                http_status=getattr(response, "status", None),
                content_type=getattr(response, "headers", {}).get(b"Content-Type", b"").decode("utf-8", "ignore") or None,
                attempt_count=1,
                extraction_outcome="not_applicable"
            )
            return

        norm_url = normalize_url(response.url)
        if norm_url in self.visited_page_urls:
            return

        if self.pages_visited_count >= self.max_pages:
            if self.stop_reason == "queue_exhausted":
                self.stop_reason = "emergency_page_ceiling_reached" if self.mode == "auto" else "bounded_page_limit_reached"
                self.crawl_complete = False
            self.record_url_inventory(
                url=norm_url,
                status="skipped",
                reason="page_limit",
                http_status=response.status,
                attempt_count=1,
                extraction_outcome="not_attempted"
            )
            return

        # Record redirect source URLs if request was redirected
        meta_dict = getattr(response, 'meta', {}) or {}
        redirect_urls = meta_dict.get('redirect_urls', [])
        for r_url in redirect_urls:
            norm_r = normalize_url(r_url)
            self.record_url_inventory(
                url=norm_r,
                status="skipped",
                reason="redirect",
                http_status=301,
                attempt_count=1,
                extraction_outcome="not_applicable",
                error_message=f"Redirected to {response.url}"
            )

        self.visited_page_urls.add(norm_url)
        self.pages_visited_count += 1
        page_url = response.url
        html_text = response.text

        # 1. Extract Page Item
        parser = PageParser(html_text, page_url)
        soup = parser.soup

        title = clean_text(soup.find("title").text) if soup.find("title") else ""
        canonical_tag = soup.find("link", rel="canonical")
        canonical_url = canonical_tag.get("href") if canonical_tag and canonical_tag.get("href") else page_url
        
        meta_desc_el = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        meta_description = meta_desc_el.get("content") if meta_desc_el and meta_desc_el.get("content") else ""

        meta_key_el = soup.find("meta", attrs={"name": "keywords"})
        meta_keywords = meta_key_el.get("content") if meta_key_el and meta_key_el.get("content") else ""

        headings = {f"h{i}": [clean_text(h.text) for h in soup.find_all(f"h{i}") if clean_text(h.text)] for i in range(1, 7)}
        
        # Extract full structured page content (Phase 19)
        content_res = parser.parse_page_content()
        extracted_paragraphs = content_res.get("paragraphs", [])
        extracted_lists = content_res.get("lists", [])
        extracted_tables = content_res.get("tables", [])
        extracted_main_text = content_res.get("main_text", "")
        breadcrumbs = content_res.get("breadcrumbs", [])

        if not extracted_paragraphs:
            raw_p = [clean_text(p.text) for p in soup.find_all("p") if clean_text(p.text)]
            legacy_paragraphs = raw_p[:15]
            legacy_main_text = " ".join(raw_p[:10])
        else:
            legacy_paragraphs = extracted_paragraphs
            legacy_main_text = extracted_main_text or " ".join(extracted_paragraphs[:10])

        # Downloadable files
        downloadable_files = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if any(href.lower().endswith(ext) for ext in DOC_EXTENSIONS):
                full_doc_url = urljoin(page_url, href)
                downloadable_files.append({
                    "url": full_doc_url,
                    "anchor_text": clean_text(a.text) or "",
                    "same_origin": is_same_origin(page_url, full_doc_url),
                    "file_type": href.split(".")[-1].lower()
                })

        # Images
        images_list = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                images_list.append({
                    "url": urljoin(page_url, src),
                    "alt": img.get("alt", ""),
                    "title": img.get("title", "")
                })

        # Page Classification
        page_type = self._classify_page(soup, page_url)

        meta_dict = getattr(response, 'meta', {}) or {}
        lastmod = meta_dict.get("lastmod")
        sitemap_source = meta_dict.get("sitemap_source")

        page_item = PageItem(
            page_url=page_url,
            canonical_url=canonical_url,
            title=title,
            meta_title=title,
            meta_description=meta_description,
            meta_keywords=meta_keywords,
            page_type=page_type,
            language=soup.html.get("lang") if soup.html else "en",
            author=None,
            publication_date=None,
            modified_date=lastmod,
            sitemap_source=sitemap_source,
            last_modified_from_sitemap=lastmod,
            http_status=response.status,
            headings=headings,
            main_text=legacy_main_text,
            paragraphs=legacy_paragraphs,
            lists=extracted_lists,
            tables=extracted_tables,
            breadcrumbs=breadcrumbs,
            categories=[],
            tags=[],
            images=images_list,
            downloadable_files=downloadable_files,
            extracted_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            page_content=content_res.get("page_content", {}),
            content_extraction=content_res.get("content_extraction", {})
        )

        # Determine content extraction outcome
        content_ext = content_res.get("content_extraction", {})
        c_status = content_ext.get("status")
        if c_status == "empty":
            ext_outcome = "empty"
        elif c_status == "suspiciously_short":
            ext_outcome = "suspiciously_short"
        else:
            ext_outcome = "extracted"

        content_type_hdr = response.headers.get(b'Content-Type', b'').decode('utf-8', errors='ignore') if hasattr(response, 'headers') else "text/html"
        depth_val = getattr(response, 'meta', {}).get('depth', 0) if hasattr(response, 'meta') else 0
        retries = meta_dict.get('retry_times', 0)
        inv_crawled = self.record_url_inventory(
            url=page_url,
            status="crawled",
            reason="success",
            http_status=response.status,
            content_type=content_type_hdr or "text/html",
            attempt_count=1 + retries,
            depth=depth_val,
            extraction_outcome=ext_outcome,
            page_extracted=True,
            product_records_extracted=0
        )

        yield page_item

        # 2. Extract Product Records via Existing Strategy Pipeline
        extracted_prods = []
        if self.records_extracted_count < self.max_records:
            records, strategy = parser.parse_records()
            extracted_prods = records
            for rec in records:
                if self.records_extracted_count < self.max_records:
                    self.records_extracted_count += 1
                    yield ProductItem(
                        title=rec.get("title"),
                        name=rec.get("title"),
                        description=rec.get("description"),
                        image_url=rec.get("image_url"),
                        image_urls=rec.get("image_urls", []),
                        product_url=rec.get("product_url"),
                        brand=rec.get("brand"),
                        sku=rec.get("sku"),
                        price=rec.get("price"),
                        currency=rec.get("currency"),
                        availability="InStock" if rec.get("price") else None,
                        specifications={},
                        catalogue_links=[],
                        source_url=page_url,
                        images=rec.get("images", []),
                        extracted_at=time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                else:
                    if self.stop_reason == "queue_exhausted":
                        self.stop_reason = "emergency_record_ceiling_reached" if self.mode == "auto" else "bounded_record_limit_reached"
                        self.crawl_complete = False
                    break
        else:
            if self.stop_reason == "queue_exhausted":
                self.stop_reason = "emergency_record_ceiling_reached" if self.mode == "auto" else "bounded_record_limit_reached"
                self.crawl_complete = False

        if norm_url in self.url_inventory:
            self.url_inventory[norm_url]["product_records_extracted"] = len(extracted_prods)

        # 3. Link discovery & inventory classification
        all_links = parser.discover_all_links()

        # Classify cross-origin links
        for co_link in all_links.get("cross_origin", []):
            norm_co = normalize_url(co_link)
            if norm_co in self.url_inventory:
                self.duplicate_discoveries += 1
            else:
                self.record_url_inventory(
                    url=norm_co,
                    status="skipped",
                    reason="cross_origin",
                    source_url=page_url,
                    discovery_method="html_link",
                    extraction_outcome="not_applicable"
                )

        # Classify internal links
        internal_links = all_links.get("internal", [])
        for link in internal_links:
            norm_link = normalize_url(link)
            if is_non_page_asset_url(norm_link):
                if norm_link in self.url_inventory:
                    self.duplicate_discoveries += 1
                else:
                    self.record_url_inventory(
                        url=norm_link,
                        status="skipped",
                        reason="non_html_asset",
                        source_url=page_url,
                        discovery_method="html_link",
                        extraction_outcome="not_applicable"
                    )
                continue

            if norm_link in self.url_inventory:
                self.duplicate_discoveries += 1
                continue

            if (self.pages_visited_count < self.max_pages 
                and self.records_extracted_count < self.max_records):
                self.record_url_inventory(
                    url=norm_link,
                    status="pending",
                    reason="html_link",
                    source_url=page_url,
                    discovery_method="html_link",
                    attempt_count=0
                )
                yield Request(
                    url=norm_link,
                    callback=self.parse_page,
                    errback=self.handle_error,
                    meta={'sitemap_source': None, 'lastmod': None}
                )
            else:
                limit_reason = "record_limit" if self.records_extracted_count >= self.max_records else "page_limit"
                self.record_url_inventory(
                    url=norm_link,
                    status="skipped",
                    reason=limit_reason,
                    source_url=page_url,
                    discovery_method="html_link",
                    extraction_outcome="not_attempted"
                )
                if self.stop_reason == "queue_exhausted":
                    self.stop_reason = f"emergency_{limit_reason}_ceiling_reached" if self.mode == "auto" else f"bounded_{limit_reason}_reached"
                    self.crawl_complete = False

    def _classify_page(self, soup, page_url: str) -> str:
        url_lower = page_url.lower()
        if "product" in url_lower or "item" in url_lower or soup.find(class_=re.compile(r"product", re.I)):
            return "product"
        elif "shop" in url_lower or "catalog" in url_lower or "category" in url_lower:
            return "product_listing"
        elif "article" in url_lower or "blog" in url_lower or "news" in url_lower:
            return "article"
        elif "service" in url_lower:
            return "service"
        return "static_page"

    def handle_error(self, failure):
        req_url = getattr(failure.request, "url", "unknown")
        err_msg = f"Request Error for {req_url}: {failure.value}"
        is_asset = is_non_page_asset_url(req_url)
        if is_asset:
            formatted_msg = f"[Asset Error] {err_msg}"
            self.asset_errors.append(formatted_msg)
            self.crawler_errors.append(formatted_msg)
        else:
            formatted_msg = f"[Page Error] {err_msg}"
            self.page_errors.append(formatted_msg)
            self.crawler_errors.append(formatted_msg)
        is_start = getattr(failure.request, "meta", {}).get("is_start_url", False)
        if is_start:
            self.root_url_failed = True
            self.stop_reason = "start_url_failed"
            self.crawl_complete = False
        elif self.stop_reason == "queue_exhausted":
            self.stop_reason = "download_error"
            self.crawl_complete = False

        # Record error in URL inventory
        http_status = None
        if hasattr(failure.value, "response") and failure.value.response is not None:
            http_status = failure.value.response.status

        err_type = type(failure.value).__name__
        err_msg_str = str(failure.value)
        reason = "http_error" if http_status else ("timeout" if ("timeout" in err_msg_str.lower() or "timeout" in err_type.lower()) else "connection_error")

        req_meta = getattr(getattr(failure, "request", None), "meta", {}) or {}
        attempt_cnt = 1 + req_meta.get("retry_times", 0)

        inv_err = self.record_url_inventory(
            url=req_url,
            status="failed",
            reason=reason,
            http_status=http_status,
            attempt_count=attempt_cnt,
            error_type=err_type,
            error_message=err_msg_str,
            extraction_outcome="not_available"
        )

    def handle_sitemap_error(self, failure):
        logger.debug(f"Sitemap candidate failed: {failure.value}")
        req_url = getattr(failure.request, "url", None)
        item = None
        if req_url:
            reason_str = str(failure.value)
            if hasattr(failure.value, "response") and failure.value.response is not None:
                reason_str = f"HTTP {failure.value.response.status}"
            item = SitemapInventoryItem(
                url=req_url,
                sitemap_url=req_url,
                lastmod=None,
                status="failed",
                reason=reason_str
            )
            self.sitemap_candidate_failures[req_url] = reason_str
            is_candidate = getattr(failure.request, "meta", {}).get("is_candidate_probe", False)
            if not is_candidate:
                self.sitemap_inventory[req_url] = item
        return [item] if item else []
