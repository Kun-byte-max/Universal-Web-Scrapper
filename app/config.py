import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

class Settings(BaseSettings):
    APP_NAME: str = "Universal Web Scraper"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Server settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # Scraping limits & timeouts
    DEFAULT_MAX_PAGES: int = 5
    MAX_PAGES_LIMIT: int = 50
    DEFAULT_MAX_RECORDS: int = 50
    MAX_RECORDS_LIMIT: int = 500
    REQUEST_TIMEOUT_SECONDS: float = 12.0
    PLAYWRIGHT_TIMEOUT_MS: int = 15000
    MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024  # 10MB
    DEFAULT_DELAY_SECONDS: float = 0.5

    # Auto / Full-site mode emergency ceilings
    AUTO_MAX_PAGES: int = 500
    AUTO_MAX_RECORDS: int = 2500
    AUTO_MAX_DEPTH: int = 10
    AUTO_CRAWL_TIMEOUT_SECONDS: float = 600.0
    
    # Security
    ALLOW_PRIVATE_IPS: bool = False
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36 (UniversalWebScraper/1.0)"
    )
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

