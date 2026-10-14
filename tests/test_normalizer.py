import pytest
from app.scraper.normalizer import normalize_records

def test_normalize_and_deduplicate():
    raw_input = [
        {
            "title": "Item A ",
            "sku": "SKU-100",
            "product_url": "https://example.com/p1#ref",
            "image_url": "https://example.com/img1.jpg",
            "source_url": "https://example.com/cat"
        },
        # Duplicate by SKU
        {
            "title": "Item A Duplicate",
            "sku": "SKU-100",
            "product_url": "https://example.com/p1-duplicate",
            "image_url": "https://example.com/img1.jpg",
            "source_url": "https://example.com/cat"
        },
        # Duplicate by product_url fragment removal
        {
            "title": "Item B",
            "sku": None,
            "product_url": "https://example.com/p2#section",
            "image_url": "https://example.com/img2.jpg",
            "source_url": "https://example.com/cat"
        },
        {
            "title": "Item B Copy",
            "sku": None,
            "product_url": "https://example.com/p2",
            "image_url": "https://example.com/img2.jpg",
            "source_url": "https://example.com/cat"
        }
    ]

    normalized = normalize_records(raw_input, "https://example.com/cat")
    
    assert len(normalized) == 2
    assert normalized[0].sku == "SKU-100"
    assert normalized[0].product_url == "https://example.com/p1"
    assert normalized[1].product_url == "https://example.com/p2"

def test_missing_fields_defaults():
    raw = [{
        "title": "Minimal Product",
        "source_url": "https://example.com/p"
    }]
    normalized = normalize_records(raw, "https://example.com/p")
    assert len(normalized) == 1
    rec = normalized[0]
    assert rec.title == "Minimal Product"
    assert rec.price is None
    assert rec.currency is None
    assert rec.brand is None
    assert rec.sku is None
    assert rec.image_urls == []
