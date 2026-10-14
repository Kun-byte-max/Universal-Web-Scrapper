import json
import pytest
from app.models import ExtractedRecord
from app.scraper.exporter import export_records_to_json

def test_export_records_to_json():
    records = [
        ExtractedRecord(
            title="Café Machine Pro",
            image_url="https://example.com/cafe.jpg",
            description="Premium espresso machine with 15-bar pressure.",
            product_url="https://example.com/cafe",
            price=499.0,
            currency="EUR",
            brand="De'Longhi",
            sku="DL-990",
            source_url="https://example.com/catalog",
            image_urls=["https://example.com/cafe.jpg"]
        )
    ]

    json_output = export_records_to_json(records)
    parsed = json.loads(json_output)

    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Café Machine Pro"
    assert parsed[0]["currency"] == "EUR"
    assert "De'Longhi" in json_output  # Ensure Unicode UTF-8 preserved
