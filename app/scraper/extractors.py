import json
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

Tuple_Price = Tuple[Optional[Any], Optional[str]]

def clean_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned if cleaned else None

def parse_price(price_str: Optional[str]) -> Tuple_Price:
    """Parse price string into float/str price and currency symbol/code."""
    if not price_str:
        return None, None

    
    price_str = str(price_str).strip()
    
    # Currency symbols & patterns
    currency_map = {
        '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '₹': 'INR', 'CA$': 'CAD', 'AU$': 'AUD'
    }
    
    found_currency = None
    for symbol, code in currency_map.items():
        if symbol in price_str:
            found_currency = code
            break
            
    if not found_currency:
        curr_match = re.search(r'([A-Z]{3})', price_str)
        if curr_match:
            found_currency = curr_match.group(1)

    # Extract clean numeric value
    num_match = re.search(r'[\d,]+(?:\.\d{1,2})?', price_str)
    if num_match:
        val_str = num_match.group(0).replace(',', '')
        try:
            val_float = float(val_str)
            return val_float, found_currency
        except ValueError:
            return val_str, found_currency

    return price_str, found_currency

Tuple_Price = tuple[Optional[Any], Optional[str]]

def parse_srcset(srcset: str, base_url: str) -> List[str]:
    """Parse srcset attribute and return candidate image URLs in order."""
    candidates = []
    if not srcset:
        return candidates
        
    parts = srcset.split(',')
    for part in parts:
        tokens = part.strip().split()
        if tokens:
            img_url = urljoin(base_url, tokens[0])
            candidates.append(img_url)
    return candidates

def get_best_img_src(img_tag: Tag, base_url: str) -> Optional[str]:
    """Extract best image source considering lazy loading and srcset attributes."""
    if not isinstance(img_tag, Tag):
        return None
        
    # Check lazy load attributes first
    for attr in ["data-src", "data-lazy-src", "data-original", "data-high-res-src", "data-srcset"]:
        val = img_tag.get(attr)
        if val:
            if "," in str(val):
                candidates = parse_srcset(str(val), base_url)
                if candidates:
                    return candidates[-1]
            return urljoin(base_url, str(val))
            
    # Check standard srcset
    srcset = img_tag.get("srcset")
    if srcset:
        candidates = parse_srcset(str(srcset), base_url)
        if candidates:
            return candidates[-1]
            
    # Fallback standard src
    src = img_tag.get("src")
    if src and not str(src).startswith("data:"):
        return urljoin(base_url, str(src))
        
def extract_rich_image_metadata(img_tag: Tag, base_url: str, container_soup: Optional[Tag] = None) -> Optional[Dict[str, Any]]:
    """Extract rich image-level metadata including image_url, title, alt, caption, and section_title."""
    if not isinstance(img_tag, Tag):
        return None

    src = get_best_img_src(img_tag, base_url)
    if not src:
        return None

    alt = clean_text(img_tag.get("alt"))
    img_title = clean_text(img_tag.get("title"))

    # Caption extraction (figcaption or .caption element)
    caption = None
    fig = img_tag.find_parent("figure")
    if fig:
        figcaption = fig.find("figcaption")
        if figcaption:
            caption = clean_text(figcaption.text)

    if not caption:
        parent = img_tag.parent
        if parent:
            cap_el = parent.find(class_=re.compile(r"(caption|label|title)", re.I))
            if cap_el and cap_el != img_tag:
                caption = clean_text(cap_el.text)

    # Title association:
    # 1. explicit caption
    # 2. img_title
    resolved_title = caption or img_title

    # 3. Parent card heading (h3..h6)
    if not resolved_title:
        parent = img_tag.parent
        if parent:
            card_h = parent.find(["h3", "h4", "h5", "h6"])
            if card_h:
                resolved_title = clean_text(card_h.text)

    # 4. Enclosing link title
    if not resolved_title:
        parent_a = img_tag.find_parent("a")
        if parent_a and parent_a.get("title"):
            resolved_title = clean_text(parent_a.get("title"))

    # 5. Visible label inside immediate widget/card container (e.g. p > strong, card label)
    if not resolved_title:
        curr = img_tag
        for _ in range(4):
            curr = curr.parent
            if not curr or curr.name in ["body", "html", "[document]", "main", "article"]:
                break

            # Previous sibling widget/element within the same container
            prev_sib = curr.find_previous_sibling()
            if prev_sib:
                text_el = prev_sib.find(["strong", "b", "h4", "h5", "h6"]) or prev_sib.find("p")
                if text_el:
                    cand = clean_text(text_el.text)
                    if cand and 2 <= len(cand) <= 120 and not prev_sib.find_all("img"):
                        resolved_title = cand
                        break

            # Enclosing card/cell containing exactly 1 image
            classes = " ".join(curr.get("class", []))
            if any(k in classes for k in ["cell", "card", "item", "widget", "col"]) and not any(k in classes for k in ["grid", "row", "layout"]):
                if len(curr.find_all("img")) == 1:
                    text_el = curr.find(["strong", "b", "h4", "h5", "h6"]) or curr.find("p")
                    if text_el:
                        cand = clean_text(text_el.text)
                        if cand and 2 <= len(cand) <= 120:
                            resolved_title = cand
                            break

    # 6. Fallback to alt attribute
    if not resolved_title:
        resolved_title = alt

    # Section title association: nearest preceding section heading (h1..h3) outside the image's own card
    section_title = None
    parent_card = img_tag.find_parent(class_=re.compile(r"(card|widget_sow-image|sow-image|product-item)", re.I)) or img_tag.find_parent("figure")
    all_prev = img_tag.find_all_previous(["h1", "h2", "h3"])
    for h in all_prev:
        # Ignore a heading if it is inside the image's immediate card/figure (which represents the item title, not the section)
        if parent_card and (h in parent_card.descendants or h == parent_card):
            continue
        h_text = clean_text(h.text)
        if h_text:
            section_title = h_text
            break

    return {
        "image_url": src,
        "title": resolved_title,
        "alt": alt,
        "caption": caption,
        "section_title": section_title,
        "source_page_url": base_url
    }

