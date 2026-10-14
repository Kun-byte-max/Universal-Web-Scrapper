import json
from urllib.parse import urlparse
from app.scraper.scrapy_engine.spiders.universal_spider import is_non_page_asset_url

# We can inspect the discovered links by parsing the visited pages
pages = json.load(open('output/168b1b31-ea3a-47a7-8f84-8cee92c2aa96/website_pages.json', encoding='utf-8'))
visited_urls = {p['page_url'] for p in pages}

from app.scraper.parser import PageParser

all_discovered = set()
for p in pages:
    parser = PageParser(p.get('main_text', ''), p['page_url'])
    # reconstruct discover_links using the page html or links
    # Actually let's check PageItem downloadable_files and images
    pass

print(f"Total visited HTML pages: {len(visited_urls)}")
