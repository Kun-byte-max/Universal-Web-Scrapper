import scrapy

class PageItem(scrapy.Item):
    page_url = scrapy.Field()
    canonical_url = scrapy.Field()
    title = scrapy.Field()
    meta_title = scrapy.Field()
    meta_description = scrapy.Field()
    meta_keywords = scrapy.Field()
    page_type = scrapy.Field()
    language = scrapy.Field()
    author = scrapy.Field()
    publication_date = scrapy.Field()
    modified_date = scrapy.Field()
    sitemap_source = scrapy.Field()
    last_modified_from_sitemap = scrapy.Field()
    http_status = scrapy.Field()
    headings = scrapy.Field()          # Dict[str, List[str]] h1..h6
    main_text = scrapy.Field()
    paragraphs = scrapy.Field()
    lists = scrapy.Field()
    tables = scrapy.Field()
    breadcrumbs = scrapy.Field()
    categories = scrapy.Field()
    tags = scrapy.Field()
    images = scrapy.Field()             # List[Dict]
    downloadable_files = scrapy.Field() # List[Dict]
    extracted_at = scrapy.Field()
    page_content = scrapy.Field()
    content_extraction = scrapy.Field()

class ProductItem(scrapy.Item):
    title = scrapy.Field()
    name = scrapy.Field()
    description = scrapy.Field()
    image_url = scrapy.Field()
    image_urls = scrapy.Field()
    product_url = scrapy.Field()
    brand = scrapy.Field()
    sku = scrapy.Field()
    price = scrapy.Field()
    currency = scrapy.Field()
    availability = scrapy.Field()
    specifications = scrapy.Field()
    catalogue_links = scrapy.Field()
    source_url = scrapy.Field()
    images = scrapy.Field()
    extracted_at = scrapy.Field()

class SitemapInventoryItem(scrapy.Item):
    url = scrapy.Field()
    sitemap_url = scrapy.Field()
    lastmod = scrapy.Field()
    status = scrapy.Field() # "discovered", "crawled", "skipped", "failed"
    reason = scrapy.Field()

class UrlInventoryItem(scrapy.Item):
    url = scrapy.Field()
    source_url = scrapy.Field()
    discovery_method = scrapy.Field()  # "start_url", "sitemap", "html_link", "redirect"
    status = scrapy.Field()            # "discovered", "pending", "crawled", "failed", "skipped"
    reason = scrapy.Field()            # structured reason code
    http_status = scrapy.Field()       # int or None
    content_type = scrapy.Field()      # str or None
    attempt_count = scrapy.Field()     # int
    depth = scrapy.Field()             # int or None
    discovered_at = scrapy.Field()     # ISO timestamp or str
    completed_at = scrapy.Field()      # ISO timestamp or str
    extraction_outcome = scrapy.Field()# "not_attempted", "extracted", "empty", "suspiciously_short", "not_applicable", "not_available"
    page_extracted = scrapy.Field()    # bool
    product_records_extracted = scrapy.Field() # int
    error_type = scrapy.Field()        # str or None
    error_message = scrapy.Field()     # str or None

class ExtractionReportItem(scrapy.Item):
    target_url = scrapy.Field()
    sitemaps_discovered = scrapy.Field()
    pages_visited = scrapy.Field()
    products_extracted = scrapy.Field()
    files_discovered = scrapy.Field()
    duration_seconds = scrapy.Field()
    errors = scrapy.Field()