GENERIC_TITLES = [
    "contact", "contact us", "about us", "privacy policy", "terms & conditions", "terms of service", "quality control",
    "home", "homepage", "services", "our services", "quotes to scrape", "top ten tags", "login", "authors", "tags",
    "company profile"
]

def is_generic_title(title: Optional[str]) -> bool:
    """Check if a candidate title matches known generic page, layout, or navigation headings."""
    if not title:
        return True
    t_clean = clean_text(title)
    if not t_clean or len(t_clean) < 2:
        return True
    t_lower = t_clean.lower()
    for gt in GENERIC_TITLES:
        if gt == t_lower:
            return True
        if gt in ("quotes to scrape", "top ten tags") and gt in t_lower:
            return True
        if gt == "home":
            if (
                t_lower.startswith(("home -", "home –", "home —", "home |", "home :", "home-", "home–", "home|", "home:", "home page"))
                or t_lower.endswith((" home", "-home", "–home", "|home"))
            ):
                return True
        elif gt == "contact":
            if (
                t_lower in ("contact", "contact us", "contact our team", "contact details", "contact info", "contact information")
                or t_lower.startswith(("contact -", "contact –", "contact —", "contact |", "contact :", "contact us -", "contact us –", "contact us |"))
                or t_lower.endswith((" contact", "-contact", "–contact", "|contact", ":contact", " contact us", "-contact us", "–contact us", "|contact us"))
            ):
                return True
        elif gt == "company profile":
            if (
                t_lower in ("company profile", "our company profile", "company-profile")
                or t_lower.startswith(("company profile -", "company profile –", "company profile —", "company profile |", "company profile :"))
                or t_lower.endswith((" company profile", "-company profile", "–company profile", "|company profile"))
            ):
                return True
        else:
            if (
                t_lower.startswith((f"{gt} ", f"{gt}-", f"{gt}–", f"{gt}:", f"{gt}|"))
                or t_lower.endswith((f" {gt}", f"-{gt}", f"–{gt}", f"|{gt}"))
            ):
                return True
    return False

