import uuid
import asyncio
from typing import Dict
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response
from fastapi.responses import Response, FileResponse

from app.models import ScrapeRequest, JobResponse, JobStatus, ScrapeStats, ExtractedRecord
from app.scraper.scrapy_engine.runner import ScrapyJobRunner
from app.scraper.exporter import export_records_to_json
from app.config import settings, OUTPUT_DIR

router = APIRouter()

import io
import re
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional

# In-memory job store
jobs_db: Dict[str, JobResponse] = {}

SAFE_JOB_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")

ARTIFACT_FILE_MAP = {
    "products": "products.json",
    "pages": "website_pages.json",
    "report": "extraction_report.json",
    "sitemap": "sitemap_inventory.json",
    "inventory": "url_inventory.json",
}

EXPECTED_BUNDLE_FILES = [
    "products.json",
    "website_pages.json",
    "extraction_report.json",
    "sitemap_inventory.json"
]

OPTIONAL_BUNDLE_FILES = [
    "url_inventory.json"
]

VALID_INVENTORY_STATUSES = {"discovered", "pending", "crawled", "failed", "skipped"}

def _resolve_safe_job_dir(job_id: str) -> Path:
    """Validate job_id format and resolve canonical output directory preventing path traversal."""
    if not job_id or not SAFE_JOB_ID_REGEX.match(job_id):
        raise HTTPException(status_code=400, detail=f"Invalid job ID format: '{job_id}'")
    
    base_output = OUTPUT_DIR.resolve()
    job_dir = (OUTPUT_DIR / job_id).resolve()
    
    # Path traversal protection
    if base_output not in job_dir.parents and job_dir != base_output:
        raise HTTPException(status_code=400, detail="Invalid job path specification")
        
    return job_dir

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    job = jobs_db.get(job_id)
    if not job:
        job_dir = _resolve_safe_job_dir(job_id)
        report_file = job_dir / "extraction_report.json"
        products_file = job_dir / "products.json"
        if report_file.exists() and products_file.exists():
            try:
                rep_data = json.loads(report_file.read_text(encoding="utf-8"))
                prods_data = json.loads(products_file.read_text(encoding="utf-8"))
                records = [ExtractedRecord(**p) for p in prods_data]
                stats = ScrapeStats(
                    pages_visited=rep_data.get("pages_visited", 0),
                    records_extracted=len(records),
                    duration_seconds=rep_data.get("duration_seconds", 0.0),
                    errors=rep_data.get("errors", []),
                    stop_reason=rep_data.get("stop_reason", "queue_exhausted"),
                    crawl_complete=rep_data.get("crawl_complete", True)
                )
                reconstructed = JobResponse(
                    job_id=job_id,
                    status=JobStatus.COMPLETED,
                    target_url=rep_data.get("target_url", ""),
                    progress=100.0,
                    status_message=f"Completed successfully. Extracted {len(records)} products.",
                    stats=stats,
                    records=records
                )
                jobs_db[job_id] = reconstructed
                return reconstructed
            except Exception:
                pass
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/jobs/{job_id}/pages")
async def get_job_pages(job_id: str):
    """Retrieve visited pages array from website_pages.json for dashboard preview."""
    job = jobs_db.get(job_id)
    job_dir = _resolve_safe_job_dir(job_id)
    if not job and not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    pages_file = job_dir / "website_pages.json"
    if not pages_file.exists():
        return []

    try:
        return json.loads(pages_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading visited pages: {str(e)}")

@router.get("/jobs/{job_id}/download")
async def download_job_results(job_id: str):
    job = jobs_db.get(job_id)
    if not job:
        job_dir = _resolve_safe_job_dir(job_id)
        if job_dir.exists():
            prod_file = job_dir / "products.json"
            if prod_file.exists():
                content = prod_file.read_text(encoding="utf-8")
                filename = f"scrape_results_{job_id[:8]}.json"
                return Response(
                    content=content,
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'}
                )
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED) or not job.records:
        if job.status == JobStatus.FAILED:
            raise HTTPException(status_code=400, detail=f"Job failed with no extracted records: {job.error or 'Worker error'}")
        raise HTTPException(status_code=400, detail="Job results are not ready for download yet")

    json_str = export_records_to_json(job.records)
    filename = f"scrape_results_{job_id[:8]}.json"

    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/jobs/{job_id}/download/bundle")
async def download_job_bundle(job_id: str):
    """Create in-memory ZIP bundle containing all 4 canonical crawl artifacts."""
    job_dir = _resolve_safe_job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job output directory not found for job '{job_id}'")

    missing = [fname for fname in EXPECTED_BUNDLE_FILES if not (job_dir / fname).exists()]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Incomplete bundle for job '{job_id}': missing required artifact(s): {', '.join(missing)}"
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname in EXPECTED_BUNDLE_FILES:
            zf.write(job_dir / fname, arcname=fname)
        for fname in OPTIONAL_BUNDLE_FILES:
            opt_path = job_dir / fname
            if opt_path.exists():
                zf.write(opt_path, arcname=fname)

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()
    bundle_filename = f"scrape_bundle_{job_id}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle_filename}"'}
    )

