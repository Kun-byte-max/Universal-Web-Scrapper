import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag, NavigableString

from app.scraper.extractors import clean_text, get_best_img_src
from app.scraper.safety import normalize_url

logger = logging.getLogger(__name__)

# Elements to strip or skip during content extraction
EXCLUDED_TAG_NAMES = {
    "script", "style", "noscript", "svg", "header", "footer", "nav", 
    "aside", "form", "button", "iframe", "dialog", "canvas", "template"
}

# Navigation chrome class and ID patterns
NAV_CHROME_CLASS_ID_REGEX = re.compile(
    r"(navbar|nav-menu|navigation|widget_nav_menu|mobile-menu|top-menu|main-menu|"
    r"site-menu|header-menu|primary-menu|secondary-menu|mega-menu|dropdown-menu|"
    r"drawer-menu|flyout-menu|offcanvas-menu|\bnav\b|nav[-_]container|nav[-_]wrapper)",
    re.I
)

# Page chrome & noise class and ID patterns (excluding navigation which is handled specifically)
NOISE_CLASS_ID_REGEX = re.compile(
    r"(cookie|banner|consent|site-header|site-footer|footer|social-share|share-buttons|popup|modal|copyright)",
    re.I
)

STANDALONE_SECTION_NAMES = {
    "features", "specifications", "specification", "overview", "gallery", 
    "contact", "contact us", "about", "about us", "faq", "faqs", "reviews", 
    "applications", "options", "accessories", "systems", "equipment"
}

def is_noise_or_chrome(tag: Tag, is_root: bool = False) -> bool:
    """Check if an element is part of page chrome, navigation, footer, or noise."""
    if not isinstance(tag, Tag):
        return False
    name = tag.name.lower()
    
    # Never discard an explicit main or article container
    if name in ("main", "article") or tag.get("role") == "main":
        return False

    classes = " ".join(tag.get("class", [])) if isinstance(tag.get("class"), list) else str(tag.get("class") or "")
    tag_id = str(tag.get("id") or "")
    combined = f"{classes} {tag_id}".lower()

    if name in EXCLUDED_TAG_NAMES and not is_root:
        # If an <aside> is specifically marked as product specifications or content, retain it
        if name == "aside" and re.search(r"(spec|product|detail|info)", combined):
            pass
        else:
            return True

    # Semantic ARIA navigation
    if tag.get("role") == "navigation":
        return True

    # Ancestor check: if tag is nested inside a <nav>, role="navigation", or navigation chrome container
    if tag.find_parent(lambda p: isinstance(p, Tag) and (
        p.name == "nav" or 
        p.get("role") == "navigation" or
        bool(NAV_CHROME_CLASS_ID_REGEX.search(
            " ".join(p.get("class", [])) if isinstance(p.get("class"), list) else str(p.get("class") or "")
        ))
    )):
        return True

    # Specific navigation chrome patterns (e.g. .navbar, .mobile-menu-wrapper, .top-menu-container)
    if NAV_CHROME_CLASS_ID_REGEX.search(combined):
        return True

    # General noise patterns (cookie banners, popups, footers, social share)
    if NOISE_CLASS_ID_REGEX.search(combined):
        return True

    # Sidebar handling: distinguish product/spec sidebars from generic layout/widget sidebars
    if re.search(r"\bsidebar\b", combined):
        # 1. Container class/id explicitly indicates specifications, product info, or content
        if re.search(r"(spec|product|detail|info|attribute|content|summary|desc)", combined):
            return False
        # 2. Structural evidence: container directly contains specification/product headings or tables
        if tag.find(lambda t: isinstance(t, Tag) and (
            (t.name in ("h1", "h2", "h3", "h4", "h5", "h6") and re.search(r"(spec|specification|product|technical|dimension)", t.text, re.I)) or
            t.name == "table"
        )):
            return False
        # Otherwise, generic blog/widget sidebar is excluded
        return True

    return False