BOILERPLATE_DESCRIPTION_PATTERNS = [
    # 1. Copyright, rights, and authorship boilerplate
    re.compile(r"(?:^|[|\-•·\s])(?:©|&copy;|copyright|\(c\))\s*(?:\d{4})?", re.I),
    re.compile(r"\ball\s+rights\s+reserved\b", re.I),
    re.compile(r"\bpowered\s+by\b", re.I),
    re.compile(r"\bdesigned\s+by\b", re.I),
    re.compile(r"\bdeveloped\s+by\b", re.I),

    # 2. Cookie consent & privacy banner boilerplate
    re.compile(r"\b(?:we\s+use|this\s+website\s+uses|this\s+site\s+uses)\s+cookies\b", re.I),
    re.compile(r"\b(?:accept|decline|manage|customize)\s+(?:all\s+)?cookies\b", re.I),
    re.compile(r"\bcookie\s+(?:policy|settings|preferences|consent)\b", re.I),

    # 3. Navigation, skip links & layout chrome
    re.compile(r"\bskip\s+to\s+(?:content|main|navigation)\b", re.I),
    re.compile(r"\b(?:toggle|open|close)\s+navigation\b", re.I),
    re.compile(r"^\s*(?:home|about\s+us|contact\s+us|menu|navigation)\s*$", re.I),
    re.compile(r"^\s*(?:privacy\s+policy|terms\s+(?:of\s+(?:use|service)|&\s*conditions))\s*$", re.I),
]

def is_valid_description(text: Optional[str], min_length: int = 15) -> bool:
    """
    Validate that candidate description is meaningful product/article prose 
    and not copyright boilerplate, cookie consent, or navigation chrome.
    """
    if not text:
        return False
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) < min_length:
        return False

    for pattern in BOILERPLATE_DESCRIPTION_PATTERNS:
        if pattern.search(cleaned):
            return False

    return True