@router.get("/jobs/{job_id}/download/{artifact_type}")
async def download_job_artifact(job_id: str, artifact_type: str):
    """Download specific JSON artifact: products, pages, report, sitemap, or inventory."""
    art_key = artifact_type.lower()
    if art_key not in ARTIFACT_FILE_MAP:
        allowed = ", ".join(sorted(ARTIFACT_FILE_MAP.keys()))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported artifact type '{artifact_type}'. Supported types: {allowed}"
        )

    job_dir = _resolve_safe_job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job output directory not found for job '{job_id}'")

    target_filename = ARTIFACT_FILE_MAP[art_key]
    file_path = job_dir / target_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{artifact_type}' ({target_filename}) not found for job '{job_id}'"
        )

    content = file_path.read_text(encoding="utf-8")

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{target_filename}"'}
    )

@router.get("/jobs/{job_id}/inventory")
async def get_job_inventory(
    job_id: str,
    page: int = 1,
    page_size: int = 50,
    status: Optional[str] = None
):
    """Paginated, filterable URL inventory endpoint scoped to job_id."""
    job_dir = _resolve_safe_job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job output directory not found for job '{job_id}'")

    inv_file = job_dir / "url_inventory.json"
    if not inv_file.exists():
        raise HTTPException(status_code=404, detail=f"URL inventory not found for job '{job_id}'")

    if page < 1:
        raise HTTPException(status_code=400, detail="Invalid page: page must be >= 1")
    if page_size < 1 or page_size > 500:
        raise HTTPException(status_code=400, detail="Invalid page_size: page_size must be between 1 and 500")

    if status:
        status_clean = status.strip().lower()
        if status_clean not in VALID_INVENTORY_STATUSES:
            allowed = ", ".join(sorted(VALID_INVENTORY_STATUSES))
            raise HTTPException(status_code=400, detail=f"Invalid status filter '{status}'. Allowed statuses: {allowed}")
    else:
        status_clean = None

    try:
        with open(inv_file, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        logger.error(f"Error reading url_inventory.json for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load URL inventory file")

    if status_clean:
        items = [item for item in items if item.get("status") == status_clean]

    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_items = items[start_idx:end_idx]

    return {
        "job_id": job_id,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "status_filter": status_clean,
        "items": paginated_items
    }

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION
    }

async def run_scrape_job(job_id: str, request: ScrapeRequest):
    job = jobs_db.get(job_id)
    if not job:
        return

    job.status = JobStatus.RUNNING
    job.status_message = "Scrape job started using Scrapy engine"

    def progress_callback(pct: float, message: str, stats: ScrapeStats):
        job.progress = round(pct, 1)
        job.status_message = message
        job.stats = stats

    try:
        # Run Scrapy job in sub-process via ScrapyJobRunner
        records, stats = await asyncio.to_thread(
            ScrapyJobRunner.run_job, request, job_id, progress_callback
        )

        job.records = records
        job.stats = stats

        stop_reason = getattr(stats, "stop_reason", "queue_exhausted")
        crawl_complete = getattr(stats, "crawl_complete", True)
        has_fatal_error = (
            stop_reason in ("timeout", "worker_error")
            or any("timeout" in e.lower() or "crashed" in e.lower() or "abnormally" in e.lower() for e in stats.errors)
        )
        root_failed = (stop_reason == "download_error" and stats.pages_visited == 0)

        if has_fatal_error or root_failed:
            job.status = JobStatus.FAILED
            err_msg = stats.errors[0] if stats.errors else f"Crawl stopped unexpectedly: {stop_reason}"
            job.error = err_msg
            if stop_reason == "timeout":
                job.status_message = f"Scrape job timed out. Recovered {len(records)} products."
            elif stop_reason == "worker_error":
                job.status_message = f"Scrape job worker failed. Recovered {len(records)} products."
            else:
                job.status_message = f"Scrape job failed: {err_msg}"
        else:
            job.status = JobStatus.COMPLETED
            if stop_reason == "queue_exhausted" and crawl_complete:
                job.status_message = f"Completed successfully. Extracted {len(records)} products."
            else:
                formatted_reason = stop_reason.replace("_", " ").title()
                job.status_message = f"Crawl finished ({formatted_reason}). Extracted {len(records)} products."
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.status_message = f"Scrape job failed: {str(e)}"


@router.post("/scrape", response_model=JobResponse)
async def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    job = JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        target_url=request.url,
        progress=0.0,
        status_message="Job queued"
    )
    jobs_db[job_id] = job

    # Run in background task so UI can poll progress asynchronously
    background_tasks.add_task(run_scrape_job, job_id, request)
    return job
