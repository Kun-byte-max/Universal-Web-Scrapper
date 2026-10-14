from typing import List, Dict, Any
from app.models import ExtractedRecord
from app.scraper.safety import normalize_url

def normalize_records(raw_records: List[Dict[str, Any]], default_source_url: str) -> List[ExtractedRecord]:
    """
    Normalize raw extraction dicts into standard ExtractedRecord models.
    Removes duplicate records based on product_url, sku, or title/image signature.
    """
    normalized_list: List[ExtractedRecord] = []
    seen_keys = set()

    for raw in raw_records:
        title = raw.get("title")
        if not title or len(str(title).strip()) < 2:
            continue

        title = str(title).strip()
        description = raw.get("description")
        if description:
            description = str(description).strip()

        source_url = raw.get("source_url") or default_source_url
        product_url = raw.get("product_url") or source_url
        if product_url:
            product_url = normalize_url(product_url)

        image_url = raw.get("image_url")
        if image_url:
            image_url = normalize_url(image_url)

        image_urls = raw.get("image_urls") or []
        norm_image_urls = []
        for img in image_urls:
            if img:
                norm_img = normalize_url(img)
                if norm_img not in norm_image_urls:
                    norm_image_urls.append(norm_img)

        price = raw.get("price")
        currency = raw.get("currency")
        brand = raw.get("brand")
        sku = raw.get("sku")

        # Key for deduplication
        dedup_key = None
        if sku:
            dedup_key = f"sku:{sku.lower()}"
        elif product_url and product_url != default_source_url:
            dedup_key = f"url:{product_url.lower()}"
        else:
            dedup_key = f"title_img:{title.lower()}_{image_url or ''}"

        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        raw_images = raw.get("images") or []
        norm_images = []
        for img_obj in raw_images:
            if isinstance(img_obj, dict) and img_obj.get("image_url"):
                img_obj["image_url"] = normalize_url(img_obj["image_url"])
                norm_images.append(img_obj)

        record = ExtractedRecord(
            title=title,
            image_url=image_url,
            description=description,
            product_url=product_url,
            price=price,
            currency=currency,
            brand=brand,
            sku=sku,
            source_url=source_url,
            image_urls=norm_image_urls,
            images=norm_images
        )
        normalized_list.append(record)

    return normalized_list
