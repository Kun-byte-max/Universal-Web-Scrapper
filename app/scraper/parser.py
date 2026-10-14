import re
import logging
from typing import List, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from app.scraper.extractors import (
    StrategyStructuredMetadata,
    StrategyHTMLCards,
    StrategyGeneralPage
)
from app.scraper.safety import normalize_url, is_same_origin

logger = logging.getLogger(__name__)

PAGINATION_REGEX = re.compile(r"(page|\bpg\b|p=\d+|\bnext\b|category|catalog|shop|collection)", re.I)

class PageParser:
    """Unified HTML parser executing extraction pipeline strategies."""

    def __init__(self, html: str, page_url: str):
        self.html = html
        self.page_url = page_url
        try:
            self.soup = BeautifulSoup(html, "lxml")
        except Exception:
            self.soup = BeautifulSoup(html, "html.parser")

    def parse_records(self) -> Tuple[List[Dict[str, Any]], str]:
        """
        Execute strategy pipeline: A (Structured) -> B (HTML Cards) -> C (General Page)
        Returns tuple of (records, strategy_used).
        """
        # Strategy A: Structured Metadata
        records = StrategyStructuredMetadata.extract(self.soup, self.page_url)
        if records and len(records) > 0:
            return records, "Strategy A: Structured Metadata (JSON-LD / OG)"

        # Strategy B: HTML Product Cards
        records = StrategyHTMLCards.extract(self.soup, self.page_url)
        if records and len(records) > 0:
            return records, "Strategy B: HTML Product Cards"

        # Strategy C: General Page Extraction
        records = StrategyGeneralPage.extract(self.soup, self.page_url)
        if records and len(records) > 0:
            return records, "Strategy C: General Page Content"

        return [], "None"

    def parse_page_content(self, max_blocks: int = 5000, max_chars: int = 1000000) -> Dict[str, Any]:
        """
        Extract full structured page content according to Phase 19 schema.
        """
        from app.scraper.page_content import extract_page_content
        return extract_page_content(self.soup, self.page_url, max_blocks=max_blocks, max_chars=max_chars)

    def discover_links(self) -> List[str]:
        """
        Extract same-origin links for crawler navigation.
        Prioritizes pagination and category links.
        """
        discovered = []
        prioritized = []

        for a_tag in self.soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = normalize_url(href, base_url=self.page_url)
            if not is_same_origin(self.page_url, full_url):
                continue

            # Prioritize links matching pagination or category keywords
            if PAGINATION_REGEX.search(full_url) or PAGINATION_REGEX.search(a_tag.text):
                if full_url not in prioritized:
                    prioritized.append(full_url)
            else:
                if full_url not in discovered:
                    discovered.append(full_url)

        return prioritized + discovered

    def discover_all_links(self) -> Dict[str, List[str]]:
        """
        Extract and classify all discovered links on the page:
        - 'internal': same-origin candidate page links (prioritized)
        - 'cross_origin': foreign-origin URLs
        """
        internal = self.discover_links()
        cross_origin = []

        for a_tag in self.soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = normalize_url(href, base_url=self.page_url)
            if not is_same_origin(self.page_url, full_url):
                if full_url not in cross_origin:
                    cross_origin.append(full_url)

        return {
            "internal": internal,
            "cross_origin": cross_origin
        }