class StrategyStructuredMetadata:
    """Strategy A: Extracts records from JSON-LD, Microdata, and OpenGraph meta tags."""

    @staticmethod
    def extract(soup: BeautifulSoup, page_url: str) -> List[Dict[str, Any]]:
        records = []
        
        # 1. Process JSON-LD script tags
        json_ld_scripts = soup.find_all("script", type=re.compile(r"application/ld\+json", re.I))
        for script in json_ld_scripts:
            if not script.string:
                continue
            try:
                # Basic sanitation for common syntax mistakes in json-ld
                raw_json = script.string.strip()
                data = json.loads(raw_json)
                extracted = StrategyStructuredMetadata._process_json_ld_item(data, page_url)
                records.extend(extracted)
            except Exception:
                # Try soft clean if standard JSON parse failed
                try:
                    cleaned_json = re.sub(r',\s*([}\]])', r'\1', script.string.strip())
                    data = json.loads(cleaned_json)
                    extracted = StrategyStructuredMetadata._process_json_ld_item(data, page_url)
                    records.extend(extracted)
                except Exception as e:
                    logger.debug(f"Failed to parse JSON-LD script: {e}")

        if records:
            return records

        # 2. Process OpenGraph & Meta tags if no JSON-LD found
        og_record = StrategyStructuredMetadata._extract_open_graph(soup, page_url)
        if og_record:
            records.append(og_record)

        return records

    @staticmethod
    def _process_json_ld_item(data: Any, page_url: str) -> List[Dict[str, Any]]:
        results = []
        if isinstance(data, list):
            for item in data:
                results.extend(StrategyStructuredMetadata._process_json_ld_item(item, page_url))
            return results

        if not isinstance(data, dict):
            return results

        # Handle @graph wrapper
        if "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                results.extend(StrategyStructuredMetadata._process_json_ld_item(item, page_url))
            return results

        type_val = data.get("@type", "")
        types = type_val if isinstance(type_val, list) else [type_val]
        types_lower = [str(t).lower() for t in types]

        # Process Product, Article, NewsArticle, BlogPosting, Offer
        if any(t in types_lower for t in ["product", "article", "newsarticle", "blogposting", "individualproduct", "productmodel"]):
            rec = StrategyStructuredMetadata._json_ld_to_record(data, page_url)
            if rec.get("title"):
                results.append(rec)
        elif "itemlist" in types_lower and "itemListElement" in data:
            for element in data.get("itemListElement", []):
                item = element.get("item", element)
                if isinstance(item, dict):
                    results.extend(StrategyStructuredMetadata._process_json_ld_item(item, page_url))

        return results

    @staticmethod
    def _json_ld_to_record(data: Dict[str, Any], page_url: str) -> Dict[str, Any]:
        title = clean_text(data.get("name") or data.get("headline") or data.get("title"))
        description = clean_text(data.get("description"))
        if description and not is_valid_description(description, min_length=10):
            description = None
        product_url = data.get("url") or page_url
        if product_url:
            product_url = urljoin(page_url, str(product_url))

        # Extract images
        image_urls = []
        img_raw = data.get("image")
        if isinstance(img_raw, str):
            image_urls.append(urljoin(page_url, img_raw))
        elif isinstance(img_raw, list):
            for img in img_raw:
                if isinstance(img, str):
                    image_urls.append(urljoin(page_url, img))
                elif isinstance(img, dict) and "url" in img:
                    image_urls.append(urljoin(page_url, str(img["url"])))
        elif isinstance(img_raw, dict) and "url" in img_raw:
            image_urls.append(urljoin(page_url, str(img_raw["url"])))

        primary_image = image_urls[0] if image_urls else None

        # Extract Brand
        brand = None
        brand_raw = data.get("brand")
        if isinstance(brand_raw, str):
            brand = brand_raw
        elif isinstance(brand_raw, dict):
            brand = brand_raw.get("name")

        # Extract SKU
        sku = clean_text(str(data.get("sku") or data.get("mpn") or data.get("gtin") or ""))

        # Extract Price & Offers (supporting Offer and AggregateOffer)
        price, currency = None, None
        offers = data.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
            currency = offers.get("priceCurrency")
            if not price and "offers" in offers and isinstance(offers["offers"], list) and len(offers["offers"]) > 0:
                sub_off = offers["offers"][0]
                if isinstance(sub_off, dict):
                    price = sub_off.get("price") or sub_off.get("lowPrice")
                    currency = currency or sub_off.get("priceCurrency")
        elif isinstance(offers, list) and len(offers) > 0:
            off0 = offers[0]
            if isinstance(off0, dict):
                price = off0.get("price") or off0.get("lowPrice")
                currency = off0.get("priceCurrency")

        if price:
            p_val, p_curr = parse_price(str(price))
            price = p_val
            if p_curr and not currency:
                currency = p_curr

        return {
            "title": title,
            "image_url": primary_image,
            "description": description,
            "product_url": product_url,
            "price": price,
            "currency": currency,
            "brand": brand,
            "sku": sku,
            "source_url": page_url,
            "image_urls": image_urls
        }

    @staticmethod
    def _extract_open_graph(soup: BeautifulSoup, page_url: str) -> Optional[Dict[str, Any]]:
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        og_type = soup.find("meta", property="og:type")
        
        # Require explicit og:type == product or explicit product price meta tag
        price_tag = soup.find("meta", property="product:price:amount") or soup.find("meta", attrs={"name": "twitter:data1"})
        is_product_type = og_type and og_type.get("content", "").lower() == "product"
        if not (is_product_type or price_tag):
            return None

        if not og_title or not og_title.get("content"):
            title_tag = soup.find("title")
            title = title_tag.text if title_tag else None
        else:
            title = og_title["content"]

        title = clean_text(title)
        if not title:
            return None

        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        description = clean_text(og_desc["content"]) if og_desc and og_desc.get("content") else None
        if description and not is_valid_description(description, min_length=10):
            description = None

        og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        image_url = urljoin(page_url, og_img["content"]) if og_img and og_img.get("content") else None

        og_url = soup.find("meta", property="og:url")
        product_url = urljoin(page_url, og_url["content"]) if og_url and og_url.get("content") else page_url

        # Price meta tags
        price_tag = soup.find("meta", property="product:price:amount") or soup.find("meta", attrs={"name": "twitter:data1"})
        curr_tag = soup.find("meta", property="product:price:currency")
        
        price, currency = None, None
        if price_tag and price_tag.get("content"):
            p_val, p_curr = parse_price(price_tag["content"])
            price = p_val
            currency = p_curr or (curr_tag["content"] if curr_tag and curr_tag.get("content") else None)

        return {
            "title": title,
            "image_url": image_url,
            "description": description,
            "product_url": product_url,
            "price": price,
            "currency": currency,
            "brand": None,
            "sku": None,
            "source_url": page_url,
            "image_urls": [image_url] if image_url else []
        }


