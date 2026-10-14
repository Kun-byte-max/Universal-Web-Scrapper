import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import jobs_db
from app.models import JobResponse, JobStatus, ExtractedRecord, ScrapeStats

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "app" in data

def test_scrape_validation_error():
    # Invalid scheme
    response = client.post("/api/scrape", json={"url": "invalid-url"})
    assert response.status_code == 422

def test_job_not_found():
    response = client.get("/api/jobs/non-existent-job-id")
    assert response.status_code == 404

def test_download_completed_job():
    job_id = "test-job-123"
    records = [
        ExtractedRecord(
            title="Test Item",
            image_url="https://example.com/img.jpg",
            description="Test Description",
            product_url="https://example.com/item",
            price=10.0,
            currency="USD",
            brand=None,
            sku="SKU-1",
            source_url="https://example.com/cat",
            image_urls=[]
        )
    ]
    
    jobs_db[job_id] = JobResponse(
        job_id=job_id,
        status=JobStatus.COMPLETED,
        target_url="https://example.com/cat",
        progress=100.0,
        status_message="Completed",
        stats=ScrapeStats(pages_visited=1, records_extracted=1),
        records=records
    )

    response = client.get(f"/api/jobs/{job_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert "attachment;" in response.headers["content-disposition"]
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Item"

def test_download_failed_job_behavior():
    # Failed job with recovered partial records allows download
    job_id_recovered = "test-job-recovered"
    jobs_db[job_id_recovered] = JobResponse(
        job_id=job_id_recovered,
        status=JobStatus.FAILED,
        target_url="https://example.com/fail",
        progress=100.0,
        status_message="Failed",
        error="Crawl timed out",
        records=[
            ExtractedRecord(
                title="Recovered Product",
                source_url="https://example.com/p",
                image_urls=[]
            )
        ]
    )
    resp_rec = client.get(f"/api/jobs/{job_id_recovered}/download")
    assert resp_rec.status_code == 200
    data_rec = resp_rec.json()
    assert len(data_rec) == 1
    assert data_rec[0]["title"] == "Recovered Product"

    # Failed job with NO records returns 400
    job_id_empty = "test-job-empty-fail"
    jobs_db[job_id_empty] = JobResponse(
        job_id=job_id_empty,
        status=JobStatus.FAILED,
        target_url="https://example.com/fail",
        progress=100.0,
        status_message="Failed",
        error="Worker crashed",
        records=[]
    )
    resp_empty = client.get(f"/api/jobs/{job_id_empty}/download")
    assert resp_empty.status_code == 400
    assert "Job failed with no extracted records" in resp_empty.json()["detail"]

def test_scrape_explicit_auto_with_limits_422():
    response = client.post("/api/scrape", json={
        "url": "https://example.com",
        "mode": "auto",
        "max_pages": 10
    })
    assert response.status_code == 422
    err_detail = response.json()["detail"]
    assert any("Cannot specify max_pages or max_records when mode is 'auto'" in str(e) for e in err_detail)