def extract_breadcrumbs(soup: BeautifulSoup, page_url: str = "") -> List[str]:
    """
    Extract breadcrumbs from breadcrumb navigation or BreadcrumbList schema.
    Returns ordered list of breadcrumb label strings.
    """
    breadcrumbs: List[str] = []

    # 1. Look for semantic breadcrumb container
    candidates = soup.find_all(
        lambda t: isinstance(t, Tag) and (
            t.get("aria-label", "").lower() == "breadcrumb" or
            any("breadcrumb" in c.lower() for c in (t.get("class") if isinstance(t.get("class"), list) else [str(t.get("class") or "")])) or
            "breadcrumb" in str(t.get("id") or "").lower()
        )
    )

    for bc_container in candidates:
        # Avoid huge containers that merely mention breadcrumb somewhere deep
        items = []
        for el in bc_container.find_all(["li", "a", "span"]):
            # Skip if this element has child li/a/span to avoid duplicate parent/child text
            if el.find(["li", "a", "span"]):
                continue
            text = clean_text(el.text)
            if not text:
                continue
            # Filter out breadcrumb separators
            if text in (">", "/", "»", "&gt;", "&raquo;", "•", "|", "→", "-"):
                continue
            if text not in items:
                items.append(text)
        if len(items) >= 2:
            return items
        if items and not breadcrumbs:
            breadcrumbs = items

    if breadcrumbs:
        return breadcrumbs

    # 2. Check JSON-LD BreadcrumbList
    for script in soup.find_all("script", type=re.compile(r"application/ld\+json", re.I)):
        if not script.string:
            continue
        try:
            import json
            data = json.loads(script.string.strip())
            items = _parse_jsonld_breadcrumbs(data)
            if items:
                return items
        except Exception:
            continue

    return []


def _parse_jsonld_breadcrumbs(data: Any) -> List[str]:
    """Parse breadcrumb items from schema.org JSON-LD."""
    if isinstance(data, list):
        for item in data:
            res = _parse_jsonld_breadcrumbs(item)
            if res:
                return res
    elif isinstance(data, dict):
        if data.get("@type") == "BreadcrumbList":
            elements = data.get("itemListElement", [])
            items = []
            for el in sorted(elements, key=lambda x: x.get("position", 0) if isinstance(x, dict) else 0):
                if isinstance(el, dict):
                    name = el.get("name") or (el.get("item", {}).get("name") if isinstance(el.get("item"), dict) else None)
                    if name:
                        items.append(clean_text(str(name)))
            if items:
                return items
        if "@graph" in data:
            return _parse_jsonld_breadcrumbs(data["@graph"])
    return []


def find_main_content_container(soup: BeautifulSoup) -> Tag:
    """Find the best main article/content container in the document."""
    for selector in ["main", "article", '[role="main"]', "#main-content", "#content", ".entry-content", ".post-content", ".page-content", ".post-formatting", "#main-wrapper"]:
        found = soup.select_one(selector)
        if found:
            return found
    return soup.body or soup


def is_paragraph_prose(text: str) -> bool:
    """
    Check if a text string is prose rather than a concise section heading.
    Detects headings hijacked by visual CMS editors to style paragraphs.
    """
    if not text:
        return False
    cleaned = text.strip()
    if len(cleaned) > 110:
        return True
    if len(cleaned) >= 45 and cleaned.endswith((".", "!", "?")):
        return True
    # Two or more complete sentences ending in period/exclamation/question
    sentence_endings = len(re.findall(r'[.!?]\s+[A-Z0-9]', cleaned))
    if sentence_endings >= 1 and len(cleaned) > 60:
        return True
    return False


def extract_image_block(img_tag: Tag, page_url: str) -> Optional[Dict[str, Any]]:
    """
    Extract an image block preserving image_url, title, alt, and reliable caption.
    Does not invent captions from filenames.
    """
    if not isinstance(img_tag, Tag):
        return None

    src = get_best_img_src(img_tag, page_url)
    if not src:
        return None

    alt = clean_text(img_tag.get("alt"))
    title = clean_text(img_tag.get("title"))

    # Caption extraction from reliable DOM relationships only
    caption = None
    fig = img_tag.find_parent("figure")
    if fig:
        figcaption = fig.find("figcaption")
        if figcaption:
            caption = clean_text(figcaption.text)

    if not caption:
        # Check immediate sibling or enclosing caption/label container
        parent = img_tag.parent
        if parent:
            cap_el = parent.find(class_=re.compile(r"(caption|label|image-title)", re.I))
            if cap_el and cap_el != img_tag and not cap_el.find("img"):
                cand = clean_text(cap_el.text)
                if cand and len(cand) <= 200:
                    caption = cand

    if not caption:
        # Next immediate sibling if it is a caption or small text
        next_sib = img_tag.find_next_sibling()
        if next_sib and next_sib.name in ("figcaption", "small", "span", "p"):
            classes = " ".join(next_sib.get("class", [])) if isinstance(next_sib.get("class"), list) else str(next_sib.get("class") or "")
            if re.search(r"(caption|label|desc)", classes, re.I) or next_sib.name in ("figcaption", "small"):
                cand = clean_text(next_sib.text)
                if cand and len(cand) <= 200:
                    caption = cand

    return {
        "type": "image",
        "image_url": src,
        "title": title,
        "alt": alt,
        "caption": caption
    }