class StrategyHTMLCards:
    """Strategy B: Extract records from repeated HTML cards or container elements."""

    CARD_KEYWORDS = re.compile(
        r"(product|item|card|article|grid-item|list-item|entry|catalog|tile|box)", re.I
    )
    LAYOUT_KEYWORDS = re.compile(
        r"(header|navbar|\bnav\b|sidebar|footer|breadcrumb|pagination|\btags?-box\b|\btag-cloud\b)", re.I
    )

    @staticmethod
    def extract(soup: BeautifulSoup, page_url: str) -> List[Dict[str, Any]]:
        records = []
        
        # Candidate container tags
        candidates = []
        for tag in soup.find_all(["article", "li", "div"]):
            # Exclude semantic layout containers
            if tag.find_parent(["header", "nav", "footer", "aside"]):
                continue

            classes = " ".join(tag.get("class", [])) if tag.get("class") else ""
            id_str = str(tag.get("id", ""))

            # Exclude elements whose class or id matches layout / navigation containers
            if StrategyHTMLCards.LAYOUT_KEYWORDS.search(classes) or StrategyHTMLCards.LAYOUT_KEYWORDS.search(id_str):
                continue

            if StrategyHTMLCards.CARD_KEYWORDS.search(classes) or StrategyHTMLCards.CARD_KEYWORDS.search(id_str):
                # Must contain at least a link and a title or image
                if tag.find("a") and (tag.find(["h1", "h2", "h3", "h4", "h5", "h6"]) or tag.find("img")):
                    candidates.append(tag)

        if not candidates:
            return records

        # Group by parent to find repeated card structures
        parent_map = {}
        for cand in candidates:
            parent = cand.parent
            if parent not in parent_map:
                parent_map[parent] = []
            parent_map[parent].append(cand)

        # Find largest sibling group
        best_group = []
        for p, group in parent_map.items():
            if len(group) >= 2 and len(group) > len(best_group):
                best_group = group

        if not best_group:
            # If no group >= 2, consider all candidates if reasonable count
            best_group = candidates[:30]

        for card in best_group:
            rec = StrategyHTMLCards._extract_single_card(card, page_url)
            if rec and rec.get("title"):
                records.append(rec)

        return records

    @staticmethod
    def _extract_single_card(card: Tag, page_url: str) -> Optional[Dict[str, Any]]:
        # 1. Title
        title = None
        heading = card.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading:
            title = clean_text(heading.text)
        
        if not title:
            link = card.find("a")
            if link and link.text:
                title = clean_text(link.text)

        if not title:
            # Try image alt text
            img = card.find("img")
            if img and img.get("alt"):
                title = clean_text(img["alt"])

        if not title or len(title) < 2:
            return None

        # Exclude generic layout / page titles
        if is_generic_title(title):
            return None

        # 2. Product Link
        product_url = page_url
        link_tag = card.find("a", href=True)
        if link_tag and link_tag["href"]:
            href = link_tag["href"]
            if not href.startswith("javascript:") and not href.startswith("#"):
                product_url = urljoin(page_url, href)

        # 3. Image URL
        all_imgs = card.find_all("img")
        image_urls = []
        for img in all_imgs:
            src = get_best_img_src(img, page_url)
            if src and src not in image_urls:
                image_urls.append(src)

        primary_image = image_urls[0] if image_urls else None

        # 4. Description
        description = None
        desc_el = card.find(class_=re.compile(r"(desc|summary|text|content|details)", re.I))
        if desc_el:
            cand_desc = clean_text(desc_el.text)
            if is_valid_description(cand_desc, min_length=15):
                description = cand_desc

        # 5. Price
        price, currency = None, None
        price_el = card.find(class_=re.compile(r"(price|cost|amount|sale)", re.I))
        if price_el:
            price, currency = parse_price(price_el.text)
        else:
            # Regex search inside entire card text for currency pattern
            match = re.search(r'([\$€£¥₹]\s*\d+(?:\.\d{2})?|\d+(?:\.\d{2})?\s*(?:USD|EUR|GBP|INR|CAD))', card.text)
            if match:
                price, currency = parse_price(match.group(0))

        # 6. Brand & SKU
        brand, sku = None, None
        brand_el = card.find(class_=re.compile(r"brand", re.I))
        if brand_el:
            brand = clean_text(brand_el.text)

        sku_el = card.find(class_=re.compile(r"sku", re.I))
        if sku_el:
            sku = clean_text(sku_el.text)

        # 7. Card evidence check: a valid product card must have at least one product attribute
        has_card_evidence = (
            price is not None or
            primary_image is not None or
            (description is not None and len(description) >= 15) or
            brand is not None or
            sku is not None
        )
        if not has_card_evidence:
            return None

        return {
            "title": title,
            "image_url": primary_image,
            "description": description,
            "product_url": product_url,
            "price": price,
            "currency": currency,
            "brand": brand,
            "sku": sku,
            "source_url": page_url,
            "image_urls": image_urls
        }

