# Universal Website-to-JSON Scraper

A production-ready website-to-JSON scraping web application built with **FastAPI** and **Scrapy**.

The system provides an automated crawling and structured data extraction engine with an interactive web dashboard for submitting crawl jobs, monitoring live progress, reviewing extracted products and rich image metadata, inspecting visited pages, and exporting artifacts in JSON and ZIP formats.

---

## 🏛️ Architecture Overview

The application is structured into a decoupled web API and an isolated Scrapy execution subsystem:

```
Web_scrapper/
├── app/
│   ├── api/
│   │   └── routes.py              # REST API endpoints (jobs, polling, downloads, bundle, pages)
│   ├── scraper/
│   │   ├── extractors.py          # Extraction strategies (JSON-LD, HTML Cards, Generic Page fallback)
│   │   ├── parser.py              # Strategy orchestrator & heuristic selection
│   │   ├── safety.py              # SSRF protection, IP/DNS validation, scheme filtering
│   │   └── scrapy_engine/
│   │       ├── runner.py          # ScrapyJobRunner (isolated multiprocessing.Process supervisor)
│   │       ├── pipelines.py       # ScrapyExtractionPipeline (dedup, atomic JSON artifact writes)
│   │       ├── middlewares.py     # SSRFDownloaderMiddleware
│   │       ├── items.py           # Scrapy Item definitions
│   │       └── spiders/
│   │           └── universal_spider.py # UniversalSitemapSpider (sitemap discovery + crawler)
│   ├── config.py                  # Application settings, limits, & safety ceilings
│   ├── models.py                  # Pydantic schemas (requests, records, job responses)
│   └── main.py                    # FastAPI application & static asset mounts
├── templates/
│   └── index.html                 # Modern glassmorphism dashboard UI
├── static/
│   ├── styles.css                 # Dark theme, glassmorphism, responsive styles
│   └── app.js                     # Frontend state management, tab routing, gallery previews
├── tests/                         # Automated unit, integration, & regression test suites
├── output/                        # Per-job artifact directories (output/<job_id>/)
├── requirements.txt
└── README.md
```

### Subprocess Isolation
Scrapy runs Twisted's event reactor, which cannot be cleanly restarted within a single persistent process. To ensure complete isolation and prevent reactor conflicts or memory leaks, each crawl job is launched in a dedicated sub-process via Python's standard `multiprocessing.Process`. The runner monitors child process execution, enforces timeouts, handles crashes gracefully, and recovers checkpointed items if a process terminates unexpectedly.

---

## 🧭 Crawl Modes & Safety Ceilings

The scraper supports two distinct crawl modes:

### 1. Auto Mode (`mode="auto"`)
Designed for full-catalog discovery without requiring users to guess catalog size:
- Probes `/sitemap.xml`, `/sitemap_index.xml`, and `robots.txt` for sitemap indexes.
- Traverses discovered product and category URLs across the same registered domain.
- Stops automatically when the URL queue is exhausted (`queue_exhausted`).
- Enforces strict safety ceilings to prevent runaway crawls on infinite or massive sites:
  - **Max Pages Ceiling**: 500 pages (`AUTO_MAX_PAGES`)
  - **Max Records Ceiling**: 2,500 records (`AUTO_MAX_RECORDS`)
  - **Max Depth**: 10 levels (`AUTO_MAX_DEPTH`)
  - **Timeout**: 600 seconds (`AUTO_CRAWL_TIMEOUT_SECONDS`)

### 2. Bounded Mode (`mode="bounded"`)
Designed for targeted, limited crawls:
- Accepts explicit user constraints:
  - `max_pages`: 1 to 1,000 (default: 5)
  - `max_records`: 1 to 5,000 (default: 50)
  - `delay_seconds`: 0.0 to 5.0 seconds (default: 0.5s)
- Terminates as soon as page or record limits are reached.

---

## 📦 Output Artifacts

Every completed crawl writes four canonical JSON artifacts atomically to `output/<job_id>/`:

| Artifact | Filename | Description |
| :--- | :--- | :--- |
| **Products** | `products.json` | Extracted product records with titles, prices, descriptions, product URLs, and rich image arrays. |
| **Visited Pages** | `website_pages.json` | Inventory of all crawled URLs with HTTP status codes, page type classifications, extracted heading trees, and text excerpts. |
| **Extraction Report** | `extraction_report.json` | Comprehensive crawl telemetry including duration, stop reason, crawl completeness, page counts, and extraction strategy metrics. |
| **Sitemap Inventory** | `sitemap_inventory.json` | Discovered sitemap URLs and locator metadata gathered during pre-crawl probing. |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/scrape` | Submit a new crawl job (`url`, `mode`, `max_pages`, `max_records`, `delay_seconds`). |
| `GET` | `/api/jobs/{job_id}` | Poll job status, progress, statistics, and extracted preview records. |
| `GET` | `/api/jobs/{job_id}/pages` | Retrieve the visited pages inventory (`website_pages.json`) for frontend inspection. |
| `GET` | `/api/jobs/{job_id}/download` | Legacy endpoint returning `products.json` as an attachment (backward compatible). |
| `GET` | `/api/jobs/{job_id}/download/{artifact_type}` | Download a specific artifact: `products`, `pages`, `report`, or `sitemap`. |
| `GET` | `/api/jobs/{job_id}/download/bundle` | Download a complete in-memory ZIP bundle containing all four JSON artifacts. |
| `GET` | `/api/health` | Service health check. |

All artifact endpoints validate the job ID format, enforce strict directory traversal prevention, and return explicit 404 responses if a job or artifact is missing.

---

## 🚀 Quick Start (Windows PowerShell)

### Step 1: Create Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Start Application Server
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🧪 Running Focused & Regression Tests

Run focused tests for API, multi-artifact export, and frontend endpoints:
```powershell
pytest tests/test_phase18_export.py tests/test_api.py
```

Run the 56-test Phase 17 extraction baseline regression set:
```powershell
pytest tests/test_parser.py tests/test_phase17_full_site.py tests/test_phase17_11_defects.py
```

---

## 🛡️ Safety & Security Features

- **SSRF Defense**: Validates URL scheme (`http`/`https`), blocks private and link-local IP addresses (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`), and blocks cloud metadata endpoints (`169.254.169.254`). Validates every DNS resolution and redirect hop.
- **Path Traversal Protection**: Job IDs are validated using strict alphanumeric patterns (`^[a-zA-Z0-9_-]+$`) and output paths are resolved against the canonical output directory.
- **Atomic Writes**: Artifacts are written to temporary files and atomically replaced upon spider completion to prevent corrupted or partial exports.