def extract_table_block(table_tag: Tag) -> Optional[Dict[str, Any]]:
    """Extract structured headers and rows from a table element."""
    headers = []
    rows = []

    # 1. Headers from <thead> or first <tr> with <th>
    th_tags = table_tag.find_all("th")
    if th_tags:
        for th in th_tags:
            h_text = clean_text(th.text)
            headers.append(h_text or "")

    # 2. Rows from <tbody> or <tr>
    for tr in table_tag.find_all("tr"):
        # If this row is all <th> and headers already captured, skip
        row_ths = tr.find_all("th")
        row_tds = tr.find_all("td")
        if row_ths and not row_tds:
            if not headers:
                headers = [clean_text(th.text) or "" for th in row_ths]
            continue

        if row_tds:
            row_vals = [clean_text(td.text) or "" for td in row_tds]
            if any(row_vals):
                rows.append(row_vals)

    if not headers and not rows:
        return None

    return {
        "type": "table",
        "headers": headers,
        "rows": rows
    }


def extract_list_block(list_tag: Tag) -> Optional[Dict[str, Any]]:
    """Extract structured ordered/unordered list block."""
    ordered = list_tag.name.lower() == "ol"
    items = []
    for li in list_tag.find_all("li", recursive=False):
        text = clean_text(li.text)
        if text:
            items.append(text)

    # If no direct li children found, search all nested li
    if not items:
        for li in list_tag.find_all("li"):
            text = clean_text(li.text)
            if text and text not in items:
                items.append(text)

    if not items:
        return None

    return {
        "type": "list",
        "ordered": ordered,
        "items": items
    }


