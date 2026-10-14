import json
import io
import zipfile
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import OUTPUT_DIR
from app.api.routes import jobs_db
from app.models import JobResponse, JobStatus, ExtractedRecord, ScrapeStats, ImageMetadata

client = TestClient(app)

@pytest.fixture
def mock_job_artifacts(tmp_path_factory):
    """Fixture creating a test job in jobs_db and its output directory with 4 canonical JSON files."""
    job_id = "test-phase18-job"
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    products_data = [
        {
            "title": "Medical Gas Alarm Panel",
            "image_url": "https://example.com/img/alarm.jpg",
            "description": "Digital master alarm panel for medical gas systems.",
            "product_url": "https://example.com/products/alarm",
            "price": "450.00",
            "currency": "USD",
            "brand": "MedTech",
            "sku": "ALM-101",
            "source_url": "https://example.com/products/alarm",
            "image_urls": ["https://example.com/img/alarm.jpg"],
            "images": [
                {
                    "image_url": "https://example.com/img/alarm.jpg",
                    "title": "Front Panel View <script>alert(1)</script>",
                    "alt": "Digital Alarm & Sensors",
                    "caption": "Master alarm overview",
                    "section_title": "Specifications & Features",
                    "source_page_url": "https://example.com/products/alarm"
                }
            ]
        }
    ]

    pages_data = [
        {
            "url": "https://example.com/products/alarm",
            "status_code": 200,
            "title": "Medical Gas Alarm Panel - MedTech",
            "page_type": "product",
            "headings": {
                "h1": ["Medical Gas Alarm Panel"],
                "h2": ["Specifications & Features", "Installation Notes"],
                "h3": []
            },
            "content_text": "Digital master alarm panel for medical gas systems with audio-visual alerts."
        },
        {
            "url": "https://example.com/empty-page",
            "status_code": 200,
            "title": "",
            "page_type": "general",
            "headings": {},
            "content_text": ""
        }
    ]

    report_data = {
        "job_id": job_id,
        "target_url": "https://example.com",
        "mode": "auto",
        "duration_seconds": 12.5,
        "pages_visited": 2,
        "records_extracted": 1,
        "stop_reason": "queue_exhausted",
        "crawl_complete": True,
        "errors": []
    }

    sitemap_data = {
        "job_id": job_id,
        "sitemap_urls_discovered": ["https://example.com/sitemap.xml"],
        "total_urls_found": 15
    }

    with open(job_dir / "products.json", "w", encoding="utf-8") as f:
        json.dump(products_data, f)
    with open(job_dir / "website_pages.json", "w", encoding="utf-8") as f:
        json.dump(pages_data, f)
    with open(job_dir / "extraction_report.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f)
    with open(job_dir / "sitemap_inventory.json", "w", encoding="utf-8") as f:
        json.dump(sitemap_data, f)

    record_obj = ExtractedRecord(
        title=products_data[0]["title"],
        image_url=products_data[0]["image_url"],
        description=products_data[0]["description"],
        product_url=products_data[0]["product_url"],
        price=products_data[0]["price"],
        currency=products_data[0]["currency"],
        brand=products_data[0]["brand"],
        sku=products_data[0]["sku"],
        source_url=products_data[0]["source_url"],
        image_urls=products_data[0]["image_urls"],
        images=[ImageMetadata(**products_data[0]["images"][0])]
    )

    jobs_db[job_id] = JobResponse(
        job_id=job_id,
        status=JobStatus.COMPLETED,
        target_url="https://example.com",
        progress=100.0,
        status_message="Completed",
        stats=ScrapeStats(pages_visited=2, records_extracted=1, crawl_complete=True),
        records=[record_obj]
    )

    yield {
        "job_id": job_id,
        "job_dir": job_dir,
        "products_data": products_data,
        "pages_data": pages_data,
        "report_data": report_data,
        "sitemap_data": sitemap_data
    }

    # Cleanup
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    if job_id in jobs_db:
        del jobs_db[job_id]


def test_download_individual_artifacts(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]

    artifact_types = {
        "products": ("products.json", mock_job_artifacts["products_data"]),
        "pages": ("website_pages.json", mock_job_artifacts["pages_data"]),
        "report": ("extraction_report.json", mock_job_artifacts["report_data"]),
        "sitemap": ("sitemap_inventory.json", mock_job_artifacts["sitemap_data"]),
    }

    for art_type, (expected_filename, expected_data) in artifact_types.items():
        resp = client.get(f"/api/jobs/{job_id}/download/{art_type}")
        assert resp.status_code == 200, f"Failed for {art_type}: {resp.text}"
        assert resp.headers["content-type"] == "application/json"
        assert f'filename="{expected_filename}"' in resp.headers["content-disposition"]
        data = resp.json()
        assert data == expected_data, f"Data mismatch for {art_type}"


def test_download_bundle_zip(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]

    resp = client.get(f"/api/jobs/{job_id}/download/bundle")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert f'filename="scrape_bundle_{job_id}.zip"' in resp.headers["content-disposition"]

    # Read the in-memory ZIP content
    zip_buffer = io.BytesIO(resp.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        namelist = zf.namelist()
        assert set(namelist) == {
            "products.json",
            "website_pages.json",
            "extraction_report.json",
            "sitemap_inventory.json"
        }

        # Validate that each artifact in the zip contains valid JSON matching original
        extracted_prods = json.loads(zf.read("products.json").decode("utf-8"))
        assert extracted_prods == mock_job_artifacts["products_data"]

        extracted_pages = json.loads(zf.read("website_pages.json").decode("utf-8"))
        assert extracted_pages == mock_job_artifacts["pages_data"]

        extracted_report = json.loads(zf.read("extraction_report.json").decode("utf-8"))
        assert extracted_report == mock_job_artifacts["report_data"]

        extracted_sitemap = json.loads(zf.read("sitemap_inventory.json").decode("utf-8"))
        assert extracted_sitemap == mock_job_artifacts["sitemap_data"]


def test_download_bundle_missing_artifact(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]
    job_dir = mock_job_artifacts["job_dir"]

    # Delete sitemap_inventory.json to simulate an incomplete crawl output
    sitemap_file = job_dir / "sitemap_inventory.json"
    sitemap_file.unlink()

    resp = client.get(f"/api/jobs/{job_id}/download/bundle")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "Incomplete bundle" in detail
    assert "sitemap_inventory.json" in detail


def test_download_individual_missing_artifact(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]
    job_dir = mock_job_artifacts["job_dir"]

    report_file = job_dir / "extraction_report.json"
    report_file.unlink()

    resp = client.get(f"/api/jobs/{job_id}/download/report")
    assert resp.status_code == 404
    assert "Artifact 'report' (extraction_report.json) not found" in resp.json()["detail"]


def test_unknown_job_and_unsupported_type(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]

    # Unknown job for individual artifact
    resp_unknown_art = client.get("/api/jobs/non-existent-99999/download/products")
    assert resp_unknown_art.status_code == 404

    # Unknown job for bundle
    resp_unknown_bundle = client.get("/api/jobs/non-existent-99999/download/bundle")
    assert resp_unknown_bundle.status_code == 404

    # Unsupported artifact type
    resp_unsupported = client.get(f"/api/jobs/{job_id}/download/unknown_type")
    assert resp_unsupported.status_code == 400
    assert "Unsupported artifact type 'unknown_type'" in resp_unsupported.json()["detail"]


def test_path_traversal_and_cross_job_isolation(mock_job_artifacts):
    # Path traversal patterns in job_id
    traversal_ids = [
        "../etc",
        "..\\windows",
        "job/../../sensitive",
        "job%2F..%2Fdir",
        "valid_job/extra"
    ]

    for bad_id in traversal_ids:
        resp = client.get(f"/api/jobs/{bad_id}/download/products")
        assert resp.status_code in [400, 404], f"Expected 400/404 for bad id '{bad_id}', got {resp.status_code}"
        if resp.status_code == 400:
            assert "Invalid job ID format" in resp.json()["detail"]


def test_legacy_download_backward_compatibility(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]

    resp = client.get(f"/api/jobs/{job_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert "attachment;" in resp.headers["content-disposition"]
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Medical Gas Alarm Panel"


def test_pages_preview_endpoint(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]

    resp = client.get(f"/api/jobs/{job_id}/pages")
    assert resp.status_code == 200
    pages = resp.json()
    assert len(pages) == 2
    assert pages[0]["url"] == "https://example.com/products/alarm"
    assert pages[0]["headings"]["h1"] == ["Medical Gas Alarm Panel"]
    assert pages[1]["url"] == "https://example.com/empty-page"
    assert pages[1]["headings"] == {}


def test_pages_preview_missing_file():
    job_id = "test-no-pages-job"
    jobs_db[job_id] = JobResponse(
        job_id=job_id,
        status=JobStatus.COMPLETED,
        target_url="https://example.com",
        progress=100.0,
        status_message="Completed",
        stats=ScrapeStats()
    )

    resp = client.get(f"/api/jobs/{job_id}/pages")
    assert resp.status_code == 200
    assert resp.json() == []

    del jobs_db[job_id]


def test_rich_image_metadata_and_html_escaping(mock_job_artifacts):
    job_id = mock_job_artifacts["job_id"]

    # Verify that products contain image metadata with potentially unsafe HTML characters
    resp = client.get(f"/api/jobs/{job_id}/download/products")
    assert resp.status_code == 200
    data = resp.json()
    img = data[0]["images"][0]
    assert "<script>alert(1)</script>" in img["title"]
    assert "&" in img["alt"]
    assert img["section_title"] == "Specifications & Features"


def test_cross_job_isolation(mock_job_artifacts):
    job_id_a = mock_job_artifacts["job_id"]
    job_id_b = "test-phase18-job-b"
    job_dir_b = OUTPUT_DIR / job_id_b
    job_dir_b.mkdir(parents=True, exist_ok=True)

    products_b = [{"title": "Distinct Job B Product", "source_url": "https://example.com/b"}]
    with open(job_dir_b / "products.json", "w", encoding="utf-8") as f:
        json.dump(products_b, f)

    try:
        resp_a = client.get(f"/api/jobs/{job_id_a}/download/products")
        resp_b = client.get(f"/api/jobs/{job_id_b}/download/products")

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()[0]["title"] == "Medical Gas Alarm Panel"
        assert resp_b.json()[0]["title"] == "Distinct Job B Product"
    finally:
        shutil.rmtree(job_dir_b, ignore_errors=True)


def test_download_in_progress_job_error():
    job_id = "test-job-running"
    jobs_db[job_id] = JobResponse(
        job_id=job_id,
        status=JobStatus.RUNNING,
        target_url="https://example.com",
        progress=50.0,
        status_message="Crawling in progress..."
    )

    resp = client.get(f"/api/jobs/{job_id}/download")
    assert resp.status_code == 400
    assert "Job results are not ready for download yet" in resp.json()["detail"]

    del jobs_db[job_id]


def test_image_metadata_optional_fields_graceful():
    # Test record with images having only image_url and all other fields None
    record = ExtractedRecord(
        title="Minimal Image Record",
        source_url="https://example.com/item",
        image_urls=["https://example.com/img.jpg"],
        images=[
            ImageMetadata(
                image_url="https://example.com/img.jpg",
                title=None,
                alt=None,
                caption=None,
                section_title=None,
                source_page_url=None
            )
        ]
    )
    dumped = record.model_dump()
    assert dumped["images"][0]["title"] is None
    assert dumped["images"][0]["image_url"] == "https://example.com/img.jpg"


def test_unknown_job_pages_endpoint_404():
    """Assert requesting /api/jobs/{unknown_id}/pages returns 404 Not Found."""
    resp = client.get("/api/jobs/non-existent-pages-job/pages")
    assert resp.status_code == 404
    assert "Job 'non-existent-pages-job' not found" in resp.json()["detail"]


def test_frontend_url_safety_rules():
    """Test safeUrl() rules directly via Node on static/app.js exports."""
    import subprocess
    node_test_script = """
    const { safeUrl } = require('./static/app.js');
    const testCases = [
        // Allowed
        { input: 'http://example.com/prod', expectedAllowed: true },
        { input: 'https://example.com/path?foo=1&bar=2', expectedAllowed: true },
        { input: '/catalog/products', expectedAllowed: true },

        // Rejected protocol-relative
        { input: '//evil.com/phish', expectedAllowed: false },

        // Rejected dangerous schemes
        { input: 'javascript:alert(1)', expectedAllowed: false },
        { input: 'JAVASCRIPT:alert(document.cookie)', expectedAllowed: false },
        { input: 'data:text/html,<script>alert(1)</script>', expectedAllowed: false },
        { input: 'vbscript:msgbox(1)', expectedAllowed: false },

        // Rejected malformed, empty, and non-string values
        { input: 'https://', expectedAllowed: false },
        { input: '', expectedAllowed: false },
        { input: '   ', expectedAllowed: false },
        { input: null, expectedAllowed: false },
        { input: undefined, expectedAllowed: false }
    ];

    for (const { input, expectedAllowed } of testCases) {
        const result = safeUrl(input);
        const isAllowed = typeof result === 'string' && result.length > 0;
        if (isAllowed !== expectedAllowed) {
            console.error(`Mismatch for input "${input}": expected allowed=${expectedAllowed}, got "${result}"`);
            process.exit(1);
        }
        // Verify HTML escaping on allowed URLs with &
        if (input === 'https://example.com/path?foo=1&bar=2') {
            if (!result.includes('&amp;')) {
                console.error(`Expected &amp; in escaped url, got "${result}"`);
                process.exit(1);
            }
        }
    }
    """
    res = subprocess.run(["node", "-e", node_test_script], cwd=str(Path(__file__).resolve().parent.parent), capture_output=True, text=True)
    assert res.returncode == 0, f"Node URL tests failed: {res.stderr}\n{res.stdout}"


def test_download_error_feedback_contracts(mock_job_artifacts):
    """Verify that failed download requests return JSON errors suitable for frontend showError display."""
    job_id = mock_job_artifacts["job_id"]

    # 1. Unsupported artifact type -> 400 with descriptive detail
    resp_bad_type = client.get(f"/api/jobs/{job_id}/download/invalid_artifact")
    assert resp_bad_type.status_code == 400
    detail_bad = resp_bad_type.json().get("detail", "")
    assert "Unsupported artifact type 'invalid_artifact'" in detail_bad

    # 2. Missing artifact -> 404 with descriptive detail
    job_dir = mock_job_artifacts["job_dir"]
    pages_file = job_dir / "website_pages.json"
    pages_file.unlink()

    resp_missing = client.get(f"/api/jobs/{job_id}/download/pages")
    assert resp_missing.status_code == 404
    detail_missing = resp_missing.json().get("detail", "")
    assert "Artifact 'pages' (website_pages.json) not found" in detail_missing

    # 3. Incomplete bundle -> 404 with list of missing files
    resp_incomplete = client.get(f"/api/jobs/{job_id}/download/bundle")
    assert resp_incomplete.status_code == 404
    detail_incomplete = resp_incomplete.json().get("detail", "")
    assert "Incomplete bundle" in detail_incomplete
    assert "website_pages.json" in detail_incomplete