class StrategyGeneralPage:
    """Strategy C: Extracts standalone product detail pages when sufficient product evidence exists."""

    PRODUCT_EVIDENCE_REGEX = re.compile(
        r"(add-to-cart|add_to_cart|buy-now|buy_now|in-stock|out-of-stock|product-price|product-title|product-detail|product-info|product-sku|sku-number|gtin)",
        re.I
    )

    @staticmethod
    def extract(soup: BeautifulSoup, page_url: str) -> List[Dict[str, Any]]:
        from app.scraper.page_content import find_main_content_container, is_paragraph_prose, is_noise_or_chrome

        # Check explicit product evidence
        main_container = find_main_content_container(soup)
        container_text = main_container.text if main_container else ""
        container_html = str(main_container) if main_container else ""

        # Price check
        price, currency = None, None
        price_el = main_container.find(class_=re.compile(r"(price|amount|sale-price)", re.I))
        if price_el:
            price, currency = parse_price(price_el.text)

        # SKU / Brand check
        sku_el = main_container.find(class_=re.compile(r"sku", re.I))
        sku = clean_text(sku_el.text) if sku_el else None

        brand_el = main_container.find(class_=re.compile(r"brand", re.I))
        brand = clean_text(brand_el.text) if brand_el else None

        # Exclude known generic page titles
        h1 = soup.find("h1")
        h1_text = clean_text(h1.text) if h1 else None
        title_tag = soup.find("title")
        doc_title = clean_text(title_tag.text) if title_tag else None

        title = h1_text or doc_title
        if not title or len(title) < 2:
            return []

        title_candidates = [t for t in (h1_text, doc_title) if t and len(t) >= 2]
        for t_cand in title_candidates:
            if is_generic_title(t_cand):
                return []

        # Check explicit or combined B2B product evidence
        has_explicit_evidence = (
            price is not None or
            sku is not None or
            brand is not None or
            bool(StrategyGeneralPage.PRODUCT_EVIDENCE_REGEX.search(container_html))
        )

        # Do not allow root homepage URLs to be extracted as products merely through general fallback heuristics
        parsed_url = urlparse(str(page_url or ""))
        is_root_homepage = parsed_url.path.strip("/") in ("", "index.html", "index.htm", "index.php")
        if is_root_homepage and not has_explicit_evidence:
            return []

        # B2B product evidence: valid description paragraph + product image + no generic page indicators
        valid_p = []

        # 1. Prefer explicit description container within main content
        explicit_desc_el = main_container.find(class_=re.compile(r"(product-description|short-description|item-description)", re.I))
        if explicit_desc_el and not explicit_desc_el.find_parent(["header", "footer", "nav"]) and not is_noise_or_chrome(explicit_desc_el):
            cand = clean_text(explicit_desc_el.text)
            if is_valid_description(cand, min_length=15):
                valid_p.append(cand)

        # 2. Collect candidate prose in reading order from <p> and heading-wrapped prose (h2..h5)
        for tag in main_container.find_all(["p", "h2", "h3", "h4", "h5"]):
            if tag.find_parent(["header", "footer", "nav"]):
                continue
            if is_noise_or_chrome(tag):
                continue

            tag_name = tag.name.lower()
            text = clean_text(tag.text)
            if not text:
                continue

            # Heading elements must qualify as prose
            if tag_name in ("h2", "h3", "h4", "h5"):
                if not is_paragraph_prose(text):
                    continue

            if is_valid_description(text, min_length=20):
                if text not in valid_p:
                    valid_p.append(text)

        description = valid_p[0] if valid_p else None

        image_urls = []
        images_meta = []
        for img in main_container.find_all("img"):
            meta = extract_rich_image_metadata(img, page_url, container_soup=main_container)
            if meta and meta["image_url"] not in image_urls:
                # Exclude obvious header/footer logos or social icons
                src_lower = meta["image_url"].lower()
                if not any(ign in src_lower for ign in ["logo", "icon", "banner-static", "avatar"]):
                    image_urls.append(meta["image_url"])
                    images_meta.append(meta)

        has_b2b_evidence = bool(description and (image_urls or len(valid_p) >= 2))

        if not (has_explicit_evidence or has_b2b_evidence):
            return []

        primary_image = image_urls[0] if image_urls else None

        return [{
            "title": title,
            "image_url": primary_image,
            "description": description,
            "product_url": page_url,
            "price": price,
            "currency": currency,
            "brand": brand,
            "sku": sku,
            "source_url": page_url,
            "image_urls": image_urls,
            "images": images_meta
        }]