class PageContentExtractor:
    """
    Traverses HTML in preorder reading order, extracting typed content blocks
    and assembling a hierarchical section tree.
    """

    def __init__(self, soup: BeautifulSoup, page_url: str, max_blocks: int = 5000, max_chars: int = 1000000):
        self.soup = soup
        self.page_url = page_url
        self.max_blocks = max_blocks
        self.max_chars = max_chars

        self.warnings: List[str] = []
        self.complete: bool = True
        self.status: str = "complete"
        self.block_count: int = 0
        self.char_count: int = 0

        self.processed_tags: Set[int] = set()

    def extract(self) -> Dict[str, Any]:
        """Main extraction pipeline."""
        # 1. Page title
        title_tag = self.soup.find("title")
        doc_title = clean_text(title_tag.text) if title_tag else ""
        h1_tag = self.soup.find("h1")
        h1_title = clean_text(h1_tag.text) if h1_tag else ""
        primary_title = h1_title or doc_title or ""

        # 2. Breadcrumbs
        breadcrumbs = extract_breadcrumbs(self.soup, self.page_url)

        # 3. Content scoping
        main_container = find_main_content_container(self.soup)

        # 4. Traverse content blocks and headings in reading order
        stream = list(self._walk_container(main_container))

        # 5. Build hierarchical section tree from stream
        sections = self._build_section_tree(stream, primary_title)

        # 6. Reconstruct full text
        full_text = self._reconstruct_full_text(sections)

        # Legacy convenience lists
        all_paragraphs = self._collect_blocks_of_type(sections, "paragraph")
        paragraph_texts = [b["text"] for b in all_paragraphs if b.get("text")]
        
        all_list_blocks = self._collect_blocks_of_type(sections, "list")
        list_records = [b.get("items", []) for b in all_list_blocks]

        all_table_blocks = self._collect_blocks_of_type(sections, "table")

        main_text_snippet = "\n\n".join(paragraph_texts[:10]) if paragraph_texts else (full_text[:500] if full_text else "")

        # 7. Evaluate content completeness and emit conservative warnings
        # Note on static HTML limitations: complete=True indicates that DOM traversal succeeded
        # without safety-limit truncation and extracted meaningful content blocks from the HTML response.
        # It does not guarantee recovery of JavaScript-rendered client-side elements, as static HTML
        # extraction cannot execute client scripts or inspect dynamically hydrated DOM state.
        if self.status == "limit_exceeded" or not self.complete:
            self.complete = False
            self.status = "limit_exceeded"
        elif self.block_count == 0:
            self.complete = False
            if primary_title:
                self.status = "suspiciously_short"
                self.warnings.append(
                    f"Extracted content is suspiciously short; page title was found ('{primary_title}') "
                    f"but 0 body content blocks (paragraphs, lists, tables, or images) were recovered. "
                    f"The page may be an empty placeholder or require JavaScript rendering to display content."
                )
            else:
                self.status = "empty"
                self.warnings.append(
                    "Extracted content is empty; no body text or content blocks were recovered "
                    "from the static HTML response."
                )
        else:
            self.complete = True
            self.status = "complete"

        return {
            "page_title": primary_title,
            "breadcrumbs": breadcrumbs,
            "page_content": {
                "title": primary_title,
                "sections": sections,
                "full_text": full_text
            },
            "content_extraction": {
                "method": "html_dom",
                "complete": self.complete,
                "status": self.status,
                "warnings": self.warnings
            },
            # Legacy fields helper output
            "paragraphs": paragraph_texts,
            "lists": list_records,
            "tables": all_table_blocks,
            "main_text": main_text_snippet
        }

    def _walk_container(self, container: Tag):
        """Walk container recursively in document reading order yielding blocks or headings."""
        for child in container.children:
            if not isinstance(child, Tag):
                # Standalone text string inside container
                text = clean_text(str(child))
                if text and len(text) >= 20 and not is_noise_or_chrome(container):
                    yield ("block", {"type": "paragraph", "text": text})
                continue

            if id(child) in self.processed_tags:
                continue

            # Skip noise and chrome
            if is_noise_or_chrome(child):
                continue

            tag_name = child.name.lower()

            # Headings
            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.processed_tags.add(id(child))
                h_text = clean_text(child.text)
                if not h_text:
                    continue
                level = int(tag_name[1])

                # Disambiguate CMS prose wrapped in heading tags
                if is_paragraph_prose(h_text):
                    yield ("block", {"type": "paragraph", "text": h_text})
                else:
                    yield ("heading", {"text": h_text, "level": level, "tag": child})

            # Paragraphs
            elif tag_name == "p":
                self.processed_tags.add(id(child))
                # Check if paragraph wraps an image
                img_inside = child.find("img")
                if img_inside:
                    img_block = extract_image_block(img_inside, self.page_url)
                    if img_block:
                        yield ("block", img_block)
                    # Text inside paragraph besides image
                    p_text = clean_text("".join([s for s in child.strings if s not in img_inside.strings]))
                    if p_text and len(p_text) >= 2:
                        yield ("block", {"type": "paragraph", "text": p_text})
                else:
                    p_text = clean_text(child.text)
                    if p_text:
                        yield ("block", {"type": "paragraph", "text": p_text})

            # Lists
            elif tag_name in ("ul", "ol"):
                self.processed_tags.add(id(child))
                list_block = extract_list_block(child)
                if list_block:
                    yield ("block", list_block)

            # Tables
            elif tag_name == "table":
                self.processed_tags.add(id(child))
                table_block = extract_table_block(child)
                if table_block:
                    yield ("block", table_block)

            # Figures
            elif tag_name == "figure":
                self.processed_tags.add(id(child))
                img_inside = child.find("img")
                if img_inside:
                    img_block = extract_image_block(img_inside, self.page_url)
                    if img_block:
                        yield ("block", img_block)

            # Standalone Images
            elif tag_name == "img":
                self.processed_tags.add(id(child))
                img_block = extract_image_block(child, self.page_url)
                if img_block:
                    yield ("block", img_block)

            # Blockquotes
            elif tag_name == "blockquote":
                self.processed_tags.add(id(child))
                q_text = clean_text(child.text)
                if q_text:
                    yield ("block", {"type": "quote", "text": q_text})

            # Code
            elif tag_name in ("pre", "code"):
                self.processed_tags.add(id(child))
                c_text = child.text.strip()
                if c_text:
                    yield ("block", {"type": "code", "text": c_text, "language": None})

            # Links and Downloadable Assets
            elif tag_name == "a":
                self.processed_tags.add(id(child))
                img_inside = child.find("img")
                if img_inside:
                    img_block = extract_image_block(img_inside, self.page_url)
                    if img_block:
                        yield ("block", img_block)
                a_text = clean_text("".join([s for s in child.strings if not img_inside or s not in img_inside.strings]))
                href = child.get("href", "").strip()
                if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    full_url = urljoin(self.page_url, href)
                    is_asset = any(full_url.lower().split("?")[0].endswith(ext) for ext in (
                        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip", ".rar", ".csv", ".tar", ".gz"
                    ))
                    if a_text or is_asset:
                        yield ("block", {
                            "type": "link",
                            "text": a_text or href,
                            "url": full_url,
                            "is_asset": is_asset
                        })
                elif a_text and len(a_text) >= 2:
                    yield ("block", {"type": "paragraph", "text": a_text})

            # Recursive traversal for general containers (div, section, article, span, etc.)
            else:
                yield from self._walk_container(child)

    def _build_section_tree(self, stream: List[Tuple[str, Dict[str, Any]]], doc_title: str) -> List[Dict[str, Any]]:
        """
        Assemble hierarchical section tree from linear stream of headings and blocks.
        Preserves reading order, subtitles, and parent-child section relationships.
        """
        sections: List[Dict[str, Any]] = []
        # Section stack: list of active section dictionaries
        section_stack: List[Dict[str, Any]] = []

        def get_current_section() -> Dict[str, Any]:
            if not section_stack:
                # Default root introductory section
                root_sec = {
                    "heading": None,
                    "level": None,
                    "subtitle": None,
                    "blocks": [],
                    "subsections": []
                }
                sections.append(root_sec)
                section_stack.append(root_sec)
            return section_stack[-1]

        def add_block_with_limits(block: Dict[str, Any]):
            if self.block_count >= self.max_blocks:
                if not any("maximum content blocks" in w for w in self.warnings):
                    self.warnings.append(f"Configured safety limit reached: maximum {self.max_blocks} content blocks per page exceeded.")
                    self.complete = False
                    self.status = "limit_exceeded"
                return

            # Char count limit check
            block_chars = len(str(block.get("text") or "")) + len(str(block.get("items") or ""))
            if self.char_count + block_chars > self.max_chars:
                if not any("maximum characters" in w for w in self.warnings):
                    self.warnings.append(f"Configured safety limit reached: maximum {self.max_chars} characters per page exceeded.")
                    self.complete = False
                    self.status = "limit_exceeded"
                return

            self.block_count += 1
            self.char_count += block_chars
            current_sec = get_current_section()
            current_sec["blocks"].append(block)

        idx = 0
        while idx < len(stream):
            item_type, data = stream[idx]

            if item_type == "block":
                add_block_with_limits(data)
                idx += 1
                continue

            if item_type == "heading":
                h_text = data["text"]
                level = data["level"]

                # If stack currently has a title-only section (e.g. h1 matching doc_title with no content blocks):
                # Remove it so actual content sections start at top level
                if section_stack and section_stack[-1]["heading"] == doc_title and len(section_stack[-1]["blocks"]) == 0:
                    title_sec = section_stack.pop()
                    if title_sec in sections:
                        sections.remove(title_sec)

                # If stack currently has a root preamble section (level is None):
                # Pop it so real heading starts at top level in sections
                if section_stack and section_stack[-1]["level"] is None:
                    section_stack.pop()

                # Subtitle detection:
                # If current active section has a heading, no subtitle yet, no blocks or subsections yet,
                # and this heading is deeper level (or matches subtitle indicators), attach as subtitle!
                if section_stack and section_stack[-1]["heading"] is not None:
                    curr = section_stack[-1]
                    is_subtitle_candidate = (
                        curr["subtitle"] is None and
                        len(curr["blocks"]) == 0 and
                        len(curr["subsections"]) == 0 and
                        level > (curr["level"] or 0) and
                        len(h_text) <= 150 and
                        h_text.lower() not in STANDALONE_SECTION_NAMES
                    )
                    if is_subtitle_candidate:
                        curr["subtitle"] = h_text
                        idx += 1
                        continue

                # Normal heading -> create new section
                new_sec = {
                    "heading": h_text,
                    "level": level,
                    "subtitle": None,
                    "blocks": [],
                    "subsections": []
                }

                # If stack contains an empty root section (no blocks, no subsections), replace it
                if section_stack and section_stack[0]["heading"] is None and len(section_stack[0]["blocks"]) == 0 and len(section_stack[0]["subsections"]) == 0:
                    sections.remove(section_stack[0])
                    section_stack.pop(0)

                # Pop sections with level >= current heading level (sibling or higher scope)
                while section_stack and section_stack[-1]["level"] is not None and section_stack[-1]["level"] >= level:
                    section_stack.pop()

                # Sibling section handling for CMS visual editor misuse:
                # If the active parent section is an introductory section that already has content blocks,
                # or if the new heading is a major standalone section (Features, Systems, Equipment, Specifications),
                # do not nest the new heading as a subordinate subsection of the introduction.
                if section_stack and section_stack[-1]["heading"]:
                    parent_h = (section_stack[-1]["heading"] or "").lower()
                    is_parent_intro = bool(re.search(r"^(an\s+)?(introduction|intro|overview)\b", parent_h))
                    is_new_standalone = (
                        h_text.lower() in STANDALONE_SECTION_NAMES or
                        any(s in h_text.lower() for s in ["features", "main systems", "specifications", "equipment"])
                    )
                    if (is_parent_intro and len(section_stack[-1]["blocks"]) > 0) or is_new_standalone:
                        while section_stack and (
                            bool(re.search(r"^(an\s+)?(introduction|intro|overview)\b", (section_stack[-1]["heading"] or "").lower())) or
                            (is_new_standalone and section_stack[-1]["level"] is not None)
                        ):
                            section_stack.pop()

                if not section_stack:
                    # Top-level section
                    sections.append(new_sec)
                    section_stack.append(new_sec)
                else:
                    # Nested subsection under parent section
                    section_stack[-1]["subsections"].append(new_sec)
                    section_stack.append(new_sec)

                idx += 1

        # Clean empty root sections with no heading, no blocks, and no subsections
        cleaned_sections = []
        for s in sections:
            if s["heading"] is None and not s["blocks"] and not s["subsections"]:
                continue
            cleaned_sections.append(s)

        return cleaned_sections

    def _collect_blocks_of_type(self, sections: List[Dict[str, Any]], block_type: str) -> List[Dict[str, Any]]:
        """Collect all blocks of a specific type recursively from section tree."""
        collected = []
        for sec in sections:
            for b in sec.get("blocks", []):
                if b.get("type") == block_type:
                    collected.append(b)
            if sec.get("subsections"):
                collected.extend(self._collect_blocks_of_type(sec["subsections"], block_type))
        return collected

    def _reconstruct_full_text(self, sections: List[Dict[str, Any]]) -> str:
        """Reconstruct clean full text in reading order from section hierarchy."""
        parts: List[str] = []

        def visit_section(sec: Dict[str, Any]):
            if sec.get("heading"):
                parts.append(sec["heading"])
            if sec.get("subtitle"):
                parts.append(sec["subtitle"])

            for block in sec.get("blocks", []):
                b_type = block.get("type")
                if b_type == "paragraph":
                    parts.append(block.get("text", ""))
                elif b_type == "list":
                    items = block.get("items", [])
                    if items:
                        parts.append("\n".join(f"- {it}" for it in items))
                elif b_type == "table":
                    t_headers = block.get("headers", [])
                    t_rows = block.get("rows", [])
                    t_lines = []
                    if t_headers:
                        t_lines.append(" | ".join(t_headers))
                    for row in t_rows:
                        t_lines.append(" | ".join(row))
                    if t_lines:
                        parts.append("\n".join(t_lines))
                elif b_type == "quote":
                    parts.append(f"> {block.get('text', '')}")
                elif b_type == "code":
                    parts.append(block.get("text", ""))
                elif b_type == "image":
                    cap = block.get("caption") or block.get("title") or block.get("alt")
                    if cap:
                        parts.append(f"[Image: {cap}]")
                elif b_type in ("link", "other"):
                    parts.append(block.get("text", ""))

            for subsec in sec.get("subsections", []):
                visit_section(subsec)

        for s in sections:
            visit_section(s)

        return "\n\n".join(p for p in parts if p.strip())


def extract_page_content(soup: BeautifulSoup, page_url: str, max_blocks: int = 5000, max_chars: int = 1000000) -> Dict[str, Any]:
    """Convenience functional interface for PageContentExtractor."""
    extractor = PageContentExtractor(soup, page_url, max_blocks=max_blocks, max_chars=max_chars)
    return extractor.extract()
