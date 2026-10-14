from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, HttpUrl, Field, field_validator, model_validator
from enum import Enum
import re

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class CrawlMode(str, Enum):
    AUTO = "auto"
    BOUNDED = "bounded"

class ScrapeRequest(BaseModel):
    url: str = Field(..., description="Target website URL to scrape")
    mode: Optional[CrawlMode] = Field(None, description="Crawl mode: 'auto' or 'bounded'")
    max_pages: Optional[int] = Field(None, ge=1, le=1000, description="Maximum pages to crawl in bounded mode")
    max_records: Optional[int] = Field(None, ge=1, le=5000, description="Maximum records to extract in bounded mode")
    use_browser_fallback: bool = Field(default=False, description="Enable Playwright browser for JS-heavy sites")
    delay_seconds: float = Field(default=0.5, ge=0.0, le=5.0, description="Delay between requests in seconds")

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def resolve_mode_and_limits(self):
        if self.mode == CrawlMode.AUTO:
            if self.max_pages is not None or self.max_records is not None:
                raise ValueError("Cannot specify max_pages or max_records when mode is 'auto'. Use mode='bounded' for bounded crawls.")
        elif self.mode == CrawlMode.BOUNDED:
            if self.max_pages is None:
                self.max_pages = 5
            if self.max_records is None:
                self.max_records = 50
        else:  # self.mode is None
            if self.max_pages is None and self.max_records is None:
                self.mode = CrawlMode.AUTO
            else:
                self.mode = CrawlMode.BOUNDED
                if self.max_pages is None:
                    self.max_pages = 5
                if self.max_records is None:
                    self.max_records = 50
        return self


class ImageMetadata(BaseModel):
    image_url: str = Field(..., description="Normalized image URL")
    title: Optional[str] = Field(None, description="Image-specific title or label")
    alt: Optional[str] = Field(None, description="Image alt text")
    caption: Optional[str] = Field(None, description="Explicit caption if available")
    section_title: Optional[str] = Field(None, description="Nearest section heading")
    source_page_url: Optional[str] = Field(None, description="Page URL where image was extracted")

class ExtractedRecord(BaseModel):
    title: str = Field(..., description="Main record title")
    image_url: Optional[str] = Field(None, description="Primary image URL")
    description: Optional[str] = Field(None, description="Record summary or content description")
    product_url: Optional[str] = Field(None, description="Direct product or item URL")
    price: Optional[Union[float, str]] = Field(None, description="Extracted price")
    currency: Optional[str] = Field(None, description="Currency symbol or 3-letter code")
    brand: Optional[str] = Field(None, description="Brand name if available")
    sku: Optional[str] = Field(None, description="Product SKU or identifier")
    source_url: str = Field(..., description="URL where record was extracted")
    image_urls: List[str] = Field(default_factory=list, description="All images associated with item")
    images: List[ImageMetadata] = Field(default_factory=list, description="Detailed image metadata list")

class ScrapeStats(BaseModel):
    pages_visited: int = 0
    records_extracted: int = 0
    start_time: str = ""
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    errors: List[str] = Field(default_factory=list)
    stop_reason: str = "queue_exhausted"
    crawl_complete: bool = True

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    target_url: str
    progress: float = 0.0
    status_message: str = "Initialized"
    stats: ScrapeStats = Field(default_factory=ScrapeStats)
    records: List[ExtractedRecord] = Field(default_factory=list)
    error: Optional[str] = None
